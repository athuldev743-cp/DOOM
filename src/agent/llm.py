# src/agent/llm.py

import os
from dotenv import load_dotenv
from langfuse import Langfuse

from src.agent.llm_providers.openai_compatible import OpenAICompatibleProvider
from src.agent.llm_providers.groq_provider import GroqProvider
from src.agent.llm_fallback import LLMFallbackChain

load_dotenv()


langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
)


# ============================================================
# MODEL LISTS
# ============================================================

GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "allam-2-7b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "groq/compound-mini",
    "groq/compound",
]


GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]


OPENAI_MODELS = [
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4o-mini",
]


OPENROUTER_MODELS = [
    "nvidia/nemotron-nano-9b-v2:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-4b:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
]


# ============================================================
# FALLBACK CHAIN
#
# Priority:
#
# 1. Groq
# 2. Gemini
# 3. OpenAI
# 4. OpenRouter
#
# ============================================================

_chain = LLMFallbackChain(
    providers=[
        # ----------------------------------------------------
        # 1. GROQ
        # ----------------------------------------------------
        GroqProvider(),

        # ----------------------------------------------------
        # 2. GEMINI
        # ----------------------------------------------------
        OpenAICompatibleProvider(
            "gemini",
            "GEMINI_API_KEY",
            GEMINI_MODELS,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ),

        # ----------------------------------------------------
        # 3. OPENAI
        # ----------------------------------------------------
        OpenAICompatibleProvider(
            "openai",
            "OPENAI_API_KEY",
            OPENAI_MODELS,
        ),

        # ----------------------------------------------------
        # 4. OPENROUTER
        # ----------------------------------------------------
        OpenAICompatibleProvider(
            "openrouter",
            "OPENROUTER_API_KEY",
            OPENROUTER_MODELS,
            base_url="https://openrouter.ai/api/v1",
            default_timeout=30,
        ),
    ],
    langfuse_client=langfuse,
    fail_message=(
        "All models (Groq, Gemini, OpenAI, and OpenRouter) "
        "are currently busy."
    ),
)


async def chat(messages: list) -> str:
    return await _chain.chat(messages)