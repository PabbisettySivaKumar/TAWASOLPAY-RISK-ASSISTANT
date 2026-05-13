# TawasolPay Risk Assistant — Backend

FastAPI service that ingests TawasolPay's security data, scores risks, retrieves NIST 800-53 guidance via RAG, and exposes everything over HTTP.

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
