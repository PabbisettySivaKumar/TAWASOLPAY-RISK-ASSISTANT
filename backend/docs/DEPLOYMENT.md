# Deploying the backend to Hugging Face Spaces

Backend deploys to **Hugging Face Spaces** using the **Docker SDK**.

## Why HF Spaces

- **16 GB RAM** on the free tier — handles sentence-transformers + ChromaDB without OOM
- **Persistent filesystem** — ChromaDB survives restarts
- **Free** — no credit card
- **Public URL** — `https://<username>-<spacename>.hf.space`
- **Designed for AI workloads** — won't surprise us with cold-start quirks the way generic PaaS hosts do

## Files needed at the repo root (when deploying)

When we eventually push the backend folder as its own Space, we'll add:

1. **`Dockerfile`** — instructs HF Spaces how to build and run the container
2. **`README.md`** with HF Spaces frontmatter:
   ```yaml
   ---
   title: TawasolPay Risk Assistant
   sdk: docker
   app_port: 8000
   ---
   ```

(These don't exist yet — we'll add them at the deployment step.)

## Sketch of the Dockerfile (for later)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Secrets

After creating the Space:

1. Go to Settings → Repository Secrets
2. Add:
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
3. Restart the Space

These will be injected as environment variables at runtime. `src/config.py` picks them up automatically.

## What gets committed to the Space repo

Everything in the `backend/` folder **except**:
- `.env` (real secrets — never commit)
- `venv/`, `__pycache__/`, etc. (covered by `.gitignore`)

What we explicitly DO commit:
- `data/raw/` — the assignment CSVs and threat report
- `data/reference/` — downloaded NIST/KEV (so we don't redownload on every boot)
- `data/chroma_db/` — prebuilt vector store (so the app starts fast)

## Deployment checklist (to use when we're ready)

- [ ] All code finished and tested locally
- [ ] `data/raw/` populated with assignment CSVs
- [ ] `python scripts/setup_data.py` run successfully (KEV + NIST + vector store built)
- [ ] `python run.py` works locally, `/risks/top` returns valid data
- [ ] `tests/` pass
- [ ] `Dockerfile` added
- [ ] HF Spaces frontmatter added to top of `README.md`
- [ ] Repo pushed to HF Spaces
- [ ] `GEMINI_API_KEY` and `GROQ_API_KEY` added as Repository Secrets in Space settings
- [ ] Public URL tested — `/docs` reachable, `/risks/top` returns a real response

## Expected performance on HF Spaces free tier

- Cold start: ~30 seconds (model loading)
- Warm `/risks/top`: ~5-15 seconds (one LLM call per top-5 risk = 5 calls)
- Memory at idle: ~600 MB
- Memory under load: ~1.2 GB
