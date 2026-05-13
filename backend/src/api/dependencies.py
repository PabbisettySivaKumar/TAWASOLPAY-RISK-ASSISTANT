"""
Shared FastAPI dependencies.

Holds singletons that are expensive to create — the vector store handle,
the loaded dataframes — so routes don't reload them on every request.

Also exposes:
    - require_api_key   : auth dependency for refresh endpoints
    - check_cooldown    : prevent abuse of expensive refresh endpoints
    - invalidate_data_caches : called after uploads
"""

import time
from functools import lru_cache

from fastapi import Header, HTTPException, status

from src.config import settings


# ---------- Singletons / caches ----------

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


# ---------- API key auth (for refresh endpoints) ----------

def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Reject the request unless the X-API-Key header matches settings.API_KEY.

    If API_KEY is empty in settings (i.e. not configured), auth is OPEN —
    useful for local development. In production, set API_KEY in .env.
    """
    expected = settings.API_KEY
    if not expected:
        # No key configured — open access. Don't break local dev.
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
        )


# ---------- Cooldown tracker (rate-limit refresh endpoints) ----------

# In-memory cooldown state. Per-process, which is fine for our single-worker
# deploy. If we ever scale out, this would move to Redis or similar.
_last_refresh_at: dict[str, float] = {}


def check_cooldown(source: str) -> None:
    """
    Raise 429 if the named source was refreshed within COOLDOWN_SECONDS.
    Otherwise, mark this moment as the latest refresh time.
    """
    now = time.monotonic()
    last = _last_refresh_at.get(source, 0.0)
    elapsed = now - last
    if elapsed < settings.REFRESH_COOLDOWN_SECONDS:
        remaining = int(settings.REFRESH_COOLDOWN_SECONDS - elapsed)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Cooldown active for '{source}'. "
                f"Try again in {remaining} second(s)."
            ),
        )
    _last_refresh_at[source] = now