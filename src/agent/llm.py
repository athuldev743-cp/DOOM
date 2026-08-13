import os
import time
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv
from langfuse import Langfuse

load_dotenv()

# --- Langfuse client (v4 API, confirmed via introspection) ---
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
)

# --- Clients Setup ---

gemini_client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "dummy",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or "dummy"
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY") or "dummy")

openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY") or "dummy"
)

# --- Model Lists ---

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-1.5-flash"
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

OPENROUTER_MODELS = [
    "nvidia/nemotron-nano-9b-v2:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-4b:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
]


def _usage_dict(response):
    usage = getattr(response, "usage", None)
    if not usage:
        return None
    return {
        "input": getattr(usage, "prompt_tokens", None),
        "output": getattr(usage, "completion_tokens", None),
    }


def _try_provider(provider: str, model: str, call_fn):
    """Runs one provider/model attempt as a Langfuse generation observation nested
    under the currently active span. Returns content on success, None on failure."""
    start = time.perf_counter()
    with langfuse.start_as_current_observation(
        name=f"{provider}:{model}",
        as_type="generation",
        model=model,
    ) as gen:
        try:
            response = call_fn()
            content = response.choices[0].message.content
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            gen.update(
                output=content,
                usage_details=_usage_dict(response),
                metadata={"duration_ms": duration_ms},
            )
            return content
        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            gen.update(level="ERROR", status_message=str(e)[:200], metadata={"duration_ms": duration_ms})
            print(f"[LLM] {provider} {model} failed: {str(e)[:60]}")
            return None


async def chat(messages: list) -> str:
    with langfuse.start_as_current_observation(
        name="doom-chat",
        as_type="span",
        input={"messages": messages[-3:]},  # last few turns only — keeps traces light
    ) as root_span:

        # --- PHASE 1: GEMINI ---
        for model in GEMINI_MODELS:
            print(f"[LLM] Gemini: {model}")
            content = _try_provider(
                "gemini", model,
                lambda m=model: gemini_client.chat.completions.create(model=m, messages=messages, timeout=20)
            )
            if content:
                print("[LLM] ✓ Gemini success")
                root_span.update(output=content, metadata={"served_by": f"gemini:{model}"})
                langfuse.flush()
                return content

        # --- PHASE 1.5: OPENAI FALLBACK ---
        print("[LLM] Gemini failed. Falling back to OpenAI GPT-5 Nano...")
        content = _try_provider(
            "openai", "gpt-5-nano",
            lambda: openai_client.chat.completions.create(model="gpt-5-nano", messages=messages, timeout=15)
        )
        if content:
            print("[LLM] ✓ OpenAI GPT-5 Nano success")
            root_span.update(output=content, metadata={"served_by": "openai:gpt-5-nano"})
            langfuse.flush()
            return content

        # --- PHASE 2: GROQ ---
        print("[LLM] Falling back to Groq...")
        for model in GROQ_MODELS:
            print(f"[LLM] Groq: {model}")
            content = _try_provider(
                "groq", model,
                lambda m=model: groq_client.chat.completions.create(model=m, messages=messages, timeout=15)
            )
            if content:
                print("[LLM] ✓ Groq success")
                root_span.update(output=content, metadata={"served_by": f"groq:{model}"})
                langfuse.flush()
                return content

        # --- PHASE 3: OPENROUTER (FINAL FALLBACK) ---
        print("[LLM] Falling back to OpenRouter...")
        for model in OPENROUTER_MODELS:
            print(f"[LLM] OpenRouter: {model}")
            content = _try_provider(
                "openrouter", model,
                lambda m=model: openrouter_client.chat.completions.create(model=m, messages=messages, timeout=30)
            )
            if content:
                print("[LLM] ✓ OpenRouter success")
                root_span.update(output=content, metadata={"served_by": f"openrouter:{model}"})
                langfuse.flush()
                return content

        fail_msg = "All models (Gemini, OpenAI, Groq, and OpenRouter) are currently busy."
        root_span.update(output=fail_msg, metadata={"served_by": "none", "total_failure": True})
        langfuse.flush()
        return fail_msg