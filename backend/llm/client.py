"""Shared OpenAI client factory; args: none; returns: OpenAI."""

from __future__ import annotations

from openai import OpenAI

from backend.config import settings


def get_client() -> OpenAI:
    """Create OpenAI client; args: none; returns: OpenAI."""
    if settings.openai_base_url:
        return OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return OpenAI(api_key=settings.openai_api_key)
