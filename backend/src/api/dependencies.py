"""
Shared FastAPI dependencies.

Holds singletons that are expensive to create — the vector store handle,
the loaded dataframes — so routes don't reload them on every request.

`invalidate_data_caches()` is called after a successful upload so the next
request sees the fresh data.
"""

from functools import lru_cache


@lru_cache(maxsize=1)
def get_data_bundle():
    """Load and cache all CSV dataframes + threat report."""
    # TODO: from src.ingestion.load_data import load_all
    # return load_all()
    raise NotImplementedError


@lru_cache(maxsize=1)
def get_vector_store():
    """Open and cache the ChromaDB collection."""
    # TODO: from src.rag.vector_store import open_collection
    # return open_collection()
    raise NotImplementedError


@lru_cache(maxsize=1)
def get_kev_catalog():
    """Load and cache the CISA KEV catalog dataframe."""
    # TODO: from src.ingestion.fetch_kev import load_kev_local
    # return load_kev_local()
    raise NotImplementedError


def invalidate_data_caches() -> None:
    """
    Clear cached data after a successful upload so the next request
    reloads from disk. Vector store cache is left alone — only the CSV
    layer changes via uploads.
    """
    get_data_bundle.cache_clear()
    get_kev_catalog.cache_clear()
