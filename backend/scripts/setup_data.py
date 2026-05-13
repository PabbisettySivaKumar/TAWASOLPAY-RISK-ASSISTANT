"""
One-time setup script.

Run this once after cloning the repo (and after dropping the CSVs into
data/raw/). It will:
    1. Download CISA KEV catalog        -> data/reference/cisa_kev.csv
    2. Download NIST 800-53 catalog     -> data/reference/nist_800_53.json
    3. Chunk + embed NIST controls
    4. Persist vector store             -> data/chroma_db/

After it finishes, the FastAPI server can start cleanly.

Usage:
    python scripts/setup_data.py
"""

from src.ingestion.fetch_kev import download_kev
from src.ingestion.fetch_nist import download_nist, load_nist_controls
from src.rag.chunker import chunk_controls
from src.rag.embedder import embed_texts
from src.rag.vector_store import build_collection


def main() -> None:
    print("[1/4] Downloading CISA KEV catalog...")
    # TODO: download_kev()

    print("[2/4] Downloading NIST 800-53 catalog...")
    # TODO: download_nist()

    print("[3/4] Chunking NIST controls...")
    # TODO: controls = load_nist_controls()
    # TODO: chunks = chunk_controls(controls)

    print("[4/4] Embedding + persisting to ChromaDB...")
    # TODO: embeddings = embed_texts([c.text for c in chunks])
    # TODO: build_collection(chunks, embeddings)

    print("Setup complete.")


if __name__ == "__main__":
    main()
