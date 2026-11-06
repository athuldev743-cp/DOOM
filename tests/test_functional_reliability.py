import asyncio
import importlib
from types import SimpleNamespace

import pytest
from pydantic import ValidationError


@pytest.fixture
def runtime_environment(monkeypatch, tmp_path_factory):
    workspace = tmp_path_factory.mktemp("functional-reliability")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{workspace / 'doom.db'}")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-with-32-bytes-minimum")
    from src.memory.database import init_db
    from src.memory.models import Conversation, Message, UserMemory  # noqa: F401
    from src.memory.profile import UserProfile  # noqa: F401
    from src.tools.reminder import Reminder  # noqa: F401

    init_db()
    return workspace


@pytest.mark.parametrize(
    ("standard_key", "legacy_key", "expected_key"),
    [
        ("standard", "legacy", "standard"),
        (None, "legacy", "legacy"),
        (None, None, "dummy"),
    ],
)
def test_groq_provider_uses_standard_then_legacy_key(
    monkeypatch,
    standard_key,
    legacy_key,
    expected_key,
):
    module = importlib.import_module("src.agent.llm_providers.groq_provider")
    captured = {}

    class FakeGroq:
        def __init__(self, api_key, max_retries):
            captured["api_key"] = api_key
            captured["max_retries"] = max_retries

    monkeypatch.setattr(module, "Groq", FakeGroq)
    if standard_key is None:
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GROQ_API_KEY", standard_key)
    if legacy_key is None:
        monkeypatch.delenv("GROQAPI_KEY", raising=False)
    else:
        monkeypatch.setenv("GROQAPI_KEY", legacy_key)

    module.GroqProvider()

    assert captured == {"api_key": expected_key, "max_retries": 0}


class _FakeLeadQuery:
    def __init__(self, records):
        self.records = records
        self.session_key = None

    def filter_by(self, session_key):
        self.session_key = session_key
        return self

    def first(self):
        return self.records.get(self.session_key)


class _FakeLeadSession:
    def __init__(self, records):
        self.records = records
        self.committed = False

    def query(self, _model):
        return _FakeLeadQuery(self.records)

    def add(self, visitor):
        self.records[visitor.session_key] = visitor

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_save_lead_uses_trusted_context_and_isolates_visitors(runtime_environment, monkeypatch):
    from src.tools import visitor_tool

    records = {}
    sessions = []

    def fake_session_local():
        session = _FakeLeadSession(records)
        sessions.append(session)
        return session

    monkeypatch.setattr(visitor_tool, "SessionLocal", fake_session_local)
    tool = visitor_tool.SaveLeadTool()

    without_context = tool.run(name="Unaffiliated")
    with visitor_tool.visitor_lead_context("visitor-a"):
        first = tool.run(name="Ada", company="Example")
    with visitor_tool.visitor_lead_context("visitor-b"):
        second = tool.run(name="Ben", interest="Hiring")

    assert not without_context.success
    assert first.success and second.success
    assert records["visitor-a"].name == "Ada"
    assert records["visitor-b"].name == "Ben"
    assert records["visitor-a"].company == "Example"
    assert all(session.committed for session in sessions)


def test_save_lead_schema_rejects_empty_and_internal_identity(runtime_environment):
    from src.tools.schemas import SaveLeadArgs

    with pytest.raises(ValidationError):
        SaveLeadArgs()
    with pytest.raises(ValidationError):
        SaveLeadArgs(name="Ada", session_key="visitor-b")


def test_save_lead_mcp_handler_cannot_select_visitor_identity(runtime_environment):
    from src.tools.mcp_server import _build_handler
    from src.tools.visitor_tool import SaveLeadTool

    handler = _build_handler("save_lead", SaveLeadTool())
    result = asyncio.run(handler(name="Ada"))

    assert result == "Lead capture is only available in a visitor conversation."
    with pytest.raises(ValueError, match="save_lead failed"):
        asyncio.run(handler(name="Ada", session_key="visitor-b"))


def test_save_lead_executes_through_graph_with_trusted_identity(runtime_environment, monkeypatch):
    from src.agent import graph
    from src.tools import visitor_tool

    records = {}
    monkeypatch.setattr(visitor_tool, "SessionLocal", lambda: _FakeLeadSession(records))
    monkeypatch.setattr(graph, "get_tool", lambda name: visitor_tool.SaveLeadTool())

    responses = iter([
        "TOOL: save_lead\nARGS: Ada | Recruiter | Example | Hiring | Intro",
        "Lead saved.",
    ])

    async def fake_chat(_messages):
        return next(responses)

    monkeypatch.setattr(graph, "chat", fake_chat)

    response = asyncio.run(
        graph.run_graph(
            [
                {"role": "system", "content": "visitor"},
                {"role": "user", "content": "hello"},
            ],
            tool_context={"visitor_session_key": "visitor-a"},
        )
    )

    assert response == "Lead saved."
    assert records["visitor-a"].name == "Ada"
    assert records["visitor-a"].company == "Example"


def test_visitor_agent_passes_trusted_identity_to_graph(runtime_environment, monkeypatch):
    from src.agent import core

    captured = {}

    async def fake_run_graph(messages, tool_context=None):
        captured["messages"] = messages
        captured["tool_context"] = tool_context
        return "Lead saved."

    monkeypatch.setattr(core, "run_graph", fake_run_graph)
    agent = core.Agent(
        session_id="visitor-memory-session",
        is_owner=False,
        visitor_session_key="visitor-trusted",
    )

    response = asyncio.run(agent.chat("I am Ada from Example"))

    assert response == "Lead saved."
    assert captured["tool_context"] == {"visitor_session_key": "visitor-trusted"}


def test_whatsapp_tools_parse_and_validate_arguments(runtime_environment):
    from src.tools.contacts_tool import WhatsAppContactTool, WhatsAppResumeTool

    contact_tool = WhatsAppContactTool()
    resume_tool = WhatsAppResumeTool()

    assert contact_tool.parse_args("Ada | Hello there") == {
        "name": "Ada",
        "message": "Hello there",
    }
    assert resume_tool.parse_args("Ada") == {"name": "Ada"}
    assert contact_tool.args_schema.model_validate(contact_tool.parse_args("Ada | Hi")).name == "Ada"
    with pytest.raises(ValidationError):
        contact_tool.args_schema.model_validate(contact_tool.parse_args(" | Hi"))
    with pytest.raises(ValidationError):
        resume_tool.args_schema.model_validate(resume_tool.parse_args("  "))


def test_whatsapp_tools_build_existing_wire_payloads_without_sending(runtime_environment, monkeypatch):
    from src.tools import contacts_tool

    contact = SimpleNamespace(name="Ada", phone="+91 123 456", whatsapp="+91 123 456")
    monkeypatch.setattr(contacts_tool.profile, "find_contact", lambda name: contact)

    contact_result = contacts_tool.WhatsAppContactTool().run(name="Ada", message="Hello")
    resume_result = contacts_tool.WhatsAppResumeTool().run(name="Ada")

    assert contact_result == "WHATSAPP:91123456:Hello"
    assert resume_result.startswith("WHATSAPP:91123456:")


def test_whatsapp_contact_executes_through_graph(runtime_environment, monkeypatch):
    from src.agent import graph
    from src.tools import contacts_tool

    contact = SimpleNamespace(name="Ada", phone="+91 123 456", whatsapp="+91 123 456")
    tool = contacts_tool.WhatsAppContactTool()
    monkeypatch.setattr(contacts_tool.profile, "find_contact", lambda name: contact)
    monkeypatch.setattr(graph, "get_tool", lambda name: tool if name == "whatsapp_contact" else None)

    async def fake_chat(_messages):
        return "TOOL: whatsapp_contact\nARGS: Ada | Hello"

    monkeypatch.setattr(graph, "chat", fake_chat)

    response = asyncio.run(
        graph.run_graph(
            [
                {"role": "system", "content": "owner"},
                {"role": "user", "content": "message Ada"},
            ]
        )
    )

    assert response == "WHATSAPP:91123456:Hello"
