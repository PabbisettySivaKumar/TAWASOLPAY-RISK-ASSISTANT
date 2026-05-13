"""
Multi-signal risk scoring engine.

Computes a composite risk score for each vulnerability that combines:
    - CVSS technical severity                       (weight from config)
    - Internet exposure of the asset                (weight from config)
    - Active exploit availability                   (weight from config)
    - Threat actor / campaign match for the CVE     (weight from config)
    - Business service criticality                  (weight from config)
    - Missing compensating controls (e.g. no EDR)   (weight from config)

The score is normalized to 0..100. Top 5 highest are returned.

Why not just CVSS:
    A CVSS 10 on an internal dev box should NOT outrank a CVSS 8 on the
    internet-exposed payment gateway with an active ransomware campaign
    pointing at it. This scoring captures that.
"""

from dataclasses import dataclass, field

import pandas as pd

from src.config import settings
from src.ingestion.load_data import match_threat_intel_to_cves


@dataclass
class ScoredRisk:
    """A scored, ranked risk with all context needed for downstream layers."""
    risk_id: str
    score: float
    asset_id: str
    cve_id: str
    score_breakdown: dict
    evidence: dict = field(default_factory=dict)


def score_all_risks(
    vulnerabilities: pd.DataFrame,
    assets: pd.DataFrame,
    threat_intel: pd.DataFrame,
    business_services: pd.DataFrame,
    kev_df: pd.DataFrame | None,
) -> list[ScoredRisk]:
    """Score every vulnerability and return them sorted high-to-low."""
    enriched = _enrich(vulnerabilities, assets, business_services)
    threat_cves, ransom_cves_ti, threat_lookup = _build_threat_index(
        vulnerabilities, threat_intel
    )
    kev_cves, kev_ransom_cves = _build_kev_index(kev_df)

    scored: list[ScoredRisk] = []
    for _, row in enriched.iterrows():
        scored.append(_score_row(row, threat_cves, ransom_cves_ti, threat_lookup,
                                 kev_cves, kev_ransom_cves))

    return sorted(scored, key=lambda r: r.score, reverse=True)


def get_top_n(scored: list[ScoredRisk], n: int = 5) -> list[ScoredRisk]:
    """Return the top-N risks."""
    return sorted(scored, key=lambda r: r.score, reverse=True)[:n]


# ---------- Internals ----------

def _enrich(
    vulnerabilities: pd.DataFrame,
    assets: pd.DataFrame,
    business_services: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join vulns onto asset + business_service context."""
    df = vulnerabilities.merge(assets, on="asset_id", how="left", suffixes=("", "_asset"))
    df = df.merge(business_services, on="business_service", how="left", suffixes=("", "_svc"))
    return df


def _build_threat_index(
    vulnerabilities: pd.DataFrame,
    threat_intel: pd.DataFrame,
) -> tuple[set[str], set[str], dict[str, dict]]:
    """
    Returns:
        - set of CVE ids that have any matching threat intel
        - set of CVE ids whose matched threat intel is ransomware-linked
        - lookup dict: cve -> first matching threat-intel record (for evidence)
    """
    matched = match_threat_intel_to_cves(vulnerabilities, threat_intel)
    if matched.empty:
        return set(), set(), {}

    matched["cve"] = matched["cve"].astype(str).str.upper()
    threat_cves = set(matched["cve"])

    if "ransomware_association" in matched.columns:
        ransom_cves = set(matched.loc[matched["ransomware_association"] == True, "cve"])
    else:
        ransom_cves = set()

    lookup = {row["cve"]: row.to_dict() for _, row in matched.iterrows()}
    return threat_cves, ransom_cves, lookup


def _build_kev_index(kev_df: pd.DataFrame | None) -> tuple[set[str], set[str]]:
    """Returns (set of KEV CVE ids, set of KEV CVE ids flagged ransomware)."""
    if kev_df is None or kev_df.empty or "cveID" not in kev_df.columns:
        return set(), set()

    cves = set(kev_df["cveID"].astype(str).str.upper())
    if "knownRansomwareCampaignUse" in kev_df.columns:
        ransom = set(
            kev_df.loc[
                kev_df["knownRansomwareCampaignUse"].astype(str).str.lower() == "known",
                "cveID",
            ].astype(str).str.upper()
        )
    else:
        ransom = set()
    return cves, ransom


def _score_row(
    row: pd.Series,
    threat_cves: set[str],
    ransom_cves_ti: set[str],
    threat_lookup: dict[str, dict],
    kev_cves: set[str],
    kev_ransom_cves: set[str],
) -> ScoredRisk:
    cve = str(row.get("cve", "")).upper()

    cvss_value = _safe_float(row.get("cvss"))
    internet_exposed = bool(row.get("internet_exposed", False))
    exploit_available = bool(row.get("exploit_available", False))
    in_kev = cve in kev_cves
    ti_matched = cve in threat_cves
    ti_ransom = cve in ransom_cves_ti or cve in kev_ransom_cves
    criticality = str(row.get("criticality") or "medium")
    edr_installed = bool(row.get("edr_installed", True))

    cvss_s = _cvss_signal(cvss_value)
    expo_s = _exposure_signal(internet_exposed)
    expl_s = _exploit_signal(exploit_available, in_kev)
    ti_s = _threat_intel_signal(ti_matched, ti_ransom)
    crit_s = _criticality_signal(criticality)
    ctrl_s = _missing_controls_signal(edr_installed)

    contributions = {
        "cvss": cvss_s * settings.WEIGHT_CVSS,
        "internet_exposure": expo_s * settings.WEIGHT_INTERNET_EXPOSURE,
        "active_exploit": expl_s * settings.WEIGHT_ACTIVE_EXPLOIT,
        "threat_intel": ti_s * settings.WEIGHT_THREAT_INTEL_MATCH,
        "business_criticality": crit_s * settings.WEIGHT_BUSINESS_CRITICALITY,
        "missing_controls": ctrl_s * settings.WEIGHT_MISSING_CONTROLS,
    }
    score = round(sum(contributions.values()) * 100, 2)

    breakdown = {
        "cvss": {"value": cvss_value, "signal": round(cvss_s, 3),
                 "weight": settings.WEIGHT_CVSS,
                 "contribution": round(contributions["cvss"] * 100, 2)},
        "internet_exposure": {"value": internet_exposed, "signal": expo_s,
                              "weight": settings.WEIGHT_INTERNET_EXPOSURE,
                              "contribution": round(contributions["internet_exposure"] * 100, 2)},
        "active_exploit": {"exploit_available": exploit_available, "in_kev": in_kev,
                           "signal": round(expl_s, 3),
                           "weight": settings.WEIGHT_ACTIVE_EXPLOIT,
                           "contribution": round(contributions["active_exploit"] * 100, 2)},
        "threat_intel": {"matched": ti_matched, "ransomware": ti_ransom,
                         "signal": round(ti_s, 3),
                         "weight": settings.WEIGHT_THREAT_INTEL_MATCH,
                         "contribution": round(contributions["threat_intel"] * 100, 2)},
        "business_criticality": {"value": criticality, "signal": round(crit_s, 3),
                                 "weight": settings.WEIGHT_BUSINESS_CRITICALITY,
                                 "contribution": round(contributions["business_criticality"] * 100, 2)},
        "missing_controls": {"edr_installed": edr_installed, "signal": ctrl_s,
                             "weight": settings.WEIGHT_MISSING_CONTROLS,
                             "contribution": round(contributions["missing_controls"] * 100, 2)},
    }

    evidence = {
        "asset_name": _safe_str(row.get("asset_name")),
        "asset_type": _safe_str(row.get("asset_type")),
        "environment": _safe_str(row.get("environment")),
        "owner_team": _safe_str(row.get("owner_team")),
        "vendor_product": _safe_str(row.get("vendor_product")),
        "business_service": _safe_str(row.get("business_service")),
        "business_owner": _safe_str(row.get("business_owner")),
        "customer_facing": bool(row.get("customer_facing", False)),
        "compliance_scope": _safe_str(row.get("compliance_scope")),
        "vulnerability_name": _safe_str(row.get("vulnerability_name")),
        "severity": _safe_str(row.get("severity")),
        "days_open": _safe_int(row.get("days_open")),
        "patch_available": bool(row.get("patch_available", False)),
        "threat_actor": _safe_str(threat_lookup.get(cve, {}).get("threat_actor")),
        "campaign_name": _safe_str(threat_lookup.get(cve, {}).get("campaign_name")),
        "threat_summary": _safe_str(threat_lookup.get(cve, {}).get("summary")),
    }

    return ScoredRisk(
        risk_id=str(row.get("vuln_id") or f"{row.get('asset_id', '?')}::{cve}"),
        score=score,
        asset_id=str(row.get("asset_id", "")),
        cve_id=cve,
        score_breakdown=breakdown,
        evidence=evidence,
    )


def _safe_float(v) -> float:
    try:
        f = float(v)
        return 0.0 if pd.isna(f) else f
    except (TypeError, ValueError):
        return 0.0


def _safe_int(v) -> int | None:
    try:
        if pd.isna(v):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_str(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s and s.lower() != "nan" else None


# ---------- Individual signal calculators ----------
# Each returns a 0..1 contribution that gets multiplied by the weight.

def _cvss_signal(cvss: float) -> float:
    """Normalize CVSS (0-10) to 0..1."""
    return min(max(cvss / 10.0, 0.0), 1.0)


def _exposure_signal(internet_exposed: bool) -> float:
    return 1.0 if internet_exposed else 0.0


def _exploit_signal(exploit_available: bool, in_kev: bool) -> float:
    """1.0 if both exploit + in KEV, 0.7 if just exploit, 0.5 if just KEV, 0 else."""
    if exploit_available and in_kev:
        return 1.0
    if in_kev:
        return 0.7
    if exploit_available:
        return 0.5
    return 0.0


def _threat_intel_signal(matched: bool, ransomware: bool) -> float:
    if matched and ransomware:
        return 1.0
    if matched:
        return 0.6
    return 0.0


def _criticality_signal(criticality: str) -> float:
    mapping = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
    return mapping.get(criticality.lower(), 0.5)


def _missing_controls_signal(edr_installed: bool) -> float:
    return 1.0 if not edr_installed else 0.0
