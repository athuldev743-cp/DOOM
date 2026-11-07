# src/agent/llm_providers/groq_provider.py

import os

from groq import Groq

from .base import LLMProvider


# ============================================================
# GROQ MODELS
# ============================================================

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

class GroqProvider(LLMProvider):
    """Groq provider using the official Groq SDK."""

    name = "groq"

    def __init__(
        self,
        model_list: list[str] | None = None,
        default_timeout: int = 15,
    ):
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQAPI_KEY") or "dummy"
        self._client = Groq(
            api_key=api_key,
            max_retries=0,  # our own fallback chain is the sole retry controller
        )

        self._models = model_list or GROQ_MODELS
        self._default_timeout = default_timeout

    def models(self) -> list[str]:
        return self._models

    def complete(
        self,
        model: str,
        messages: list,
        timeout: int | None = None,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=timeout or self._default_timeout,
        )

        return response.choices[0].message.content
