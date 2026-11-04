"""Expose DOOM's existing tool registry through the Model Context Protocol.

The MCP adapter is intentionally thin: tool implementations remain in
src/tools, and execution continues through each tool's existing argument
schema/signature validation.
"""
import asyncio
import inspect
from typing import get_type_hints

from mcp.server import MCPServer

from src.tools.registry import TOOLS
from src.tools.schemas import ToolResult


def _tool_signature(tool):
    """Build a JSON-schema-friendly signature from the tool's Pydantic schema
    when present, otherwise from its run() method.
    """
    schema = getattr(tool, "args_schema", None)
    if schema is not None:
        parameters = []
        annotations = {}
        for name, field in schema.model_fields.items():
            default = inspect.Parameter.empty if field.is_required() else field.default
            parameters.append(
                inspect.Parameter(
                    name,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                    annotation=field.annotation,
                )
            )
            annotations[name] = field.annotation
        return inspect.Signature(parameters), annotations

    run_signature = inspect.signature(tool.run)
    hints = get_type_hints(tool.run)
    parameters = []
    annotations = {}
    for parameter in run_signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        annotation = hints.get(parameter.name, parameter.annotation)
        parameters.append(parameter.replace(annotation=annotation))
        if annotation is not inspect.Parameter.empty:
            annotations[parameter.name] = annotation
    return inspect.Signature(parameters), annotations


def _build_handler(name, tool):
    signature, annotations = _tool_signature(tool)

    def execute(arguments):
        if getattr(tool, "args_schema", None) is not None:
            validated = tool.args_schema.model_validate(arguments)
            safe_arguments = validated.model_dump()
        else:
            # Signature binding rejects unknown keys and missing required args.
            bound = signature.bind(**arguments)
            safe_arguments = dict(bound.arguments)

        result = tool.run(**safe_arguments)
        if isinstance(result, ToolResult):
            return result.to_wire()
        return str(result)

    async def handler(**kwargs):
        try:
            return await asyncio.to_thread(execute, kwargs)
        except Exception as exc:
            # Keep the MCP error concise; detailed exceptions stay in server logs.
            print(f"[MCP] {name} failed: {type(exc).__name__}: {exc}")
            raise ValueError(f"{name} failed: {exc}") from exc

    handler.__name__ = name
    handler.__qualname__ = name
    handler.__doc__ = tool.description or f"Execute DOOM tool: {name}"
    handler.__signature__ = signature
    handler.__annotations__ = {**annotations, "return": str}
    return handler


mcp_server = MCPServer(
    "DOOM",
    instructions=(
        "DOOM's existing tools exposed through MCP. Tool execution is owner-only. "
        "Use the supplied typed arguments; do not invent results."
    ),
)

for tool_name, tool_instance in TOOLS.items():
    mcp_server.add_tool(_build_handler(tool_name, tool_instance))


def registered_mcp_tool_names():
    """Return registry names for health checks and tests."""
    return tuple(TOOLS.keys())
