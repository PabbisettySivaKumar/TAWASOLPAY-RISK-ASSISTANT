# Backend Architecture

This document explains every folder and file in the backend so anyone (you, the reviewer, or future-you) can navigate the codebase quickly.

## High-level data flow

The backend serves three distinct pipelines from one FastAPI app.

### 1. Risk-ranking pipeline (the assignment's main ask)

```
                ┌──────────────────────────────────────────────┐
                │  FastAPI  GET /risks/top  /  /risks/{id}     │
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
│ fetch_kev.py  │   ────►    │   (top-N)         │  ────►  │   (NIST top-k)    │
│ fetch_nist.py │            │                   │         │                   │
└───────────────┘            └───────────────────┘         └─────────┬─────────┘
                                                                     │
                                                                     ▼
                                                          ┌───────────────────┐
                                                          │        llm        │
                                                          │                   │
                                                          │  llm_client.py    │
                                                          │  (LiteLLM,        │
                                                          │   env-configured) │
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

### 2. Upload pipeline (daily CSV refresh)

```
POST /data/upload/{dataset}                       POST /data/upload/batch
POST /data/upload/threat-report                   POST /data/clear
              │                                            │
              ▼                                            ▼
        ┌─────────────────────────────────────────────────────┐
        │             src/api/upload.py                       │
        │  schema validation → stage to .tmp → atomic rename  │
        │  → backup previous version → prune old backups      │
        └────────────────────────────┬────────────────────────┘
                                     │
                                     ▼
                  data/raw/  ←  data/backups/  (last 5 per file)
                                     │
                                     ▼
                       invalidate_data_caches()
                       (clears get_data_bundle + get_kev_catalog)
```

### 3. External-data refresh pipeline (CISA KEV + NIST 800-53)

```
POST /data/external/refresh/kev             scripts/setup_data.py
POST /data/external/refresh/nist                        │
POST /data/external/refresh/all                         │
            │                                           │
            ▼                                           ▼
       ┌──────────────────────────────────────────────────┐
       │       src/pipeline/data_refresh.py               │
       │   (single source of truth — same module used     │
       │    by the API routes AND the CLI script)         │
       └──────────────────────────────────────────────────┘
                          │
                          ▼
   ┌─────────────────┐         ┌────────────────────────────────┐
   │  refresh_kev()  │         │     refresh_nist()             │
   │  download CSV   │         │  download CSV + chunk + embed  │
   │  → reference/   │         │  + rebuild ChromaDB collection │
   └─────────────────┘         └────────────────────────────────┘
```

## Folder-by-folder

### `src/api/` — HTTP layer
The thinnest layer. Defines routes, request/response schemas, and shared dependencies. **Contains no business logic.** Routes call into `src/pipeline/` or `src/api/upload.py`.

| File | Purpose |
|---|---|
| `main.py` | FastAPI app instance, CORS middleware, all route definitions |
| `schemas.py` | Pydantic models for every JSON shape the API exposes/accepts |
| `dependencies.py` | Cached singletons (`get_data_bundle`, `get_vector_store`, `get_kev_catalog`); `require_api_key` auth dependency; per-source `check_cooldown`; `invalidate_data_caches` helper |
| `upload.py` | CSV validation + atomic write + auto-backup; powers every `/data/upload/*` and `/data/clear` route |

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
| `retriever.py` | Composes a query from a scored risk, embeds it, returns top-k controls (with multi-query expansion) |

### `src/llm/` — Generation
One place where the LLM is called. **Every other module imports `generate()` from here.** Keeps prompt engineering and provider config in one spot.

| File | Purpose |
|---|---|
| `llm_client.py` | LiteLLM wrapper. Primary + fallback models read from `LLM_PRIMARY_MODEL` / `LLM_FALLBACK_MODEL` env vars (default: Groq primary + Groq fallback). API keys (`GROQ_API_KEY`, optional `GEMINI_API_KEY`) are set into the LiteLLM environment only if non-empty. Single `generate()` function — logs which model actually served the response. |
| `prompts.py` | Prompt templates (`EXPLANATION_SYSTEM`, `EXPLANATION_USER_TEMPLATE`). Easy to iterate on, easy for a reviewer to audit |

### `src/pipeline/` — Orchestration
Wires every layer together. Routes call into this folder.

| File | Purpose |
|---|---|
| `orchestrator.py` | Top-level risk pipeline: load → score → retrieve → generate → format. Exposes `run_pipeline()` and `get_risk_by_id()` |
| `data_refresh.py` | Single source of truth for fetching CISA KEV + NIST 800-53 and rebuilding the vector store. Same module is called by the CLI script (`scripts/setup_data.py`) **and** the API routes (`/data/external/refresh/*`) — one implementation, two entry points |

### `src/output/` — Response shaping
Converts internal data structures into the pydantic models from `api/schemas.py`. Keeps the API layer free of formatting code.

| File | Purpose |
|---|---|
| `formatter.py` | Builds `RiskEntry` and `RiskListResponse` objects |

### `src/config.py`
Single source of truth for paths, model names, weights, and secrets. Uses `pydantic-settings` so values can be overridden by environment variables without code changes.

### `src/logging_setup.py`
Configures structured logging for the whole app. Called once from `main.py` at import time so every module gets a consistent format.

### `data/`
Read-side data for the system. Split into four subfolders:

| Folder | Contents | Committed to Git? |
|---|---|---|
| `data/raw/` | The 5 assignment CSVs + `synthetic_threat_report.md` | Yes |
| `data/reference/` | Downloaded CISA KEV + NIST 800-53 | Yes (small) |
| `data/chroma_db/` | Persisted vector store | Yes — and on the **backend HF Space**, `chroma.sqlite3` and `*.bin` files are tracked via **Git LFS** so the Space ships with a pre-built index |
| `data/backups/` | Auto-backups of previous CSV versions (timestamped) | No (only README) |

### `scripts/`

| File | Purpose |
|---|---|
| `setup_data.py` | One-time setup: downloads CISA KEV + NIST 800-53 and builds the vector store. A thin CLI wrapper around `src/pipeline/data_refresh.refresh_all()` — the same code path as the API routes |
| `test_pipeline.py` | Runs the full risk pipeline from CLI without HTTP — fast feedback loop |

### `tests/`
Lightweight unit tests. Not aiming for full coverage — just enough to catch regressions in the scoring formula and retrieval correctness.

### `docs/`

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | This file |
| `DEPLOYMENT.md` | How to deploy / redeploy the two Hugging Face Spaces |

## Endpoints, at a glance

| Method | Path | Module |
|---|---|---|
| GET  | `/`                              | `api/main.py` |
| GET  | `/risks/top`                     | `pipeline/orchestrator.py:run_pipeline` |
| GET  | `/risks/{risk_id}`               | `pipeline/orchestrator.py:get_risk_by_id` |
| GET  | `/data/status`                   | `api/upload.py:get_data_status` |
| POST | `/data/refresh`                  | `api/dependencies.py:invalidate_data_caches` |
| POST | `/data/clear`                    | `api/upload.py:clear_all_files` |
| POST | `/data/upload/{dataset}`         | `api/upload.py:write_csv_atomic` |
| POST | `/data/upload/threat-report`     | `api/upload.py:write_threat_report_atomic` |
| POST | `/data/upload/batch`             | `api/upload.py` (5× `write_csv_atomic`) |
| GET  | `/data/external/status`          | `pipeline/data_refresh.py:get_external_status` |
| POST | `/data/external/refresh/kev`     | `pipeline/data_refresh.py:refresh_kev` |
| POST | `/data/external/refresh/nist`    | `pipeline/data_refresh.py:refresh_nist` |
| POST | `/data/external/refresh/all`     | `pipeline/data_refresh.py:refresh_all` |
| GET  | `/docs`                          | FastAPI auto-generated Swagger UI |

## The deployed surface

Two Hugging Face Spaces, both owned by `itspsk`:

- **Backend** (Docker, this folder) — https://itspsk-tawasolpay-backend.hf.space
- **Frontend** (Streamlit, `../frontend/`) — https://itspsk-tawasolpay-frontend.hf.space

The frontend is a thin Streamlit client; it has no business logic. See `../frontend/README.md`.

## Why this layout

- **Separation of concerns.** API layer is thin, business logic lives in `src/scoring/`, `src/rag/`, `src/llm/`, and is composed in `src/pipeline/`.
- **One source of truth per concern.** Vector-store rebuild logic lives in `pipeline/data_refresh.py` and is shared by the CLI script and the API routes — nobody re-implements it.
- **Testable.** Each module has a single responsibility, mock its inputs and test in isolation.
- **Reviewer-friendly.** A reviewer can read this doc, then jump to `risk_engine.py` (scoring), `retriever.py` (RAG), and `prompts.py` (LLM prompts) to see exactly the three pieces being evaluated.
