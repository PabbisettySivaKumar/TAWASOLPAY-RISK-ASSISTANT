"""
ChromaDB persistent vector store wrapper.

Persists to data/chroma_db/ on disk so we don't rebuild on every cold start.
We commit data/chroma_db/ to the repo so HF Spaces has it ready on first boot.
"""

import chromadb

from src.config import settings
from src.rag.chunker import NistChunk

COLLECTION_NAME = "nist_800_53"


def get_client() -> chromadb.PersistentClient:
    """Return a persistent ChromaDB client rooted at data/chroma_db/."""
    return chromadb.PersistentClient(path=str(settings.CHROMA_DB_DIR))


def build_collection(chunks: list[NistChunk], embeddings: list[list[float]]) -> None:
    """Wipe and rebuild the collection from chunks + embeddings."""
    # TODO: implement
    raise NotImplementedError


def open_collection():
    """Return the existing collection (raises if not built)."""
    client = get_client()
    return client.get_collection(name=COLLECTION_NAME)


def query_collection(query_embedding: list[float], top_k: int = 3) -> dict:
    """Query the collection and return top-k chunks with metadata + scores."""
    # TODO: implement
    raise NotImplementedError
