# Deployment — Hugging Face Spaces

The project is live as **two Hugging Face Spaces** under the `itspsk` account.

| Space | SDK | URL | Settings |
|---|---|---|---|
| `itspsk/tawasolpay-backend`  | Docker    | https://itspsk-tawasolpay-backend.hf.space  | https://huggingface.co/spaces/itspsk/tawasolpay-backend/settings  |
| `itspsk/tawasolpay-frontend` | Streamlit | https://itspsk-tawasolpay-frontend.hf.space | https://huggingface.co/spaces/itspsk/tawasolpay-frontend/settings |

This doc covers how both Spaces are configured and how to redeploy / maintain them.

## Why Hugging Face Spaces

- **16 GB RAM** on the free tier — handles sentence-transformers + ChromaDB without OOM
- **Persistent filesystem** — ChromaDB survives restarts
- **Free** — no credit card
- **Public URL** — `https://<username>-<spacename>.hf.space`
- **Designed for AI workloads** — won't surprise us with cold-start quirks the way generic PaaS hosts do

---

## Backend Space (Docker)

### Files on the Space

What ships:

- Everything in `backend/` **except** `.env`, `venv/`, `__pycache__/`, etc. (covered by `.gitignore`)
- `data/raw/` — the 5 assignment CSVs + threat report (so the demo works on cold-clone)
- `data/reference/` — pre-downloaded CISA KEV + NIST 800-53 (so the Space doesn't redownload on every boot)
- `data/chroma_db/` — pre-built vector store (so the app starts fast — see *Git LFS* below)

### HF Space frontmatter (top of `backend/README.md`)

```yaml
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
```

`app_port: 7860` matters — HF Spaces require the container to listen on 7860. The Dockerfile's `CMD` reflects this.

### The Dockerfile (actual, not a sketch)

The real `Dockerfile` in the repo does three non-obvious things:

1. **Runs as a non-root user** (`user`, uid 1000). HF Spaces enforce this; running as root will get the container killed. `HF_HOME` is pointed at a writable cache dir under `/home/user/.cache/huggingface` so sentence-transformers and the HF Hub client can cache downloads.
2. **Installs CPU-only PyTorch from the dedicated index** before pip-resolving the rest of `requirements.txt`. Without this, sentence-transformers pulls the CUDA torch wheels (~900 MB of pure bloat on a CPU-only Space).
3. **Listens on 7860**, not 8000. Local dev uses 8000 (`uvicorn ... --port 8000`); the Space uses 7860.

If you need to see the current version, read `backend/Dockerfile` directly — keeping a sketch in sync with the real thing was a maintenance burden the last time around.

### Environment variables / Secrets

Set these in the backend Space's **Variables and secrets** panel (Settings → Variables and secrets). Anything marked **Secret** is encrypted; **Variable** is plaintext and visible.

| Key | Required | Kind | Description |
|---|---|---|---|
| `GROQ_API_KEY`          | Yes | Secret   | Groq Cloud key — https://console.groq.com/keys |
| `LLM_PRIMARY_MODEL`     | No  | Variable | LiteLLM model id, e.g. `groq/llama-3.1-8b-instant` (the default if unset) |
| `LLM_FALLBACK_MODEL`    | No  | Variable | Used when the primary errors / hits quota, e.g. `groq/meta-llama/llama-4-scout-17b-16e-instruct`. Empty string disables fallback |
| `GEMINI_API_KEY`        | No  | Secret   | Only needed if a `gemini/*` model is configured. Currently unused — Gemini path exists in code but is not in the active rotation |
| `API_KEY`               | No  | Secret   | If set, every `POST /data/external/refresh/*` route requires `X-API-Key: <value>`. If empty (default), refresh routes are open |
| `REFRESH_COOLDOWN_SECONDS` | No | Variable | Min seconds between refreshes of the same external source. Default `300` (5 min) |
| `LOG_LEVEL`             | No  | Variable | `DEBUG` / `INFO` / `WARNING` / `ERROR`. Default `INFO` |
| `BACKEND_PORT`          | No  | Variable | Only meaningful for local dev — the Dockerfile hard-codes 7860 |

After changing a Secret, **restart the Space** (Settings → "Restart this Space") — env vars are only read at container boot.

### Git LFS

The backend Space repo uses **Git LFS** for two file globs in `data/chroma_db/`:

- `chroma.sqlite3` (the vector store's SQLite backing file)
- `*.bin` (HNSW index files)

Practical consequences:

- **First clone:** `git lfs install` once on your machine, then `git clone …`. LFS will pull the binaries automatically.
- **Text-only updates:** if you only need to push code changes and don't want to wait for LFS to pull the binaries, clone with `GIT_LFS_SKIP_SMUDGE=1 git clone …`. The LFS pointers stay intact, the actual binaries stay on the Space — push works, and you didn't download ~30 MB you weren't going to touch.
- **Don't `git add` a new `.bin` or `.sqlite3` without LFS active** — you'll bloat the regular git history and the push will be rejected by HF's size limits.

---

## Frontend Space (Streamlit)

### Files on the Space

Only what's in `frontend/`:

- `app.py`
- `requirements.txt` (must include `python-dotenv`)
- `.streamlit/config.toml`
- `README.md` with Streamlit frontmatter
- `.env.example` (committed); the real `.env` is **not** committed — its values come from the Space's env var panel instead

### HF Space frontmatter (top of `frontend/README.md`)

```yaml
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
```

No Dockerfile is needed — Streamlit Spaces auto-detect `app_file` and run `streamlit run` on it.

### Environment variables

| Key | Required | Description |
|---|---|---|
| `BACKEND_URL` | Yes (in practice) | The deployed backend Space URL, e.g. `https://itspsk-tawasolpay-backend.hf.space`. If unset, `app.py` falls back to this exact URL so the cloned repo "just works" against the live demo |

This goes in the frontend Space's **Variables** panel (Secrets also works — they're both injected as env vars). The same `os.getenv("BACKEND_URL")` call in `app.py` reads from `.env` locally (via `python-dotenv`) and from the Space env in deploy.

---

## Redeploying

There is no permanent local clone of either Space — the repo of record is the GitHub monorepo at `https://github.com/PabbisettySivaKumar/TAWASOLPAY-RISK-ASSISTANT`. The standard push flow is:

```bash
# Backend
GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/spaces/itspsk/tawasolpay-backend /tmp/hf-backend
cp -R /Users/sivakumar/Downloads/tawasolpay-risk-assistant/backend/* /tmp/hf-backend/
cd /tmp/hf-backend
git add -A
git commit -m "deploy: <what changed>"
git push

# Frontend
git clone https://huggingface.co/spaces/itspsk/tawasolpay-frontend /tmp/hf-frontend
cp -R /Users/sivakumar/Downloads/tawasolpay-risk-assistant/frontend/* /tmp/hf-frontend/
cd /tmp/hf-frontend
git add -A
git commit -m "deploy: <what changed>"
git push
```

The Space rebuilds automatically on push. The backend rebuild typically takes 3–5 min (pip install + image build); the frontend is ~30 s (no Docker layer).

### Redeploy checklist

- [ ] Local tests / smoke checks pass
- [ ] `data/raw/` is in the state you want the Space to ship with
- [ ] If you changed NIST chunking / embedding model, rerun `python scripts/setup_data.py` so the committed `data/chroma_db/` matches the new code
- [ ] Push to GitHub first, then to each Space (keeps git history in sync)
- [ ] Watch the Space's *Build* log until it goes green
- [ ] `curl https://itspsk-tawasolpay-backend.hf.space/` returns `{"status":"ok",...}`
- [ ] Open the frontend Space, click **Load top risks**, verify a real response (5 cards with NIST guidance + explanation)

### Rollback

Each Space is its own git repo. If a deploy is bad:

```bash
cd /tmp/hf-backend            # or /tmp/hf-frontend
git log                       # find the last good SHA
git reset --hard <good-sha>
git push --force
```

The Space rebuilds from the rolled-back state on push. This is fine for a personal Space; on a team Space you'd coordinate first.

---

## Performance on the free tier

- **Cold start:** ~30 s (sentence-transformers loads MiniLM, ChromaDB opens the persisted collection)
- **Warm `/risks/top` (top_n=5):** dominated by **5 sequential LLM calls** — typically 6–12 s end-to-end on Groq's `llama-3.1-8b-instant`. The structured scoring + RAG retrieval take well under 1 s combined; the LLM is the bottleneck
- **Per-call prompt cost:** ~366 input tokens (NIST excerpts are capped at 250 chars in `pipeline/orchestrator.py:_format_nist_excerpts` — was 700 originally; the cap cuts input tokens ~60% without hurting explanation quality)
- **Memory at idle:** ~600 MB
- **Memory under load:** ~1.2 GB

If response time becomes a problem, the obvious fix is the one called out in `backend/README.md`'s Q3: decouple the LLM from `/risks/top` and serve explanations on-demand per card, so the page renders immediately and each card pays its own LLM cost only when the user opens it.
