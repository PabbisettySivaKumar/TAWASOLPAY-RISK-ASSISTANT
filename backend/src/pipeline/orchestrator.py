"""
End-to-end pipeline.

Flow:
    1. Load CSVs + threat report                    (ingestion.load_data)
    2. Load CISA KEV                                (ingestion.fetch_kev)
    3. Score every vulnerability                    (scoring.risk_engine)
    4. Take top N                                   (scoring.risk_engine)
    5. For each: retrieve NIST controls             (rag.retriever)
    6. For each: generate plain-English explanation (llm.llm_client)
                 — falls back to rule-based prose if the LLM call fails
                   (no API key, rate limit, network error).
    7. Return RiskListResponse                      (api.schemas)
"""

import logging
import time
from datetime import datetime, timezone

from src.api.dependencies import get_data_bundle, get_kev_catalog
from src.api.schemas import (
    NistControl,
    RiskEntry,
    RiskListResponse,
    ThreatIntelMatch,
)
from src.scoring.risk_engine import ScoredRisk, get_top_n, score_all_risks

logger = logging.getLogger(__name__)


def run_pipeline(top_n: int = 5) -> RiskListResponse:
    """Run the full pipeline end-to-end and return the API response."""
    t_start = time.perf_counter()
    logger.info("pipeline start — top_n=%d", top_n)

    scored = _score_all()
    top = get_top_n(scored, n=top_n)
    logger.info(
        "top %d selected from %d scored risks (top score=%.2f)",
        len(top), len(scored), top[0].score if top else 0.0,
    )

    entries = [_to_risk_entry(r, rank=i + 1) for i, r in enumerate(top)]

    elapsed = time.perf_counter() - t_start
    logger.info("pipeline done — %d risks in %.2fs", len(entries), elapsed)
    return RiskListResponse(
        risks=entries,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def get_risk_by_id(risk_id: str) -> RiskEntry | None:
    """
    Look up a single risk by its risk_id (== vuln_id) and return a full entry.

    Returns None if no risk matches. The rank reflects this risk's position in
    the full sorted list, not just within the top-5.
    """
    t_start = time.perf_counter()
    logger.info("lookup start — risk_id=%s", risk_id)
    scored = _score_all()
    for idx, r in enumerate(scored):
        if r.risk_id == risk_id:
            entry = _to_risk_entry(r, rank=idx + 1)
            elapsed = time.perf_counter() - t_start
            logger.info(
                "lookup hit — risk_id=%s rank=%d score=%.2f in %.2fs",
                risk_id, idx + 1, r.score, elapsed,
            )
            return entry
    logger.info("lookup miss — risk_id=%s not found", risk_id)
    return None


def _score_all() -> list:
    """Load data + KEV, score every vulnerability, return sorted high-to-low."""
    t = time.perf_counter()
    bundle = get_data_bundle()
    kev = get_kev_catalog()
    logger.info(
        "data loaded — assets=%d vulns=%d threat_intel=%d services=%d kev=%d",
        len(bundle.assets), len(bundle.vulnerabilities),
        len(bundle.threat_intelligence), len(bundle.business_services),
        len(kev) if kev is not None else 0,
    )
    scored = score_all_risks(
        vulnerabilities=bundle.vulnerabilities,
        assets=bundle.assets,
        threat_intel=bundle.threat_intelligence,
        business_services=bundle.business_services,
        kev_df=kev,
    )
    logger.info("scored %d risks in %.2fs", len(scored), time.perf_counter() - t)
    return scored


def _to_risk_entry(r: ScoredRisk, rank: int) -> RiskEntry:
    ev = r.evidence
    bd = r.score_breakdown

    logger.info(
        "rank=%d cve=%s asset=%s score=%.2f — retrieving NIST controls",
        rank, r.cve_id, ev.get("asset_name") or r.asset_id, r.score,
    )
    nist_controls = _retrieve_nist_controls(r)
    logger.info(
        "rank=%d nist_controls=%s",
        rank, [c.control_id for c in nist_controls] or "[]",
    )

    threat_intel = None
    if bd["threat_intel"]["matched"]:
        threat_intel = ThreatIntelMatch(
            actor=ev.get("threat_actor") or "Unknown",
            campaign=ev.get("campaign_name") or "Unknown",
            target_sector="",
            ransomware_associated=bd["threat_intel"]["ransomware"],
        )

    return RiskEntry(
        risk_id=r.risk_id,
        rank=rank,
        risk_score=r.score,
        asset_id=r.asset_id,
        asset_name=ev.get("asset_name") or r.asset_id,
        asset_environment=ev.get("environment") or "unknown",
        cve_id=r.cve_id,
        cvss=bd["cvss"]["value"],
        internet_exposed=bd["internet_exposure"]["value"],
        active_exploit=bool(
            bd["active_exploit"]["exploit_available"] or bd["active_exploit"]["in_kev"]
        ),
        business_service=ev.get("business_service") or "unknown",
        threat_intel=threat_intel,
        nist_controls=nist_controls,
        explanation=_explain(r, nist_controls),
    )


def _retrieve_nist_controls(r: ScoredRisk) -> list[NistControl]:
    """Retrieve top-k NIST controls for this risk via RAG. Empty if vector store missing."""
    from src.rag.retriever import retrieve_for_risk

    bd = r.score_breakdown
    ev = r.evidence
    query_risk = {
        "cve_id": r.cve_id,
        "vulnerability_name": ev.get("vulnerability_name"),
        "asset_type": ev.get("asset_type"),
        "business_service": ev.get("business_service"),
        "internet_exposed": bd["internet_exposure"]["value"],
        "active_exploit": bd["active_exploit"]["exploit_available"],
        "in_kev": bd["active_exploit"]["in_kev"],
        "patch_available": ev.get("patch_available"),
        "threat_actor": ev.get("threat_actor"),
        "ransomware": bd["threat_intel"]["ransomware"],
        "missing_edr": not bd["missing_controls"]["edr_installed"],
    }

    try:
        results = retrieve_for_risk(query_risk)
    except Exception as e:
        logger.warning("NIST retrieval failed for %s: %s — returning []", r.cve_id, e)
        return []

    return [
        NistControl(
            control_id=item["control_id"],
            control_name=item["control_name"],
            excerpt=item["excerpt"],
            similarity_score=item["similarity_score"],
        )
        for item in results
    ]


def _explain(r: ScoredRisk, nist_controls: list[NistControl]) -> str:
    """
    Generate the plain-English explanation.

    Tries the LLM first (grounded in retrieved NIST excerpts), falls back to
    a rule-based template if the LLM is unavailable (no key, rate limit, etc.).
    """
    try:
        return _llm_explanation(r, nist_controls)
    except Exception as e:
        logger.warning(
            "LLM explanation failed for %s: %s — using rule-based fallback",
            r.cve_id, e,
        )
        return _rule_based_explanation(r)


def _llm_explanation(r: ScoredRisk, nist_controls: list[NistControl]) -> str:
    """Ask the LLM to write the 2-3 sentence explanation, grounded in NIST excerpts."""
    from src.llm.llm_client import generate
    from src.llm.prompts import format_explanation_prompt

    ev = r.evidence
    bd = r.score_breakdown

    threat_summary = "none"
    if bd["threat_intel"]["matched"]:
        actor = ev.get("threat_actor") or "tracked actor"
        campaign = ev.get("campaign_name") or "active campaign"
        kind = "ransomware campaign" if bd["threat_intel"]["ransomware"] else "campaign"
        threat_summary = f"{actor} running {kind} '{campaign}'"

    missing = []
    if not bd["missing_controls"]["edr_installed"]:
        missing.append("EDR not installed")
    if not ev.get("patch_available"):
        missing.append("no vendor patch available")
    missing_str = ", ".join(missing) if missing else "none"

    risk_data = {
        "asset_name": ev.get("asset_name") or r.asset_id,
        "asset_environment": ev.get("environment") or "unknown",
        "internet_exposed": bd["internet_exposure"]["value"],
        "cve_id": r.cve_id,
        "cvss": bd["cvss"]["value"],
        "active_exploit": bool(
            bd["active_exploit"]["exploit_available"] or bd["active_exploit"]["in_kev"]
        ),
        "threat_actor_summary": threat_summary,
        "business_service": ev.get("business_service") or "unknown",
        "missing_controls": missing_str,
        "risk_score": r.score,
    }

    nist_excerpts = _format_nist_excerpts(nist_controls)
    system, user = format_explanation_prompt(risk_data, nist_excerpts)
    return generate(prompt=user, system=system, temperature=0.2, max_tokens=300).strip()


def _format_nist_excerpts(controls: list[NistControl]) -> str:
    """Render retrieved controls into the block the prompt expects."""
    if not controls:
        return "(no retrieved NIST guidance — speak only to scoring evidence)"
    blocks = []
    for c in controls:
        excerpt = (c.excerpt or "").strip()
        if len(excerpt) > 250:
            excerpt = excerpt[:250].rstrip() + "..."
        blocks.append(f"[{c.control_id}] {c.control_name}\n{excerpt}")
    return "\n\n".join(blocks)


def _rule_based_explanation(r: ScoredRisk) -> str:
    """Deterministic fallback used when the LLM call fails."""
    ev = r.evidence
    bd = r.score_breakdown
    parts: list[str] = []

    asset_label = ev.get("asset_name") or r.asset_id
    asset_type = ev.get("asset_type") or "asset"
    env = ev.get("environment") or "unknown environment"
    service = ev.get("business_service") or "an unknown service"
    parts.append(
        f"This {asset_type} ({asset_label}) in {env} supports the '{service}' business service."
    )

    if bd["internet_exposure"]["value"]:
        parts.append("It is internet-exposed.")

    cvss = bd["cvss"]["value"]
    if cvss:
        parts.append(f"It has {r.cve_id} with CVSS {cvss}.")

    if bd["active_exploit"]["in_kev"]:
        parts.append("This CVE is in CISA's KEV catalog (actively exploited in the wild).")
    elif bd["active_exploit"]["exploit_available"]:
        parts.append("Working exploit code is available.")

    if bd["threat_intel"]["ransomware"]:
        actor = ev.get("threat_actor") or "a known actor"
        campaign = ev.get("campaign_name") or "an active campaign"
        parts.append(
            f"Threat actor {actor} is running ransomware campaign '{campaign}' against this CVE."
        )
    elif bd["threat_intel"]["matched"]:
        actor = ev.get("threat_actor") or "a tracked actor"
        parts.append(f"Threat intelligence links this CVE to {actor}.")

    if not bd["missing_controls"]["edr_installed"]:
        parts.append("No EDR is installed on this asset.")

    parts.append(f"(Composite risk score: {r.score}/100.)")
    return " ".join(parts)
