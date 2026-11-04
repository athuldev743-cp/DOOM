from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import (
    chat, system, upload, memory, linkedin, transcribe,
    auth as auth_routes, leads, latency,
)
from src.memory.database import init_db
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

# Stateless HTTP avoids in-memory session affinity requirements on hosted
# deployments and works well for request/response tool calls.
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

init_db()

app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(linkedin.router)
app.include_router(transcribe.router)
app.include_router(auth_routes.router)
app.include_router(leads.router)
app.include_router(latency.router)


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
# The MCP SDK's own endpoint remains /mcp (not /mcp/mcp).
app.mount("/", mcp_http_app)
