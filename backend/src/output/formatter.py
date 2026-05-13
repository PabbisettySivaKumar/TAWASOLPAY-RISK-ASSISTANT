"""
Format pipeline results into the API response shape.

Builds RiskEntry pydantic models from raw scored risks + retrieved
NIST excerpts + LLM-generated explanations.
"""

from src.api.schemas import RiskEntry, RiskListResponse


def build_risk_entry(
    rank: int,
    scored_risk,
    asset_row,
    vuln_row,
    threat_intel_match,
    business_service,
    nist_controls: list,
    explanation: str,
) -> RiskEntry:
    """Assemble one RiskEntry from all the pieces."""
    # TODO: implement
    raise NotImplementedError


def build_response(entries: list[RiskEntry]) -> RiskListResponse:
    """Wrap entries in the response envelope with a timestamp."""
    from datetime import datetime, timezone
    return RiskListResponse(
        risks=entries,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
