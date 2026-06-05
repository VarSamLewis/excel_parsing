"""Shared OpenAI client factory and retry utilities."""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import OpenAI

from backend.config import settings
from backend.log_store import write_llm_usage

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # seconds


def get_client() -> OpenAI:
    """Create OpenAI client; args: none; returns: OpenAI."""
    if settings.openai_base_url:
        return OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return OpenAI(api_key=settings.openai_api_key)


def call_with_retry(client: OpenAI, step: str, run_id: str = "", **kwargs: Any) -> str:
    """Call the OpenAI API with retry logic for transient errors; args: client (OpenAI), step (str), run_id (str), **kwargs (Any); returns: str."""
    start: float = time.perf_counter()

    for attempt in range(1 + MAX_RETRIES):
        try:
            response = client.chat.completions.create(**kwargs)
            usage: Any = getattr(response, "usage", None)
            finish_reason: str | None = None
            if response.choices:
                finish_reason = response.choices[0].finish_reason
            write_llm_usage(
                step=step,
                model=str(kwargs.get("model", "")),
                run_id=run_id,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
                finish_reason=finish_reason,
                latency_ms=(time.perf_counter() - start) * 1000,
                retries=attempt,
            )
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            status_code = getattr(e, "status_code", None)

            is_retryable = (
                status_code in (429, 500, 502, 503, 504)
                or "rate limit" in error_str.lower()
                or "connection" in error_str.lower()
                or "timeout" in error_str.lower()
            )

            if not is_retryable or attempt >= MAX_RETRIES:
                write_llm_usage(
                    step=step,
                    model=str(kwargs.get("model", "")),
                    run_id=run_id,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    retries=attempt,
                    error=str(e),
                )
                raise

            delay = RETRY_BASE_DELAY * (2**attempt)
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                1 + MAX_RETRIES,
                delay,
                e,
            )
            time.sleep(delay)

    raise RuntimeError(f"LLM call failed after {1 + MAX_RETRIES} attempts")
