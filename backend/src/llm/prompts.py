"""
Prompt templates for the LLM layer.

Keeping prompts in one file makes them easy to iterate on and review.
The reviewer can read this file to see exactly how the LLM is being asked
to ground its output in retrieved NIST text — no hidden magic.
"""

EXPLANATION_SYSTEM = """You are a cybersecurity risk analyst writing for a CISO board briefing.
Be concise, factual, and grounded ONLY in the evidence provided.
Do not invent CVEs, threat actors, or NIST controls.
Do not use markdown, bullet points, or headers — write 2-3 plain sentences."""


EXPLANATION_USER_TEMPLATE = """Risk evidence:
- Asset: {asset_name} ({asset_environment}, internet-exposed: {internet_exposed})
- Vulnerability: {cve_id}, CVSS {cvss}
- Active exploit available: {active_exploit}
- Threat actor match: {threat_actor_summary}
- Business service at risk: {business_service}
- Missing controls: {missing_controls}
- Composite risk score: {risk_score}/100

Retrieved NIST 800-53 guidance:
{nist_excerpts}

Write 2-3 sentences explaining (a) why this ranks where it does, and
(b) what the NIST control above recommends doing about it. Reference
the control by its ID (e.g., "SI-2"). Do not repeat the evidence verbatim."""


def format_explanation_prompt(risk_data: dict, nist_excerpts: str) -> tuple[str, str]:
    """Return (system, user) prompt for the explanation generation."""
    user = EXPLANATION_USER_TEMPLATE.format(
        nist_excerpts=nist_excerpts,
        **risk_data,
    )
    return EXPLANATION_SYSTEM, user
