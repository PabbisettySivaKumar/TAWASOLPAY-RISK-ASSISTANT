# syntax=docker/dockerfile:1
FROM python:3.11-slim

# No build-essential needed — chromadb, hnswlib, torch (CPU), sentence-transformers,
# numpy, pandas all ship prebuilt manylinux wheels for both amd64 and aarch64.

# HF Spaces runs containers as a non-root user. Create one with a writable HOME
# so sentence-transformers / HF Hub caches land somewhere we can write.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/user/.cache/huggingface \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

COPY --chown=user:user requirements.txt .

# Install CPU-only torch FIRST so the resolver doesn't pull the ~900 MB of
# CUDA wheels that sentence-transformers' default torch dep would otherwise
# drag in. HF Spaces free tier is CPU-only — GPU wheels are pure bloat.
RUN pip install --no-cache-dir --user --upgrade \
        --index-url https://download.pytorch.org/whl/cpu \
        torch \
 && pip install --no-cache-dir --user --upgrade -r requirements.txt

COPY --chown=user:user . .

EXPOSE 7860

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
