# src/agent/llm_providers/base.py
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """A single LLM provider: a client plus an ordered list of models to try."""

    name: str

    @abstractmethod
    def models(self) -> list[str]:
        """Ordered list of model ids to attempt for this provider, best first."""
        ...

    @abstractmethod
    def complete(self, model: str, messages: list, timeout: int) -> str:
        """Return the response text, or raise on failure."""
        ...