"""
Retrieve relevant NIST 800-53 controls for a given risk.

Build a query string from the risk (CVE, asset type, threat actor, etc.),
embed it, query ChromaDB, and return the top-k matching control chunks.
"""

from src.config import settings
from src.rag.embedder import embed_query
from src.rag.vector_store import query_collection


def build_query_from_risk(risk: dict) -> str:
    """
    Compose a natural-language query from a scored risk's evidence.

    Pulls the salient features (asset type, vuln, exposure, threat actor,
    business service, missing controls) into a single paragraph. The
    embedding model maps it to nearby control text in vector space.
    """
    parts: list[str] = []

    vuln_name = risk.get("vulnerability_name") or risk.get("cve_id") or ""
    if vuln_name:
        parts.append(f"Remediation guidance for {vuln_name}.")

    asset_type = risk.get("asset_type")
    if asset_type:
        parts.append(f"Affected asset is a {asset_type}.")

    if risk.get("internet_exposed"):
        parts.append("The asset is internet-exposed.")

    if risk.get("active_exploit") or risk.get("in_kev"):
        parts.append("Exploit code is available and the CVE is actively exploited in the wild.")

    if risk.get("patch_available"):
        parts.append("A vendor patch is available; patch management and flaw remediation are required.")
    else:
        parts.append("No patch is yet available; compensating controls are required.")

    if risk.get("threat_actor"):
        parts.append(
            f"Tracked threat actor {risk['threat_actor']} is running "
            f"{'a ransomware campaign' if risk.get('ransomware') else 'an active campaign'} against this CVE."
        )

    if risk.get("business_service"):
        parts.append(f"The asset supports the '{risk['business_service']}' business service.")

    if risk.get("missing_edr"):
        parts.append("No endpoint detection and response control is installed.")

    return " ".join(parts)


def retrieve_for_risk(risk: dict, top_k: int | None = None) -> list[dict]:
    """
    Return the top-k NIST controls relevant to this risk.
    Each result includes: control_id, control_name, family, excerpt, similarity_score.
    """
    if top_k is None:
        top_k = settings.TOP_K_RETRIEVAL
    query = build_query_from_risk(risk)
    embedding = embed_query(query)
    return query_collection(embedding, top_k=top_k)
