# src/agent/llm_providers/groq_provider.py
import os
from groq import Groq
from .base import LLMProvider


class GroqProvider(LLMProvider):
    """Groq uses its own SDK, not the OpenAI client, so it gets its own
    thin adapter — but implements the same LLMProvider interface."""

    name = "groq"

    def __init__(self, model_list: list[str], default_timeout: int = 15):
        self._client = Groq(api_key=os.getenv("GROQ_API_KEY") or "dummy")
        self._models = model_list
        self._default_timeout = default_timeout

    def models(self) -> list[str]:
        return self._models

    def complete(self, model: str, messages: list, timeout: int | None = None) -> str:
        response = self._client.chat.completions.create(
            model=model, messages=messages, timeout=timeout or self._default_timeout
        )
        return response.choices[0].message.content