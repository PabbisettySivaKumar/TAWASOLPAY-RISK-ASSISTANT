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

## Live demo

| Surface | URL |
|---|---|
| Frontend (Streamlit) | https://itspsk-tawasolpay-frontend.hf.space |
| Backend (FastAPI)    | https://itspsk-tawasolpay-backend.hf.space |
| Backend docs (Swagger) | https://itspsk-tawasolpay-backend.hf.space/docs |

> **Deployed on Hugging Face Spaces:** this folder is pushed as-is to a Docker Space. The `Dockerfile` runs `uvicorn` on port 7860 (HF's required port). Set `GROQ_API_KEY` (and optionally `LLM_PRIMARY_MODEL` / `LLM_FALLBACK_MODEL`) as Space secrets — the rest works out of the box because `data/raw/`, `data/reference/`, and the pre-built `data/chroma_db/` are committed to the repo.

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
# Edit .env and paste your GROQ_API_KEY (the LLM stack is Groq-only by default;
# GEMINI_API_KEY is optional and only used if you point a model at gemini/*)

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

> On Hugging Face Spaces the container serves on port **7860** instead (HF's required port). The `Dockerfile` runs `uvicorn ... --port 7860` — locally we use 8000 to avoid clashing with anything else.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Health check + system status |
| GET | `/risks/top` | Top-N ranked risks with evidence + NIST guidance |
| GET | `/risks/{risk_id}` | Details for one risk |
| GET | `/data/status` | What CSVs are currently loaded (rows, size, last modified) |
| POST | `/data/refresh` | Invalidate in-memory data caches (next `/risks/top` reloads CSVs from disk). Does **not** touch the vector store. |
| POST | `/data/clear` | Wipe every CSV + threat report in `data/raw/` (backups taken first) |
| POST | `/data/upload/{dataset}` | **Replace one CSV** — for daily refreshes |
| POST | `/data/upload/threat-report` | Replace the markdown threat report |
| POST | `/data/upload/batch` | **Replace all 5 CSVs at once** (and optionally the threat report) |
| GET | `/data/external/status` | What CISA KEV / NIST 800-53 files are downloaded, and how fresh |
| POST | `/data/external/refresh/kev` | Re-download CISA KEV |
| POST | `/data/external/refresh/nist` | Re-download NIST 800-53 + **rebuild the vector store** |
| POST | `/data/external/refresh/all` | Refresh both (partial success allowed) |
| GET | `/docs` | Swagger UI (auto-generated) |

**Auth + cooldown on the external-refresh routes.** If `API_KEY` is set in the environment, all three `POST /data/external/refresh/*` routes require an `X-API-Key` header. If `API_KEY` is empty (local dev default), the routes are open. Each source has an independent 5-minute cooldown (`REFRESH_COOLDOWN_SECONDS`); hitting the same source twice in that window returns `429`.

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
| `GROQ_API_KEY` | Yes | Groq Cloud free key — https://console.groq.com/keys |
| `LLM_PRIMARY_MODEL` | No | LiteLLM model id. Default `groq/llama-3.1-8b-instant`. |
| `LLM_FALLBACK_MODEL` | No | Used when the primary fails / hits quota. Default `groq/meta-llama/llama-4-scout-17b-16e-instruct`. Empty string disables the fallback chain. |
| `GEMINI_API_KEY` | No | Only needed if a `gemini/*` model is configured. The Gemini path exists in code but is not used by default — see the write-up below. |
| `BACKEND_PORT` | No | Defaults to 8000. |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` / `ERROR`. Default `INFO`. |

## Folder structure

See `docs/ARCHITECTURE.md` for the full breakdown of every folder and file.

## Deployment

Backend deploys to Hugging Face Spaces (Docker SDK). See `docs/DEPLOYMENT.md`.

## Assignment write-up

### Q1 — What did you embed vs query, and why that split?

Only **NIST SP 800-53 Rev. 5** (~1,189 controls) gets embedded into the vector store. Everything else — assets, vulnerabilities, threat intel, business services, CISA KEV — stays in pandas and is queried with exact joins on `cve_id`, `asset_id`, and `business_service`.

The rule I followed: **embed where the value is semantic, join where the value is identity.** NIST control prose ("the organization employs flaw remediation processes…") is paraphrased natural language — a risk like "unpatched VPN gateway" needs *semantic* similarity to surface SI-2 (Flaw Remediation). CVE IDs and asset IDs are unique strings — embeddings would be strictly worse than a hash join, and would also corrupt the cosine-similarity space with high-cardinality noise.

The retrieval pipeline reflects this:
1. **Score** in pandas (six structured signals: CVSS, internet exposure, active exploit, threat-intel match, business criticality, missing controls).
2. **Build a query string** per top-N risk from the structured fields (CVE description, asset role, exposure flags).
3. **RAG against NIST only** — multi-query expansion fans out into ~6 sub-queries per risk, top-K per sub-query, deduped on `control_id`.
4. **LLM** receives the full structured evidence + retrieved NIST excerpts and writes the explanation.

This keeps the vector store small (~10 MB, committed to Git so HF Spaces doesn't rebuild on cold start) and makes the structured-data path debuggable — you can recreate any score by reading the CSVs, no embeddings involved.

### Q2 — Three specific failure modes, and how each degrades

I designed for three failure modes I consider load-bearing in a daily-ingest demo:

| Failure | What actually breaks | Degradation |
|---|---|---|
| **CISA KEV lag** | KEV is a *list of known-exploited* CVEs, not a real-time exploit feed. A zero-day under active exploit may be in the wild for days before KEV adds it. | The "active exploit" signal under-fires for fresh CVEs. Partially mitigated by the threat-intel signal, which catches actor-attributed exploitation even when KEV hasn't ratified it yet. Honest exposure: brand-new ITW activity can be silently underweighted. |
| **Threat-intel matching is string-equality** | `threat_intel.target_technologies` is matched against `assets.platform` / `assets.role` via case-folded `in` checks. A typo, locale variant, or new product name (`"FortiOS 7.4"` vs `"FortiGate VPN"`) drops the match. | The "threat intel match" signal goes to zero for that pair, so the LLM also stops citing the actor + campaign — the risk still ranks via CVSS + exposure but loses the narrative. Fix path: fuzzy-match or an embedded technology taxonomy. |
| **Top-K RAG retrieval blind spots** | Multi-query expansion helps, but if the controls families that are most operationally relevant (e.g. SI-2 *Flaw Remediation* for a missing-patch finding) score below the top-K for every sub-query, they never reach the LLM. | The explanation is still grounded — it cites whatever NIST excerpts did surface (often SA-family development controls) — but it can miss the most actionable guidance. Mitigation today: cap excerpt length so the LLM gets *more* distinct controls within budget; longer-term, re-rank candidates by control-family priors for the failure category. |

Other failure modes are handled defensively but aren't the headline risks:
- **LLM call fails** (no API key, rate limit, network error) → falls back to `_rule_based_explanation()` so the API still returns explanations.
- **Vector store empty** → caught in `orchestrator._retrieve_nist_controls`; the risk gets an empty `nist_controls` list and the LLM prompt tells the model to speak only to scoring evidence so it doesn't hallucinate control IDs.
- **Bad CSV uploaded** → schema validation runs *before* the file is written, the previous version is preserved, the route returns 400 with the validation error. No partial state.

### Q3 — One thing to change with another day: decouple the LLM from `/risks/top`

Right now `/risks/top` runs the LLM for **every** ranked risk inline — score → retrieve → LLM → return. With `top_n=5` that's 5 LLM calls on the request's critical path before the UI sees anything, which is why the response can take 10–20 seconds and why a single rate-limit hit degrades the whole page.

The change I'd ship next: **make `/risks/top` return scoring + retrieval only, and add a separate `/risks/{id}/explanation` endpoint that the frontend calls per card on demand (or lazily on expander open).** Concretely:

- `/risks/top` stays cacheable, deterministic, and fast (no LLM in the loop).
- Each card on the frontend renders immediately with the structured evidence + NIST excerpts; the "Why this ranks here" expander triggers `/risks/{id}/explanation` only when the user opens it.
- Explanations get cached per-risk in memory (key = `risk_id + evidence_hash`) so re-opens are free.
- Rate-limit failures become *card-local* — one card falls back to the rule-based template, the rest of the page is unaffected.

This also makes the prompt-cost math cleaner: today we burn 5 explanations whether the user reads any of them or not. After the change, we pay only for what's actually read, and the heavy-tail of "user only looks at the top 1-2 risks" stops costing 5× quota.
