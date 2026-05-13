"""
ChromaDB persistent vector store wrapper.

Persists to data/chroma_db/ on disk so we don't rebuild on every cold start.
We commit data/chroma_db/ to the repo so HF Spaces has it ready on first boot.
"""

import logging
import os

# Two-pronged silence for ChromaDB's PostHog telemetry:
#   1) Set the env var before chromadb imports — disables capture entirely
#      on systems where pydantic-settings picks it up.
#   2) Silence the telemetry logger — kills the "capture() takes 1
#      positional argument but 3 were given" stderr spam that surfaces
#      via logger.error() regardless of the disabled flag (chromadb's
#      embedded posthog client is incompatible with the installed
#      posthog version, so every capture() call raises and gets logged).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)

import chromadb  # noqa: E402

from src.config import settings  # noqa: E402
from src.rag.chunker import NistChunk  # noqa: E402

COLLECTION_NAME = "nist_800_53"


def get_client() -> chromadb.PersistentClient:
    """Return a persistent ChromaDB client rooted at data/chroma_db/."""
    settings.CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.CHROMA_DB_DIR))


def build_collection(chunks: list[NistChunk], embeddings: list[list[float]]) -> None:
    """Wipe and rebuild the collection from chunks + embeddings."""
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must match"
        )

    client = get_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except (ValueError, Exception):
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    collection.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "control_id": c.control_id,
                "control_name": c.control_name,
                "family": c.family,
            }
            for c in chunks
        ],
    )


def open_collection():
    """Return the existing collection (raises if not built)."""
    client = get_client()
    return client.get_collection(name=COLLECTION_NAME)


def query_collection(query_embedding: list[float], top_k: int = 3) -> list[dict]:
    """
    Query the collection and return top-k matches.

    Each result is a dict with:
        control_id, control_name, family, excerpt, similarity_score
    """
    collection = open_collection()
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    out: list[dict] = []
    for _id, doc, meta, dist in zip(ids, docs, metas, dists):
        meta = meta or {}
        out.append({
            "control_id": meta.get("control_id", _id),
            "control_name": meta.get("control_name", ""),
            "family": meta.get("family", ""),
            "excerpt": doc or "",
            "similarity_score": round(1.0 - float(dist), 4),
        })
    return out
