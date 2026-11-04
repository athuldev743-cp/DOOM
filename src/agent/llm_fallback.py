# src/agent/llm_fallback.py
import asyncio
import os
import time

from src.agent.llm_providers.base import LLMProvider


class LLMFallbackChain:
    """Bounded, non-blocking fallback across providers and their models."""

    def __init__(
        self,
        providers: list[LLMProvider],
        langfuse_client,
        fail_message: str,
        total_timeout_seconds: float | None = None,
        attempt_timeout_seconds: int | None = None,
    ):
        self._providers = providers
        self._langfuse = langfuse_client
        self._fail_message = fail_message
        self._total_timeout = total_timeout_seconds or float(
            os.getenv("LLM_TOTAL_TIMEOUT_SECONDS", "45")
        )
        self._attempt_timeout = attempt_timeout_seconds or int(
            os.getenv("LLM_ATTEMPT_TIMEOUT_SECONDS", "8")
        )

    async def chat(self, messages: list) -> str:
        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._total_timeout
        attempted = 0
        timed_out = False

        with self._langfuse.start_as_current_observation(
            name="doom-chat",
            as_type="span",
            input={"messages": messages[-3:]},
        ) as root_span:
            for provider in self._providers:
                for model in provider.models():
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        timed_out = True
                        break

                    attempt_timeout = max(
                        1, min(self._attempt_timeout, int(remaining))
                    )
                    attempted += 1
                    print(
                        f"[LLM] {provider.name}: {model} "
                        f"(timeout={attempt_timeout}s, remaining={remaining:.1f}s)"
                    )

                    try:
                        content = await asyncio.wait_for(
                            asyncio.to_thread(
                                self._try, provider, model, messages, attempt_timeout
                            ),
                            timeout=attempt_timeout + 0.5,
                        )
                    except asyncio.TimeoutError:
                        content = None
                        print(f"[LLM] {provider.name} {model} timed out")

                    if content:
                        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
                        print(f"[LLM] ✓ {provider.name} success ({elapsed_ms}ms)")
                        root_span.update(
                            output=content,
                            metadata={
                                "served_by": f"{provider.name}:{model}",
                                "attempted_models": attempted,
                                "elapsed_ms": elapsed_ms,
                                "timeout_budget_seconds": self._total_timeout,
                            },
                        )
                        await asyncio.to_thread(self._langfuse.flush)
                        return content

                if timed_out:
                    break

            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            root_span.update(
                output=self._fail_message,
                metadata={
                    "served_by": "none",
                    "total_failure": True,
                    "attempted_models": attempted,
                    "elapsed_ms": elapsed_ms,
                    "timeout_budget_seconds": self._total_timeout,
                    "budget_exhausted": timed_out or loop.time() >= deadline,
                },
            )
            await asyncio.to_thread(self._langfuse.flush)
            return self._fail_message

    def _try(
        self,
        provider: LLMProvider,
        model: str,
        messages: list,
        timeout: int,
    ) -> str | None:
        start = time.perf_counter()
        with self._langfuse.start_as_current_observation(
            name=f"{provider.name}:{model}",
            as_type="generation",
            model=model,
        ) as generation:
            try:
                content = provider.complete(model, messages, timeout=timeout)
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                generation.update(
                    output=content,
                    metadata={"duration_ms": duration_ms, "timeout_seconds": timeout},
                )
                return content
            except Exception as exc:
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                generation.update(
                    level="ERROR",
                    status_message=str(exc)[:200],
                    metadata={"duration_ms": duration_ms, "timeout_seconds": timeout},
                )
                print(
                    f"[LLM] {provider.name} {model} failed: {str(exc)[:100]}"
                )
                return None
