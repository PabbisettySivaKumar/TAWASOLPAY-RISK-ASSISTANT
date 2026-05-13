"""
Embedding wrapper around sentence-transformers.

Uses `all-MiniLM-L6-v2` by default — fast, free, 384-dim vectors,
~80 MB model. Good enough for technical security text.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from src.config import settings


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Lazy-load the embedding model. Cached after first call."""
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns a list of vectors."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]
