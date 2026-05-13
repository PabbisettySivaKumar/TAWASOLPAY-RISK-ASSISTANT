"""
Single LLM access point for the whole backend.

Uses LiteLLM with built-in fallback:
    Primary  : Gemini 2.0 Flash (free tier — 1500 req/day)
    Fallback : Groq Llama 3.3 70B Versatile (free tier)

If Gemini hits a rate limit or errors, LiteLLM retries on Groq automatically.
Every other module imports `generate()` from here — no direct SDK calls anywhere.
"""

import logging
import os
import time

import litellm

from src.config import settings

# Configure LiteLLM with API keys from environment
os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY
os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY

# Quiet the "Give Feedback / Get Help" banner that LiteLLM prints on every
# transient provider error before falling through to the fallback model.
litellm.suppress_debug_info = True

logger = logging.getLogger(__name__)


def generate(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 600,
) -> str:
    """
    Generate a completion. Tries Gemini first, falls back to Groq on failure.

    Args:
        prompt: user message
        system: optional system message
        temperature: 0.0 (deterministic) to 1.0 (creative)
        max_tokens: response cap

    Returns:
        The generated text string.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    t = time.perf_counter()
    response = litellm.completion(
        model=settings.LLM_PRIMARY_MODEL,
        fallbacks=[settings.LLM_FALLBACK_MODEL],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    elapsed = time.perf_counter() - t

    served_by = getattr(response, "model", None) or "unknown"
    primary = settings.LLM_PRIMARY_MODEL.split("/", 1)[-1]
    used_fallback = primary not in served_by
    logger.info(
        "LLM call — model=%s fallback=%s tokens<=%d in %.0fms",
        served_by, used_fallback, max_tokens, elapsed * 1000,
    )
    return response.choices[0].message.content
