import asyncio
import importlib
import sys
import types

from pydantic import BaseModel


class EchoArgs(BaseModel):
    message: str
    uppercase: bool = False


class FakeTool:
    name = "echo"
    description = "Return the supplied message."
    args_schema = EchoArgs

    def run(self, message: str, uppercase: bool = False):
        return message.upper() if uppercase else message


class RawTool:
    description = "Accept a required name."

    def run(self, name: str):
        return f"hello {name}"


def load_adapter(monkeypatch, tools):
    registry = types.ModuleType("src.tools.registry")
    registry.TOOLS = tools

    schemas = types.ModuleType("src.tools.schemas")

    class ToolResult:
        def __init__(self, value):
            self.value = value

        def to_wire(self):
            return self.value

    schemas.ToolResult = ToolResult
    monkeypatch.setitem(sys.modules, "src.tools.registry", registry)
    monkeypatch.setitem(sys.modules, "src.tools.schemas", schemas)
    sys.modules.pop("src.tools.mcp_server", None)
    return importlib.import_module("src.tools.mcp_server")


def test_all_registry_tools_are_registered_with_mcp(monkeypatch):
    adapter = load_adapter(monkeypatch, {"echo": FakeTool(), "raw": RawTool()})
    assert adapter.registered_mcp_tool_names() == ("echo", "raw")


def test_pydantic_schema_validates_and_executes(monkeypatch):
    adapter = load_adapter(monkeypatch, {"echo": FakeTool()})
    handler = adapter._build_handler("echo", FakeTool())
    result = asyncio.run(handler(message="doom", uppercase=True))
    assert result == "DOOM"


def test_untyped_tool_rejects_missing_required_arguments(monkeypatch):
    adapter = load_adapter(monkeypatch, {"raw": RawTool()})
    handler = adapter._build_handler("raw", RawTool())
    try:
        asyncio.run(handler())
    except ValueError as exc:
        assert "raw failed" in str(exc)
    else:
        raise AssertionError("Missing required MCP arguments were accepted")
