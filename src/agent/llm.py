import os
import asyncio
from groq import Groq
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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

    # --- PHASE 1.5: OPENAI FALLBACK (AFTER GEMINI FAILS) ---
    print("[LLM] Gemini failed. Falling back to OpenAI GPT-5 Nano...")
    try:
        response = openai_client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages,
            timeout=15
        )
        print(f"[LLM] ✓ OpenAI GPT-5 Nano success")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] OpenAI GPT-5 Nano failed: {str(e)[:60]}")

    # --- PHASE 2: GROQ (AFTER OPENAI FAILS) ---
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

    return "All models (Gemini, OpenAI, Groq, and OpenRouter) are currently busy."