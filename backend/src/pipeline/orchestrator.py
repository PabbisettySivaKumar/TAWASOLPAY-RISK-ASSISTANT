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

from datetime import datetime, timezone

from src.api.dependencies import get_data_bundle, get_kev_catalog
from src.api.schemas import (
    NistControl,
    RiskEntry,
    RiskListResponse,
    ThreatIntelMatch,
)
from src.scoring.risk_engine import ScoredRisk, get_top_n, score_all_risks


def run_pipeline(top_n: int = 5) -> RiskListResponse:
    """Run the full pipeline end-to-end and return the API response."""
    bundle = get_data_bundle()
    kev = get_kev_catalog()

    scored = score_all_risks(
        vulnerabilities=bundle.vulnerabilities,
        assets=bundle.assets,
        threat_intel=bundle.threat_intelligence,
        business_services=bundle.business_services,
        kev_df=kev,
    )
    top = get_top_n(scored, n=top_n)

    entries = [_to_risk_entry(r, rank=i + 1) for i, r in enumerate(top)]
    return RiskListResponse(
        risks=entries,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _to_risk_entry(r: ScoredRisk, rank: int) -> RiskEntry:
    ev = r.evidence
    bd = r.score_breakdown

    nist_controls = _retrieve_nist_controls(r)

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
    except Exception:
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
    except Exception:
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
        if len(excerpt) > 700:
            excerpt = excerpt[:700].rstrip() + "..."
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
