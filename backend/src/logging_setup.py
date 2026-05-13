"""
Logging configuration for the backend.

Called once from src/api/main.py. Uses settings.LOG_LEVEL (default INFO).
Format is concise: `LEVEL [module] message` — readable when interleaved
with uvicorn's request logs.

Third-party loggers we keep quiet (or silent):
    - chromadb.telemetry : CRITICAL (posthog version-mismatch spam)
    - LiteLLM            : WARNING (router routing chatter at INFO)
    - httpx / httpcore   : WARNING (gemini/groq request lines at INFO)
"""

import logging

from src.config import settings


def configure_logging() -> None:
    """Configure root logger and silence noisy third-party loggers."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(levelname)-5s [%(name)s] %(message)s",
        force=True,
    )

    logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
