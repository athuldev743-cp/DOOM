import os
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

gemini_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or "dummy",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

GEMINI_MODELS = [
    "gemini-3-flash-preview", 
    "gemini-3.1-flash-lite-preview"
]

# Primary — Groq (fast, free)
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Fallback — OpenRouter
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

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

async def chat(messages: list) -> str:
    # --- PHASE 1: GEMINI (FIRST PRIORITY) ---
    for model in GEMINI_MODELS:
        try:
            print(f"[LLM] Gemini: {model}")
            response = gemini_client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=20
            )
            print(f"[LLM] ✓ Gemini success")
            return response.choices[0].message.content
        except Exception as e:
            print(f"[LLM] Gemini {model} failed: {str(e)[:60]}")

    # --- PHASE 2: GROQ (AFTER GEMINI FAILS) ---
    print("[LLM] Falling back to Groq...")
    for model in GROQ_MODELS:
        try:
            print(f"[LLM] Groq: {model}")
            response = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=15
            )
            print(f"[LLM] ✓ Groq success")
            return response.choices[0].message.content
        except Exception as e:
            print(f"[LLM] Groq {model} failed: {str(e)[:60]}")

    # --- PHASE 3: OPENROUTER (FINAL FALLBACK) ---
    print("[LLM] Falling back to OpenRouter...")
    for model in OPENROUTER_MODELS:
        try:
            print(f"[LLM] OpenRouter: {model}")
            response = openrouter_client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=30
            )
            print(f"[LLM] ✓ OpenRouter success")
            return response.choices[0].message.content
        except Exception as e:
            print(f"[LLM] OpenRouter {model} failed: {str(e)[:60]}")

    return "All models (Gemini, Groq, and OpenRouter) are currently busy."