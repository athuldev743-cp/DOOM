# src/agent/llm_providers/openai_compatible.py
import os
from openai import OpenAI
from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Covers Gemini, OpenAI, Grok, and OpenRouter — all speak the OpenAI
    chat-completions shape, differing only in base_url/api key/model list."""

    def __init__(self, name: str, api_key_env: str, model_list: list[str],
                 base_url: str | None = None, default_timeout: int = 20):
        self.name = name
        self._client = OpenAI(api_key=os.getenv(api_key_env) or "dummy", base_url=base_url)
        self._models = model_list
        self._default_timeout = default_timeout

    def models(self) -> list[str]:
        return self._models

    def complete(self, model: str, messages: list, timeout: int | None = None) -> str:
        response = self._client.chat.completions.create(
            model=model, messages=messages, timeout=timeout or self._default_timeout
        )
        return response.choices[0].message.content