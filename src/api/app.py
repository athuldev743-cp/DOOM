from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.api.routes import chat, system, upload, memory, linkedin, transcribe


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    from src.voice.tts_server import text_to_speech
    from src.tools.scheduler import scheduler

    common = ["Got it.", "Done.", "Sure thing.", "Let me check.", "Here's what I found."]
    for phrase in common:
        await text_to_speech(phrase)
    print("[TTS] Warmup complete")

    scheduler.start()
    print("[DOOM] Scheduler started")

    yield  # Application runs while suspended here

    # --- SHUTDOWN LOGIC ---
    if scheduler.running:
        scheduler.shutdown()
        print("[DOOM] Scheduler stopped")


app = FastAPI(title="DOOM AI", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(memory.router)
app.include_router(linkedin.router)
app.include_router(transcribe.router)


@app.head("/health")
@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "DOOM-AI-Backend"
    }