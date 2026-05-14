---
title: TawasolPay Risk Assistant Backend
emoji: 🛡️
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Ranks cyber risks with NIST 800-53 RAG guidance.
---

# TawasolPay Risk Assistant — Backend

FastAPI service that ingests TawasolPay's security data, scores risks, retrieves NIST 800-53 guidance via RAG, and exposes everything over HTTP.

> **Deployed on Hugging Face Spaces:** this repo is pushed as-is to a Docker Space. The `Dockerfile` runs `uvicorn` on port 7860 (HF's required port). Set `GEMINI_API_KEY` and `GROQ_API_KEY` as Space secrets — the rest works out of the box because `data/raw/`, `data/reference/`, and the pre-built `data/chroma_db/` are committed to the repo.

## Quick start (local)

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY and GROQ_API_KEY

# 4. Drop the data pack CSVs + threat report into data/raw/
#    Files expected:
#      assets.csv, vulnerabilities.csv, threat_intelligence.csv,
#      business_services.csv, remediation_guidance.csv,
#      synthetic_threat_report.md

# 5. One-time setup: fetch CISA KEV + NIST 800-53, build vector store
python scripts/setup_data.py

# 6. Run the API server
uvicorn src.api.main:app --reload --port 8000
```

Then open: `http://localhost:8000/docs` — FastAPI's interactive Swagger UI.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Health check + system status |
| GET | `/risks/top` | Top 5 ranked risks with evidence + NIST guidance |
| GET | `/risks/{risk_id}` | Details for one risk |
| GET | `/data/status` | What CSVs are currently loaded (rows, size, last modified) |
| POST | `/data/refresh` | Reload caches + rebuild vector store |
| POST | `/data/upload/{dataset}` | **Replace one CSV** — for daily refreshes |
| POST | `/data/upload/threat-report` | Replace the markdown threat report |
| POST | `/data/upload/batch` | **Replace all 5 CSVs at once** (and optionally the threat report) |
| GET | `/docs` | Swagger UI (auto-generated) |

### Upload behavior

- The previous version of each file is automatically backed up to `data/backups/` with a timestamp.
- The last 5 backups per dataset are kept; older ones are pruned.
- Files are validated against the schema in `src/config.py:DATASET_SCHEMAS` before any write happens.
- Writes are atomic (stage to `.tmp`, validate, rename).
- Caches are invalidated after any successful upload so the next `/risks/top` request sees fresh data.

### Example upload calls

```bash
# Single CSV
curl -X POST "http://localhost:8000/data/upload/assets" \
     -F "file=@/path/to/new_assets.csv"

# Batch (all 5)
curl -X POST "http://localhost:8000/data/upload/batch" \
     -F "assets=@/path/to/assets.csv" \
     -F "vulnerabilities=@/path/to/vulnerabilities.csv" \
     -F "threat_intelligence=@/path/to/threat_intelligence.csv" \
     -F "business_services=@/path/to/business_services.csv" \
     -F "remediation_guidance=@/path/to/remediation_guidance.csv" \
     -F "threat_report=@/path/to/synthetic_threat_report.md"
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google AI Studio free key — https://aistudio.google.com |
| `GROQ_API_KEY` | Yes | Groq Cloud free key — https://console.groq.com |
| `BACKEND_PORT` | No | Defaults to 8000 |

## Folder structure

See `docs/ARCHITECTURE.md` for the full breakdown of every folder and file.

## Deployment

Backend deploys to Hugging Face Spaces (Docker SDK). See `docs/DEPLOYMENT.md`.

## Assignment write-up

### Q1 — How did you split the data, and why?

The data lives in three folders that each have a distinct lifecycle and trust boundary:

- **`data/raw/`** — the five assignment CSVs and the threat report. This is the **customer's data**: it changes daily, is uploaded through `/data/upload/*`, and every write is atomic and auto-backed-up to `data/backups/`. The schema for each file is locked in `config.py:DATASET_SCHEMAS` and validated before any write touches disk.
- **`data/reference/`** — externally-fetched ground truth: CISA KEV (~1,590 rows) and NIST SP 800-53 Rev. 5 (~1,189 controls). These are **third-party authoritative sources** — we don't own them, but we cache them locally so we don't depend on the network at request time. Refresh is explicit via `scripts/setup_data.py` or `POST /data/refresh`.
- **`data/chroma_db/`** — the **derived** vector store. It's the embedded form of NIST 800-53, persisted to disk so Hugging Face Spaces doesn't rebuild it on every cold start. It's committed to Git for the same reason (~10 MB, well under HF's limits) so deploy is one `git push`.

The split reflects who owns each piece: TawasolPay owns `raw/`, NIST/CISA own `reference/`, and the build pipeline owns `chroma_db/`. Cache invalidation rules follow naturally — a fresh CSV upload invalidates the data-bundle cache but **not** the vector store; refreshing NIST rebuilds the vector store but not the in-memory data bundle.

### Q2 — Where can this system fail, and how does it degrade?

I designed for three failure modes that are likely in a take-home / demo environment:

| Failure | Symptom | Behavior |
|---|---|---|
| **LLM call fails** (no API key, rate limit, network error) | `_llm_explanation()` raises | Falls back to a deterministic rule-based template in `_rule_based_explanation()`. The API still returns explanations — they're just less polished prose. |
| **Vector store missing or empty** (forgot to run `setup_data.py`) | `retrieve_for_risk()` raises | Caught in `orchestrator._retrieve_nist_controls`; the risk entry gets an empty `nist_controls` list. The LLM prompt tells the model "no retrieved NIST guidance — speak only to scoring evidence" so it doesn't hallucinate control IDs. |
| **Bad CSV uploaded** | Missing column, wrong type, parsing error | Upload validation runs **before** the file is written, the previous version is preserved, and the route returns 400 with the validation error. No partial state. |

Two failure modes I am **not** defending against:
- **CISA KEV mirror unreachable at setup time** — the system needs at least one successful fetch to bootstrap. Mitigated by committing `data/reference/cisa_kev.csv` so a fresh clone works offline.
- **Drift between the embedding model and the persisted index** — if `all-MiniLM-L6-v2` is ever swapped, the existing ChromaDB needs to be rebuilt. There's no version check today; an obvious next step is to write the model name into the collection metadata and refuse to query if it doesn't match.

### Q3 — If I had one more day, what would I change?

**Deduplicate the top-N by CVE-on-asset-cluster.** Today the top-5 is dominated by the four VPN edge gateways — same two CVEs (CVE-2024-21762, CVE-2024-55591) appear repeatedly because the cluster is homogeneous. From a security analyst's point of view that's one finding, not four. I'd add a post-scoring pass that groups by `(cve_id, asset_role)` and returns one representative per group with a `replicated_on` field listing the other affected assets. The composite score stays the same; the surface area of the top-5 widens to actually distinct risks.

A close second would be **adding the asset_role and business_service into the RAG query string** more aggressively — the current retrieval surfaces development-process controls (SA-15 family) for an internet-exposed VPN gateway, when SI-2 (Flaw Remediation) and SI-3 (Malicious Code Protection) are more operationally relevant. The fix is mostly in `retriever.build_query_from_risk()`: weight terms like "internet-facing perimeter device" and "patch management" higher.
