"""
Retrieve relevant NIST 800-53 controls for a given risk.

Build a query string from the risk (CVE, asset type, threat actor, etc.),
embed it, query ChromaDB, and return the top-k matching control chunks.
"""

import logging
import time

from src.config import settings
from src.rag.embedder import embed_query
from src.rag.vector_store import query_collection

logger = logging.getLogger(__name__)


def build_sub_queries(risk: dict) -> list[str]:
    """
    Decompose a risk into one short query per concern.

    Each sub-query uses NIST 800-53's own normative vocabulary so cosine
    similarity actually rewards it (e.g. "Install security-relevant patches
    and firmware updates..." hits SI-2 at ~0.67 — far better than a CVE-noun
    phrasing). We run each sub-query independently and pool the hits, which
    avoids the failure mode where one concatenated query is dominated by a
    single concept (e.g. "boundary protection" drowning out SI-2).
    """
    queries: list[str] = []

    if risk.get("patch_available"):
        queries.append(
            "Install security-relevant patches and firmware updates. "
            "Identify, report, and correct system flaws in a timely manner."
        )
    else:
        queries.append(
            "No vendor patch available; apply compensating controls and "
            "isolate the affected component until a fix is released."
        )

    if risk.get("internet_exposed"):
        queries.append(
            "Boundary protection at external network interfaces. Restrict "
            "and monitor connections from untrusted networks to internet-"
            "facing systems."
        )

    if risk.get("active_exploit") or risk.get("in_kev"):
        queries.append(
            "Actively exploited flaw; apply intrusion detection, system "
            "monitoring, and incident response controls."
        )

    if risk.get("ransomware"):
        queries.append(
            "Malicious code protection on endpoints and servers. Backups "
            "and contingency plans for ransomware recovery."
        )
    elif risk.get("threat_actor"):
        queries.append(
            "Threat intelligence and incident response for a tracked "
            "adversary running an active campaign."
        )

    if risk.get("missing_edr"):
        queries.append(
            "Endpoint detection and response and host-based system "
            "monitoring on the asset."
        )

    asset_type = (risk.get("asset_type") or "").lower()
    if asset_type:
        if any(k in asset_type for k in ("vpn", "firewall", "gateway", "edge", "router")):
            queries.append(
                "Network perimeter device; restrict remote access and "
                "protect the boundary."
            )
        elif "server" in asset_type:
            queries.append(
                "Production server; harden configuration and apply least-"
                "functionality controls."
            )

    return queries


def retrieve_for_risk(risk: dict, top_k: int | None = None) -> list[dict]:
    """
    Return the top-k NIST controls relevant to this risk.

    Strategy:
        1. Decompose the risk into one short query per concern (patch,
           exposure, active exploit, threat actor, missing EDR, asset role).
        2. Run each sub-query against the vector store independently
           (top-3 each).
        3. Pool all hits, dedupe by control root (so SC-7(18) and SC-7(21)
           collapse to SC-7 — we keep the highest-scoring variant), and
           sort by similarity.
        4. Return the top-k.

    This avoids the single-query failure mode where one dominant concern
    (e.g. "boundary protection") floods the result set with variants of
    one control family, crowding out SI-2 (Flaw Remediation) and SI-3
    (Malicious Code Protection).
    """
    if top_k is None:
        top_k = settings.TOP_K_RETRIEVAL

    sub_queries = build_sub_queries(risk)
    if not sub_queries:
        logger.info("retrieval skipped — no sub-queries built for risk")
        return []

    t = time.perf_counter()
    best_per_root: dict[str, dict] = {}
    for sub_q in sub_queries:
        embedding = embed_query(sub_q)
        for hit in query_collection(embedding, top_k=3):
            root = hit["control_id"].split("(", 1)[0]
            existing = best_per_root.get(root)
            if existing is None or hit["similarity_score"] > existing["similarity_score"]:
                best_per_root[root] = hit

    ranked = sorted(
        best_per_root.values(),
        key=lambda h: h["similarity_score"],
        reverse=True,
    )
    elapsed = time.perf_counter() - t
    logger.info(
        "retrieval done — %d sub-queries -> %d unique roots -> top %d "
        "(%.0fms)",
        len(sub_queries), len(best_per_root), min(top_k, len(ranked)),
        elapsed * 1000,
    )
    return ranked[:top_k]
