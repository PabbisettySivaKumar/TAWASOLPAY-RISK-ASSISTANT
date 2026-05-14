---
title: TawasolPay Risk Assistant
emoji: 🛡️
colorFrom: red
colorTo: gray
sdk: streamlit
app_file: app.py
pinned: false
license: mit
short_description: Streamlit UI — top-N cyber risks + NIST guidance.
---

# TawasolPay Risk Assistant — Frontend

Streamlit UI for the FastAPI backend. Renders the top-N ranked risks as scannable cards with NIST 800-53 guidance, threat intel matches, and the LLM-generated explanation.

## Live demo

| Surface | URL |
|---|---|
| Frontend (this app) | https://itspsk-tawasolpay-frontend.hf.space |
| Backend             | https://itspsk-tawasolpay-backend.hf.space |

> **Deployed on Hugging Face Spaces:** this folder is pushed as-is to a Streamlit Space. The only required Space variable is `BACKEND_URL`, pointing at the deployed backend Space (e.g. `https://<your-user>-tawasolpay-backend.hf.space`).

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

# 4. Point the UI at a backend (see Configuration below)
cp .env.example .env
# Edit .env and set BACKEND_URL to your local or deployed backend

# 5. Run
streamlit run app.py
```

Then open `http://localhost:8501`.

The sidebar shows the resolved backend URL as a read-only caption — there is no input widget, by design (an editable widget auto-fired `/risks/top` on every keystroke and burned LLM quota). To change the backend, edit `.env` and restart Streamlit.

## Configuration

The frontend resolves the backend URL from a single source: the `BACKEND_URL` environment variable.

- **Local dev:** create `frontend/.env` from `.env.example` and set `BACKEND_URL=http://localhost:8000` (or the deployed Space URL if you want to test against the live backend). `app.py` loads it via `python-dotenv` at startup.
- **Hugging Face Space:** add `BACKEND_URL` to the Space's **Variables** panel (or Secrets — either works, both inject as env vars). No `.env` file ships in deploy.
- **Fallback:** if `BACKEND_URL` is unset entirely, `app.py` defaults to the deployed backend Space URL so the cloned repo "just works" against the live demo.

This project uses `.env` (not `.streamlit/secrets.toml`) on purpose — the backend already uses `.env` via pydantic-settings, so both services follow the same pattern.

## Deployment to Hugging Face Spaces

Two-Space setup:

| Space | SDK | What it runs |
|---|---|---|
| `…-backend` | Docker | FastAPI + ChromaDB |
| `…-frontend` | Streamlit | This UI |

The frontend Space needs only:

- `app.py` (this file)
- `requirements.txt` (must include `python-dotenv`)
- `.streamlit/config.toml`
- The `BACKEND_URL` env var (Variables or Secrets panel) pointing at the backend Space's public URL

Streamlit Spaces auto-detect `app.py` and `requirements.txt` — no Dockerfile needed. The Space's Variables/Secrets are injected as process env vars, so the same `os.getenv("BACKEND_URL")` call works in local dev (reading from `.env`) and in deploy (reading from the Space panel).

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
  - Read-only caption showing the resolved backend URL (configured via `.env` / Space env vars — not editable in the UI)
  - Top-N slider (3–10)
  - "Load top risks" / "Reload top risks" button — `/risks/top` is **never** auto-called; the user clicks to fetch (button-gate keeps LLM quota under control)
  - "Refresh backend caches" button — calls `POST /data/refresh`, then clears the frontend's `@st.cache_data` and pops `top_data` from `session_state` so the next "Load top risks" pulls truly fresh data
  - Single-risk lookup by ID (e.g. `V-2019`)

## Performance / quota notes

- **Button-gate.** `/risks/top` is never called on widget rerun. Clicking the slider, switching tabs, or any other Streamlit rerun does not re-fetch — the user must explicitly click "Load top risks". This is deliberate: the original implementation auto-fired the endpoint on every rerun and burned 5 LLM calls per UI interaction.
- **Cache TTL.** `_fetch_top_cached` and `_fetch_risk_cached` are decorated with `@st.cache_data(ttl=1800)`. Re-fetching the same `(backend, top_n)` within 30 minutes is free; the cache is also invalidated whenever the resolved backend URL changes between reruns.
