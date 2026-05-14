# TawasolPay Risk Assistant — Frontend

Streamlit UI for the FastAPI backend. Renders the top-N ranked risks as scannable cards with NIST 800-53 guidance, threat intel matches, and the LLM-generated explanation.

This is the "human-readable" surface the assignment asks for in Thing 3 — a technical manager can scan it and act on it without further processing.

## Quick start (local)

```bash
# 1. From the project root:
cd frontend

# 2. Optional but recommended — separate venv from the backend
python -m venv venv
source venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. Run (defaults to backend at http://localhost:8000)
streamlit run app.py
```

Then open `http://localhost:8501`.

The backend URL is editable in the sidebar — leave it as `http://localhost:8000` for local dev, set to the deployed Hugging Face Space URL when running the deployed frontend.

## Configuration

The frontend resolves the backend URL in this order:

1. The sidebar input (highest priority — overrides everything for the current session)
2. The `TAWASOLPAY_BACKEND_URL` environment variable
3. `st.secrets["BACKEND_URL"]` (set in `.streamlit/secrets.toml` locally, or in the HF Space's `Secrets` panel for deploy)
4. `http://localhost:8000`

For Hugging Face Spaces deploy, add this to the Space's `Secrets` panel:

```
BACKEND_URL = "https://your-username-tawasolpay-backend.hf.space"
```

## Deployment to Hugging Face Spaces

Two-Space setup:

| Space | SDK | What it runs |
|---|---|---|
| `…-backend` | Docker | FastAPI + ChromaDB |
| `…-frontend` | Streamlit | This UI |

The frontend Space needs only:

- `app.py` (this file)
- `requirements.txt`
- `.streamlit/config.toml`
- The `BACKEND_URL` secret pointing at the backend Space's public URL

Streamlit Spaces auto-detect `app.py` and `requirements.txt` — no Dockerfile needed.

## What the UI shows

- **Header**: title + the system's one-line elevator pitch
- **Per-risk card** (one per row):
  - Rank chip + risk-score color (🔴 ≥80, 🟠 60–79, 🟡 <60)
  - CVE + CVSS
  - Asset name, asset ID, environment
  - Risk score metric
  - Status badges: 🌐 internet-exposed, ⚠️ active exploit, 💀 ransomware-linked
  - Business service
  - Threat intel match (actor + campaign), if any
  - **"Why this ranks here"** expander — the LLM explanation grounded in retrieved NIST excerpts
  - **"NIST 800-53 guidance"** expander — retrieved controls with similarity scores and excerpts
- **Sidebar**:
  - Backend URL input
  - Top-N slider (3–10)
  - "Refresh backend caches" button (calls `POST /data/refresh`)
  - Single-risk lookup by ID (e.g. `V-2019`)
