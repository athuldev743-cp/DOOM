# src/agent/llm_providers/groq_provider.py

import os

from groq import Groq

from .base import LLMProvider


# ============================================================
# GROQ MODELS
# ============================================================

GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "allam-2-7b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "groq/compound-mini",
    "groq/compound",
]

# Free-tier Tokens-Per-Minute ceilings, from
# https://console.groq.com/docs/rate-limits (verified 2026-09-17).
# A single request whose estimated token count exceeds a model's TPM
# ceiling will ALWAYS fail (413/400) on the free tier — there's no
# point making the network call. We skip those instantly instead.
#
# NOTE: groq/compound and groq/compound-mini are NOT listed here even
# though Groq's docs show them at 70K TPM (generous) — they still
# failed with "Request Entity Too Large" in real testing, so
# something else (likely a separate context/payload cap not shown on
# that page) is limiting them. Rather than guess a number, we leave
# them unguarded — they'll still go to the network and fail/succeed
# as before until we learn their real limit.
MODEL_TPM_LIMITS = {
    "qwen/qwen3.8-27b": 8_000,
    "openai/gpt-oss-20b": 8_000,
    "openai/gpt-oss-120b": 8_000,
}

# TPM covers input + output tokens together, so reserve some budget
# for the model's response rather than using 100% of the ceiling on
# input alone.
OUTPUT_TOKEN_RESERVE = 1_000


def _estimate_tokens(messages: list) -> int:
    """
    Rough chars/4 estimate of token count. Not exact, but good enough
    to skip requests that are guaranteed to fail — false negatives
    here just mean an unnecessary network call, not a wrong answer.
    """
    total_chars = sum(
        len(str(m.get("content", ""))) for m in messages
    )
    return total_chars // 4


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
        limit = MODEL_TPM_LIMITS.get(model)

        if limit is not None:
            estimated = _estimate_tokens(messages)

            if estimated + OUTPUT_TOKEN_RESERVE > limit:
                raise ValueError(
                    f"Skipped {model}: ~{estimated} estimated input "
                    f"tokens + {OUTPUT_TOKEN_RESERVE} output reserve "
                    f"exceeds its {limit} TPM free-tier limit — "
                    f"would guaranteed-fail on the network."
                )

        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=timeout or self._default_timeout,
        )

        return response.choices[0].message.content
