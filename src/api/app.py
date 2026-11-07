from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Register every SQLAlchemy model before create_all(). ProfileManager is
# instantiated while the tool registry is imported, so its table must exist
# before importing routes/tools that create a ProfileManager at module scope.
from src.memory.database import init_db
from src.memory.profile import UserProfile  # noqa: F401 - model registration
from src.tools.reminder import Reminder  # noqa: F401 - model registration

init_db()

from src.api.routes import (
    chat, system, upload, memory, transcribe,
    auth as auth_routes, leads, latency, evaluation, production_evaluation,
)
from src.tools.mcp_server import mcp_server, registered_mcp_tool_names
from mcp.server.transport_security import TransportSecuritySettings


MCP_ALLOWED_HOSTS = [
    value.strip()
    for value in os.getenv(
        "MCP_ALLOWED_HOSTS",
        "doom-1a9d9743.fastapicloud.dev,doom-1a9d9743.fastapicloud.dev:*",
    ).split(",")
    if value.strip()
]
MCP_ALLOWED_ORIGINS = [
    value.strip()
    for value in os.getenv(
        "MCP_ALLOWED_ORIGINS",
        "https://doom-1a9d9743.fastapicloud.dev",
    ).split(",")
    if value.strip()
]
CORS_ALLOWED_ORIGINS = [
    value.strip()
    for value in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost,http://localhost:8000,"
        "http://127.0.0.1,http://127.0.0.1:8000",
    ).split(",")
    if value.strip()
]

mcp_http_app = mcp_server.streamable_http_app(
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=MCP_ALLOWED_HOSTS,
        allowed_origins=MCP_ALLOWED_ORIGINS,
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.voice.tts_server import text_to_speech
    from src.tools.scheduler import scheduler

    async with mcp_server.session_manager.run():
        try:
            common = [
                "Got it.", "Done.", "Sure thing.",
                "Let me check.", "Here's what I found.",
            ]
            for phrase in common:
                await text_to_speech(phrase)
            print("[TTS] Warmup complete")

            if not scheduler.running:
                scheduler.start()
            print("[DOOM] Scheduler started")
            print(
                f"[MCP] Streamable HTTP ready; "
                f"{len(registered_mcp_tool_names())} tools registered"
            )
            yield
        finally:
            if scheduler.running:
                scheduler.shutdown()
                print("[DOOM] Scheduler stopped")


app = FastAPI(title="DOOM AI", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_owner_for_mcp(request: Request, call_next):
    """MCP exposes personal tools, so every MCP request is owner-only."""
    if request.url.path == "/mcp" or request.url.path.startswith("/mcp/"):
        if request.method == "OPTIONS":
            return await call_next(request)

        token = request.cookies.get("doom_session")
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()

        from src.api.auth import decode_session_token

        identity = decode_session_token(token)
        if identity is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Owner authentication required for DOOM MCP."},
            )

    return await call_next(request)


app.include_router(system.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(memory.router)

app.include_router(transcribe.router)
app.include_router(auth_routes.router)
app.include_router(leads.router)
app.include_router(latency.router)
app.include_router(evaluation.router)
app.include_router(production_evaluation.router)


@app.head("/health")
@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "DOOM-AI-Backend",
        "mcp": {
            "transport": "streamable-http",
            "endpoint": "/mcp",
            "tools": len(registered_mcp_tool_names()),
            "authentication": "owner-only",
        },
    }


# Mount last so the existing FastAPI routes keep precedence.
app.mount("/", mcp_http_app)
