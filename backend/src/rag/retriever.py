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
    Compose a natural-language query from a scored risk.

    Example output:
        "Patch management for unpatched CVE-2023-1234 affecting internet-exposed
         payment gateway with active ransomware exploitation."
    """
    # TODO: implement
    raise NotImplementedError


def retrieve_for_risk(risk: dict, top_k: int = None) -> list[dict]:
    """
    Return the top-k NIST controls relevant to this risk.
    Each result includes: control_id, control_name, excerpt, similarity_score.
    """
    if top_k is None:
        top_k = settings.TOP_K_RETRIEVAL
    query = build_query_from_risk(risk)
    embedding = embed_query(query)
    return query_collection(embedding, top_k=top_k)
