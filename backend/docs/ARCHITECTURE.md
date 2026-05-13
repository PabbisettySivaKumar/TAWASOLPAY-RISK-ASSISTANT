# Backend Architecture

This document explains every folder and file in the backend, so anyone (you, the reviewer, or future-you) can navigate the codebase quickly.

## High-level data flow

```
                ┌──────────────────────────────────────────────┐
                │           FastAPI /risks/top route           │
                └──────────────────────┬───────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │       src/pipeline/orchestrator.py           │
                │              (the main glue)                 │
                └──────────────────────┬───────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
┌───────────────┐            ┌───────────────────┐         ┌───────────────────┐
│   ingestion   │            │      scoring      │         │        rag        │
│               │            │                   │         │                   │
│ load_data.py  │            │  risk_engine.py   │         │   retriever.py    │
│ fetch_kev.py  │   ────►    │   (top 5)         │  ────►  │   (NIST top-k)    │
│ fetch_nist.py │            │                   │         │                   │
└───────────────┘            └───────────────────┘         └─────────┬─────────┘
                                                                     │
                                                                     ▼
                                                          ┌───────────────────┐
                                                          │        llm        │
                                                          │                   │
                                                          │  llm_client.py    │
                                                          │   (Gemini→Groq)   │
                                                          │  + prompts.py     │
                                                          └─────────┬─────────┘
                                                                    │
                                                                    ▼
                                                          ┌───────────────────┐
                                                          │      output       │
                                                          │   formatter.py    │
                                                          └─────────┬─────────┘
                                                                    │
                                                                    ▼
                                                            JSON to client
```

## Folder-by-folder

### `src/api/` — HTTP layer
The thinnest layer. Defines routes, request/response schemas, and shared dependencies. **Contains no business logic.** Routes call into `src/pipeline/` or `src/api/upload.py`.

| File | Purpose |
|---|---|
| `main.py` | FastAPI app instance, CORS middleware, route definitions |
| `schemas.py` | Pydantic models for every JSON shape the API exposes/accepts |
| `dependencies.py` | Cached singletons (data bundle, vector store) injected into routes |
| `upload.py` | CSV validation + atomic write + auto-backup for daily data refreshes |

### `src/ingestion/` — Data loading
Everything that reads from disk or network. No transformation logic, just loading.

| File | Purpose |
|---|---|
| `load_data.py` | Reads the 5 CSVs + `synthetic_threat_report.md` from `data/raw/` |
| `fetch_kev.py` | Downloads CISA KEV catalog, exposes lookup helpers |
| `fetch_nist.py` | Downloads NIST 800-53 catalog, exposes a `list[dict]` of controls |

### `src/scoring/` — Risk prioritization
The brain of the assignment. Multi-signal scoring that **does not depend on CVSS alone**.

| File | Purpose |
|---|---|
| `risk_engine.py` | Composite scoring formula. Each signal is a private function; weights come from `config.py` so they're tunable without touching code |

### `src/rag/` — Retrieval-Augmented Generation
The other half of the assignment's marks. Splits the NIST document, embeds it, stores it, retrieves it.

| File | Purpose |
|---|---|
| `chunker.py` | Splits raw NIST controls into chunks ready for embedding |
| `embedder.py` | Wraps `sentence-transformers/all-MiniLM-L6-v2` |
| `vector_store.py` | Wraps ChromaDB persistent client |
| `retriever.py` | Composes a query from a scored risk, embeds it, returns top-k controls |

### `src/llm/` — Generation
One place where the LLM is called. **Every other module imports `generate()` from here.** Keeps prompt engineering and provider config in one spot.

| File | Purpose |
|---|---|
| `llm_client.py` | LiteLLM wrapper. Gemini primary, Groq fallback. Single `generate()` function |
| `prompts.py` | Prompt templates. Easy to iterate on, easy for reviewer to audit |

### `src/pipeline/` — Orchestration
Wires every layer together. Routes call `orchestrator.run_pipeline()`.

| File | Purpose |
|---|---|
| `orchestrator.py` | Top-level pipeline: load → score → retrieve → generate → format |

### `src/output/` — Response shaping
Converts internal data structures into the pydantic models from `api/schemas.py`. Keeps the API layer free of formatting code.

| File | Purpose |
|---|---|
| `formatter.py` | Builds `RiskEntry` and `RiskListResponse` objects |

### `src/config.py`
Single source of truth for paths, model names, weights, and secrets. Uses `pydantic-settings` so values can be overridden by environment variables without code changes.

### `data/`
Read-side data for the system. Split into four subfolders:

| Folder | Contents | Committed to Git? |
|---|---|---|
| `data/raw/` | The 5 assignment CSVs + `synthetic_threat_report.md` | Yes |
| `data/reference/` | Downloaded CISA KEV + NIST 800-53 | Yes (small) |
| `data/chroma_db/` | Persisted vector store | Yes (so HF Spaces doesn't rebuild on cold start) |
| `data/backups/` | Auto-backups of previous CSV versions (timestamped) | No (only README) |

### `scripts/`

| File | Purpose |
|---|---|
| `setup_data.py` | One-time setup: download external data, build vector store |
| `test_pipeline.py` | Runs the full pipeline from CLI without HTTP — fast feedback loop |

### `tests/`
Lightweight unit tests. Not aiming for full coverage — just enough to catch regressions in the scoring formula and retrieval correctness.

### `docs/`

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | This file |
| `DEPLOYMENT.md` | How to deploy to Hugging Face Spaces |

## Why this layout

- **Separation of concerns**: API layer is thin, business logic is in modules
- **Testable**: each module has a single responsibility, mock its inputs and test in isolation
- **Frontend-agnostic**: when the frontend phase starts, it imports from `src/` or hits the HTTP API — no refactor needed
- **Reviewer-friendly**: a reviewer can read this doc, then jump to `risk_engine.py` and `retriever.py` to see the two pieces being evaluated
