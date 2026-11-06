import asyncio
import importlib
from pathlib import Path

import httpx
import pytest


def _request(app, method, path, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            client.cookies.update(kwargs.pop("cookies", {}))
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


@pytest.fixture
def app(monkeypatch, tmp_path_factory):
    workspace = tmp_path_factory.mktemp("api-security")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{workspace / 'doom.db'}")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-32-bytes-minimum")
    monkeypatch.setenv("DOCS_PATH", str(workspace / "documents"))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://allowed.example")

    module = importlib.import_module("src.api.app")
    return module.app


@pytest.fixture
def owner_cookie(app):
    from src.api.auth import create_session_token

    return {"doom_session": create_session_token("athuldev743@gmail.com")}


def test_command_rejects_anonymous_and_non_owner_requests(app):
    anonymous = _request(app, "POST", "/command", json={"command": "lock"})
    visitor = _request(
        app,
        "POST",
        "/command",
        json={"command": "lock"},
        cookies={"doom_visitor_id": "visitor"},
    )

    assert anonymous.status_code == 403
    assert visitor.status_code == 403


def test_command_allows_owner_without_executing_real_automation(app, owner_cookie, monkeypatch):
    from src.tools.automation import AutomationTool
    from src.tools.schemas import ToolResult

    calls = []

    def fake_run(self, command, args=""):
        calls.append((command, args))
        return ToolResult(success=True, message="mocked")

    monkeypatch.setattr(AutomationTool, "run", fake_run)

    response = _request(
        app,
        "POST",
        "/command",
        json={"command": "lock", "args": ""},
        cookies=owner_cookie,
    )

    assert response.status_code == 200
    assert calls == [("lock", "")]


def test_upload_rejects_anonymous_requests(app):
    response = _request(
        app,
        "POST",
        "/upload",
        files={"file": ("notes.txt", b"safe text", "text/plain")},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("filename", ["../escape.txt", "..\\escape.txt"])
def test_upload_rejects_path_traversal(app, owner_cookie, filename):
    response = _request(
        app,
        "POST",
        "/upload",
        files={"file": (filename, b"safe text", "text/plain")},
        cookies=owner_cookie,
    )

    assert response.status_code == 422


def test_upload_rejects_empty_and_unsupported_filenames(app, owner_cookie):
    empty = _request(
        app,
        "POST",
        "/upload",
        files={"file": ("", b"safe text", "text/plain")},
        cookies=owner_cookie,
    )
    unsupported = _request(
        app,
        "POST",
        "/upload",
        files={"file": ("payload.exe", b"not executable", "application/octet-stream")},
        cookies=owner_cookie,
    )

    assert empty.status_code == 422
    assert unsupported.status_code == 415


def test_upload_rejects_oversized_content(app, owner_cookie, monkeypatch):
    monkeypatch.setenv("DOCS_UPLOAD_MAX_BYTES", "8")

    response = _request(
        app,
        "POST",
        "/upload",
        files={"file": ("large.txt", b"more than eight bytes", "text/plain")},
        cookies=owner_cookie,
    )

    assert response.status_code == 413


def test_owner_can_upload_supported_text_document(app, owner_cookie, monkeypatch):
    from src.memory import rag

    ingested_paths = []
    monkeypatch.setattr(rag, "ingest_text", lambda path: ingested_paths.append(path) or "indexed")

    response = _request(
        app,
        "POST",
        "/upload",
        files={"file": ("notes.txt", b"safe text", "text/plain")},
        cookies=owner_cookie,
    )

    assert response.status_code == 200
    assert response.json() == {"result": "indexed"}
    stored_file = Path(ingested_paths[0])
    assert stored_file.name == "notes.txt"
    assert stored_file.read_bytes() == b"safe text"


@pytest.mark.parametrize("path", ["/memory", "/docs-list", "/briefing", "/reminders"])
def test_sensitive_routes_reject_anonymous_requests(app, path):
    response = _request(app, "GET", path)

    assert response.status_code == 403


def test_owner_can_access_sensitive_routes(app, owner_cookie, monkeypatch):
    from src.memory import rag
    from src.memory.profile import ProfileManager
    from src.tools import briefing_tool, registry
    from src.tools.schemas import ToolResult

    monkeypatch.setattr(ProfileManager, "get_all", lambda self: {"name": "Athul"})
    monkeypatch.setattr(ProfileManager, "list_contacts", lambda self: "No contacts saved yet.")
    monkeypatch.setattr(rag, "list_docs", lambda: "Indexed documents:\n- notes.txt")
    monkeypatch.setattr(
        briefing_tool.DailyBriefingTool,
        "run",
        lambda self: ToolResult(success=True, message="briefing"),
    )
    monkeypatch.setattr(
        registry,
        "get_tool",
        lambda name: type("ReminderTool", (), {"run": lambda self: ToolResult(success=True, message="none")})(),
    )

    responses = {
        path: _request(app, "GET", path, cookies=owner_cookie)
        for path in ("/memory", "/docs-list", "/briefing", "/reminders")
    }

    assert all(response.status_code == 200 for response in responses.values())


def test_health_remains_public(app):
    response = _request(app, "GET", "/health")

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_cors_allows_only_configured_origins(app):
    allowed = _request(
        app,
        "OPTIONS",
        "/health",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    disallowed = _request(
        app,
        "GET",
        "/health",
        headers={"Origin": "https://disallowed.example"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://allowed.example"
    assert "access-control-allow-origin" not in disallowed.headers
