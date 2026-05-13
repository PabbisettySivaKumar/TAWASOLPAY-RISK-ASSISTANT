"""
Shared orchestrator for external data refresh.

This is the SINGLE source of truth for how we fetch CISA KEV and NIST 800-53
and how we rebuild the RAG vector store after a NIST refresh.

Both the CLI script (scripts/setup_data.py) AND the API routes
(/data/external/refresh/*) call into this module. Adding a new caller means
zero new logic — just a new entry point that calls these functions.

Public functions:
    refresh_kev()       — download CISA KEV, save to disk
    refresh_nist()      — download NIST 800-53, rebuild vector store
    refresh_all()       — both, partial-success allowed
    get_external_status() — report what's downloaded and how fresh it is

Each function returns a structured dict that the API can serialize directly
and the CLI script can pretty-print.
"""

import time
from datetime import datetime, timezone
from pathlib import Path

from src.ingestion.fetch_kev import (
    KEV_LOCAL_PATH,
    download_kev,
    load_kev_local,
)
from src.ingestion.fetch_nist import (
    NIST_LOCAL_PATH,
    download_nist,
    load_nist_controls,
)


# ---------------------------------------------------------------
# KEV — download only (no embedding/rebuild needed)
# ---------------------------------------------------------------

def refresh_kev() -> dict:
    """
    Download the latest CISA KEV catalog and save it locally.

    Returns a dict with:
        success, source, rows_downloaded, size_bytes,
        downloaded_at, duration_seconds, error (if any)
    """
    started_at = time.monotonic()
    started_iso = datetime.now(timezone.utc).isoformat()

    previous_size = KEV_LOCAL_PATH.stat().st_size if KEV_LOCAL_PATH.exists() else 0

    try:
        download_kev()
        df = load_kev_local()
    except Exception as e:
        return {
            "success": False,
            "source": "cisa_kev",
            "error": f"{type(e).__name__}: {e}",
            "started_at": started_iso,
            "duration_seconds": round(time.monotonic() - started_at, 2),
        }

    new_size = KEV_LOCAL_PATH.stat().st_size

    return {
        "success": True,
        "source": "cisa_kev",
        "filename": KEV_LOCAL_PATH.name,
        "rows_downloaded": len(df),
        "previous_size_bytes": previous_size,
        "new_size_bytes": new_size,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started_at, 2),
    }


# ---------------------------------------------------------------
# NIST — download + chunk + embed + rebuild vector store
# ---------------------------------------------------------------

def refresh_nist(rebuild_vector_store: bool = True) -> dict:
    """
    Download the latest NIST 800-53 catalog and (by default) rebuild the
    ChromaDB vector store so retrieval reflects the new content.

    If `rebuild_vector_store` is False, only the CSV is refreshed; the vector
    store is left untouched. Useful for debugging.

    Returns a dict with:
        success, source, rows_downloaded, vector_store_rebuilt,
        chunks_indexed, downloaded_at, duration_seconds, error (if any)
    """
    started_at = time.monotonic()
    started_iso = datetime.now(timezone.utc).isoformat()

    previous_size = NIST_LOCAL_PATH.stat().st_size if NIST_LOCAL_PATH.exists() else 0

    # Step 1: download
    try:
        download_nist()
    except Exception as e:
        return {
            "success": False,
            "source": "nist_800_53",
            "stage": "download",
            "error": f"{type(e).__name__}: {e}",
            "started_at": started_iso,
            "duration_seconds": round(time.monotonic() - started_at, 2),
        }

    # Step 2: parse
    try:
        controls = load_nist_controls()
    except Exception as e:
        return {
            "success": False,
            "source": "nist_800_53",
            "stage": "parse",
            "error": f"{type(e).__name__}: {e}",
            "started_at": started_iso,
            "duration_seconds": round(time.monotonic() - started_at, 2),
        }

    new_size = NIST_LOCAL_PATH.stat().st_size

    result = {
        "success": True,
        "source": "nist_800_53",
        "filename": NIST_LOCAL_PATH.name,
        "rows_downloaded": len(controls),
        "previous_size_bytes": previous_size,
        "new_size_bytes": new_size,
        "vector_store_rebuilt": False,
        "chunks_indexed": 0,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }

    # Step 3: chunk + embed + rebuild (optional)
    if rebuild_vector_store:
        try:
            chunks_indexed = _rebuild_vector_store_from_controls(controls)
            result["vector_store_rebuilt"] = True
            result["chunks_indexed"] = chunks_indexed
        except NotImplementedError:
            # RAG modules not implemented yet — refresh still succeeded
            result["vector_store_rebuilt"] = False
            result["chunks_indexed"] = 0
            result["note"] = (
                "Vector store rebuild skipped — RAG modules not yet implemented. "
                "CSV was refreshed successfully."
            )
        except Exception as e:
            result["success"] = False
            result["stage"] = "vector_store_rebuild"
            result["error"] = f"{type(e).__name__}: {e}"

    result["duration_seconds"] = round(time.monotonic() - started_at, 2)
    return result


def _rebuild_vector_store_from_controls(controls: list[dict]) -> int:
    """
    Internal helper: take parsed NIST controls and rebuild the vector store.

    Returns the number of chunks indexed.

    Imports happen inside the function so this module loads cleanly even
    when sentence-transformers / chromadb aren't installed yet (e.g. during
    early-stage testing).
    """
    from src.rag.chunker import chunk_controls
    from src.rag.embedder import embed_texts
    from src.rag.vector_store import build_collection

    chunks = chunk_controls(controls)
    embeddings = embed_texts([c.text for c in chunks])
    build_collection(chunks, embeddings)
    return len(chunks)


# ---------------------------------------------------------------
# Both
# ---------------------------------------------------------------

def refresh_all(rebuild_vector_store: bool = True) -> dict:
    """
    Refresh both external sources. Partial-success allowed: if KEV fails
    but NIST succeeds (or vice versa), the call returns success=False
    overall but reports each source independently.
    """
    started_at = time.monotonic()

    kev_result = refresh_kev()
    nist_result = refresh_nist(rebuild_vector_store=rebuild_vector_store)

    return {
        "success": kev_result["success"] and nist_result["success"],
        "kev": kev_result,
        "nist": nist_result,
        "duration_seconds": round(time.monotonic() - started_at, 2),
    }


# ---------------------------------------------------------------
# Status
# ---------------------------------------------------------------

def _file_status(path: Path) -> dict:
    """Inspect a file on disk and return a status dict."""
    if not path.exists():
        return {
            "filename": path.name,
            "present": False,
            "size_bytes": 0,
            "last_modified": None,
            "age_hours": None,
        }
    stat = path.stat()
    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - last_modified).total_seconds()
    return {
        "filename": path.name,
        "present": True,
        "size_bytes": stat.st_size,
        "last_modified": last_modified.isoformat(),
        "age_hours": round(age_seconds / 3600, 2),
    }


def get_external_status() -> dict:
    """Report what's downloaded for the two external sources."""
    kev_status = _file_status(KEV_LOCAL_PATH)
    if kev_status["present"]:
        try:
            kev_status["rows"] = len(load_kev_local())
        except Exception:
            kev_status["rows"] = None

    nist_status = _file_status(NIST_LOCAL_PATH)
    if nist_status["present"]:
        try:
            nist_status["rows"] = len(load_nist_controls())
        except Exception:
            nist_status["rows"] = None

    return {"kev": kev_status, "nist": nist_status}