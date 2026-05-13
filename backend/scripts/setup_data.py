"""
One-time setup script — CLI wrapper for external data refresh.

This is intentionally tiny. All the real work lives in
src/pipeline/data_refresh.py, which is also called by the API
endpoints (POST /data/external/refresh/*). One implementation,
two entry points.

Run this once after cloning the repo:
    python scripts/setup_data.py

It will:
    1. Download CISA KEV catalog    -> data/reference/cisa_kev.csv
    2. Download NIST 800-53 catalog -> data/reference/nist_800_53.csv
    3. Chunk + embed NIST controls and persist the vector store
       -> data/chroma_db/   (skipped automatically if the RAG modules
       aren't implemented yet)

After it finishes, the FastAPI server can start cleanly.
"""

import json

from src.pipeline.data_refresh import refresh_all


def main() -> None:
    print("Refreshing external data sources...\n")
    result = refresh_all(rebuild_vector_store=True)

    # KEV summary
    kev = result["kev"]
    if kev["success"]:
        print(f"  CISA KEV     OK  ({kev['rows_downloaded']} rows, "
              f"{kev['new_size_bytes']/1024:.1f} KB, "
              f"{kev['duration_seconds']}s)")
    else:
        print(f"  CISA KEV     FAIL  {kev.get('error', 'unknown error')}")

    # NIST summary
    nist = result["nist"]
    if nist["success"]:
        msg = (f"  NIST 800-53  OK  ({nist['rows_downloaded']} rows, "
               f"{nist['new_size_bytes']/1024:.1f} KB, "
               f"{nist['duration_seconds']}s)")
        if nist["vector_store_rebuilt"]:
            msg += f"  +  vector store rebuilt ({nist['chunks_indexed']} chunks)"
        elif "note" in nist:
            msg += f"\n               note: {nist['note']}"
        print(msg)
    else:
        print(f"  NIST 800-53  FAIL  [{nist.get('stage', '?')}] "
              f"{nist.get('error', 'unknown error')}")

    print(f"\nTotal duration: {result['duration_seconds']}s")

    if not result["success"]:
        print("\nSetup completed with errors. See above.")
        print("Full result:")
        print(json.dumps(result, indent=2))
        raise SystemExit(1)

    print("\nSetup complete.")


if __name__ == "__main__":
    main()