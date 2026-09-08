# src/agent/llm_fallback.py
import time
from src.agent.llm_providers.base import LLMProvider


class LLMFallbackChain:
    """Tries providers in the given order, and within each provider, its
    models in order. Adding/reordering providers never touches this class —
    that's the point (OCP): it depends only on the LLMProvider interface."""

    def __init__(self, providers: list[LLMProvider], langfuse_client, fail_message: str):
        self._providers = providers
        self._langfuse = langfuse_client
        self._fail_message = fail_message

    async def chat(self, messages: list) -> str:
        with self._langfuse.start_as_current_observation(
            name="doom-chat",
            as_type="span",
            input={"messages": messages[-3:]},
        ) as root_span:

            for provider in self._providers:
                for model in provider.models():
                    print(f"[LLM] {provider.name}: {model}")
                    content = self._try(provider, model, messages)
                    if content:
                        print(f"[LLM] ✓ {provider.name} success")
                        root_span.update(output=content, metadata={"served_by": f"{provider.name}:{model}"})
                        self._langfuse.flush()
                        return content

            root_span.update(output=self._fail_message, metadata={"served_by": "none", "total_failure": True})
            self._langfuse.flush()
            return self._fail_message

    def _try(self, provider: LLMProvider, model: str, messages: list) -> str | None:
        start = time.perf_counter()
        with self._langfuse.start_as_current_observation(
            name=f"{provider.name}:{model}", as_type="generation", model=model,
        ) as gen:
            try:
                content = provider.complete(model, messages)
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                gen.update(output=content, metadata={"duration_ms": duration_ms})
                return content
            except Exception as e:
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                gen.update(level="ERROR", status_message=str(e)[:200], metadata={"duration_ms": duration_ms})
                print(f"[LLM] {provider.name} {model} failed: {str(e)[:60]}")
                return None