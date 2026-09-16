"""
LangGraph state machine replacing the old regex TOOL:/ARGS: dispatch loop.

Flow:

    decide
      ├── no tool ───────────────> respond ──> END
      │
      └── tool detected
              │
              v
        validate_args
              │
        ┌─────┴──────────────┐
        │                    │
      invalid              valid
        │                    │
        v                    v
      retry              call_tool
        │                    │
        └──> decide          │
                             v
                      format_response
                             │
                             v
                          respond
                             │
                             v
                            END

The retry loop activates the Pydantic args_schema / parse_args
validation that was introduced during the Pydantic migration.
"""

from typing import Optional

from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, ValidationError

from src.agent.llm import chat
from src.tools.registry import get_tool
from src.tools.schemas import ToolResult


MAX_RETRIES = 2
RECURSION_LIMIT = 20


# Frontend / client-facing prefixes that must NOT be reformatted by the LLM.
BYPASS_PREFIXES = (
    "CALL:",
    "WHATSAPP:",
    "YOUTUBE:",
    "APP:",
    "JOBS_DATA:",
    "APPLY_REPORT:",
)


class AgentState(BaseModel):
    """
    State carried through the LangGraph execution.
    """

    # Seeded by Agent.chat() with:
    # [system, ...history, user_input]
    messages: list[dict]

    # Tool detection
    tool_name: Optional[str] = None
    tool_args_raw: Optional[str] = None

    # Validated tool arguments
    validated_args: Optional[dict] = None

    # Validation state
    validation_error: Optional[str] = None

    # Raw result returned by the tool
    tool_result_wire: Optional[str] = None

    # Final user-facing response
    final_response: Optional[str] = None

    # Number of validation retries
    retries: int = 0


# ---------------------------------------------------------------------------
# TOOL CALL PARSING
# ---------------------------------------------------------------------------

def _parse_tool_call(response: str):
    """
    Extract:

        TOOL: tool_name
        ARGS: raw arguments

    from the LLM response.

    Returns:
        (tool_name, args_raw)

    or:

        (None, None)
    """

    import re

    response = response.strip()

    if "TOOL:" not in response:
        return None, None

    try:
        tool_match = re.search(
            r"TOOL:\s*(\S+)",
            response,
        )

        args_match = re.search(
            r"ARGS:\s*(.+?)(?:\n|$)",
            response,
            re.DOTALL,
        )

        if not tool_match:
            return None, None

        tool_name = tool_match.group(1).strip()

        args_raw = (
            args_match.group(1).strip()
            if args_match
            else ""
        )

        return tool_name, args_raw

    except Exception as e:
        print(f"[Graph] tool call parsing error: {e}")
        return None, None


def _clean_response(response: str) -> str:
    """
    Remove TOOL:/ARGS: lines before sending the response to the frontend.
    """

    if not response:
        return ""

    lines = response.split("\n")

    clean = [
        line
        for line in lines
        if not line.strip().startswith("TOOL:")
        and not line.strip().startswith("ARGS:")
    ]

    return "\n".join(clean).strip()


# ---------------------------------------------------------------------------
# NODES
# ---------------------------------------------------------------------------

async def decide_node(state: AgentState) -> dict:
    """
    Ask the LLM what to do.

    The LLM can either:
      - answer normally
      - emit TOOL:/ARGS:
    """

    response = await chat(state.messages)

    print(f"[Graph] decide -> {response!r}")

    tool_name, args_raw = _parse_tool_call(response)

    new_messages = state.messages + [
        {
            "role": "assistant",
            "content": response,
        }
    ]

    return {
        "messages": new_messages,
        "tool_name": tool_name,
        "tool_args_raw": args_raw,

        # Clear stale validation state when starting another decision.
        "validation_error": None,

        # Clear stale validated args.
        "validated_args": None,
    }


async def validate_args_node(state: AgentState) -> dict:
    """
    Validate the LLM-generated tool arguments against the tool's
    parse_args() and optional Pydantic args_schema.
    """

    if not state.tool_name:
        return {
            "validation_error": "No tool name supplied."
        }

    tool = get_tool(state.tool_name)

    if not tool:
        return {
            "validation_error": (
                f"Unknown tool: {state.tool_name}"
            )
        }

    try:
        # First allow the tool to convert the raw LLM string
        # into structured Python arguments.
        parsed = tool.parse_args(
            state.tool_args_raw or ""
        )

        # Then apply the Pydantic schema if the tool defines one.
        if tool.args_schema:
            validated = tool.args_schema.model_validate(parsed)

            args_dict = validated.model_dump()

        else:
            args_dict = parsed

        print(
            f"[Graph] validation passed for "
            f"{state.tool_name}: {args_dict}"
        )

        return {
            "validated_args": args_dict,
            "validation_error": None,
        }

    except ValidationError as e:

        print(
            f"[Graph] validation failed for "
            f"{state.tool_name}: {e}"
        )

        return {
            "validated_args": None,
            "validation_error": str(e),
        }

    except Exception as e:

        print(
            f"[Graph] argument parsing failed for "
            f"{state.tool_name}: {e}"
        )

        return {
            "validated_args": None,
            "validation_error": str(e),
        }


async def retry_node(state: AgentState) -> dict:
    """
    Tell the LLM that its previous tool call failed validation
    and ask it to issue a corrected TOOL:/ARGS: call.
    """

    correction = {
        "role": "user",
        "content": (
            "Your last tool call had invalid arguments and failed "
            "validation.\n\n"
            f"Validation error:\n{state.validation_error}\n\n"
            "Re-issue the TOOL:/ARGS: call with corrected arguments "
            "matching the expected format."
        ),
    }

    new_retries = state.retries + 1

    print(
        f"[Graph] retry -> {new_retries}/{MAX_RETRIES}"
    )

    return {
        "messages": state.messages + [correction],
        "retries": new_retries,
        "tool_name": None,
        "tool_args_raw": None,
        "validated_args": None,
        "validation_error": None,
    }


async def call_tool_node(state: AgentState) -> dict:
    """
    Execute the validated tool arguments.
    """

    tool = get_tool(state.tool_name)

    if not tool:
        wire = f"Tool error: Unknown tool: {state.tool_name}"

        return {
            "tool_result_wire": wire,
            "final_response": wire,
        }

    try:

        result = tool.run(
            **(state.validated_args or {})
        )

        if isinstance(result, ToolResult):
            wire = result.to_wire()
        else:
            wire = str(result)

    except Exception as e:

        print(
            f"[Graph] tool execution error: {e}"
        )

        wire = f"Tool error: {str(e)}"

    print(
        f"[Graph] {state.tool_name} -> {wire!r}"
    )

    # These results are already formatted for the frontend/client.
    if (
        wire.startswith(BYPASS_PREFIXES)
        or wire == "LINKEDIN_AUTH_REQUIRED"
        or "NOT_FOUND" in wire
    ):
        return {
            "tool_result_wire": wire,
            "final_response": wire,
        }

    return {
        "tool_result_wire": wire,
    }


async def format_response_node(state: AgentState) -> dict:
    """
    Convert a raw tool result into a concise user-facing response.

    The LLM is explicitly instructed to use ONLY the tool result.
    """

    instruction = {
        "role": "user",
        "content": (
            f"Tool result:\n"
            f"{state.tool_result_wire}\n\n"

            "STRICT INSTRUCTIONS:\n"

            "1. Present ONLY the information from the tool result above.\n"

            "2. Do NOT add, invent, infer, or hallucinate any jobs, "
            "companies, links, or details.\n"

            "3. Do NOT say 'I applied' unless the tool result contains "
            "'✅ Applied'.\n"

            "4. If jobs are present, list them cleanly using only "
            "the number, title, company if visible, and link.\n"

            "5. End with exactly:\n"
            "'To apply to any of these: say apply for [role] at [company]'\n"

            "6. Never show TOOL: or ARGS: in the response.\n"

            "7. Keep the response concise and factual.\n"

            "8. Do not add commentary that is not present in the "
            "tool result."
        ),
    }

    response = await chat(
        state.messages + [instruction]
    )

    return {
        "final_response": _clean_response(response)
    }


async def respond_node(state: AgentState) -> dict:
    """
    Final response node.

    If another node already produced a final response, preserve it.

    Otherwise return the latest assistant message after removing
    TOOL:/ARGS: markers.
    """

    if state.final_response is not None:
        return {
            "final_response": state.final_response
        }

    last = (
        state.messages[-1]["content"]
        if state.messages
        else ""
    )

    return {
        "final_response": _clean_response(last)
    }


# ---------------------------------------------------------------------------
# ROUTING
# ---------------------------------------------------------------------------

def route_after_decide(state: AgentState) -> str:
    """
    Decide whether the LLM requested a valid registered tool.
    """

    if (
        state.tool_name
        and get_tool(state.tool_name)
    ):
        return "validate_args"

    return "respond"


def route_after_validate(state: AgentState) -> str:
    """
    Validation routing:

        valid
            -> call_tool

        invalid + retries available
            -> retry

        invalid + retry limit reached
            -> respond
    """

    if state.validation_error:

        if state.retries >= MAX_RETRIES:
            print(
                "[Graph] validation retry limit reached"
            )

            return "respond"

        return "retry"

    return "call_tool"


def route_after_call_tool(state: AgentState) -> str:
    """
    Decide whether the tool result:

      - is already frontend-ready
      - needs LLM formatting
    """

    if state.final_response is not None:
        return "respond"

    return "format_response"


# ---------------------------------------------------------------------------
# GRAPH ASSEMBLY
# ---------------------------------------------------------------------------

def _build_graph():
    """
    Build and compile the LangGraph state machine.
    """

    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node(
        "decide",
        decide_node,
    )

    graph.add_node(
        "validate_args",
        validate_args_node,
    )

    graph.add_node(
        "retry",
        retry_node,
    )

    graph.add_node(
        "call_tool",
        call_tool_node,
    )

    graph.add_node(
        "format_response",
        format_response_node,
    )

    graph.add_node(
        "respond",
        respond_node,
    )

    # START -> decide
    graph.add_edge(
        START,
        "decide",
    )

    # decide -> validate_args OR respond
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {
            "validate_args": "validate_args",
            "respond": "respond",
        },
    )

    # validate_args -> call_tool OR retry OR respond
    graph.add_conditional_edges(
        "validate_args",
        route_after_validate,
        {
            "call_tool": "call_tool",
            "retry": "retry",
            "respond": "respond",
        },
    )

    # retry -> decide
    graph.add_edge(
        "retry",
        "decide",
    )

    # call_tool -> respond OR format_response
    graph.add_conditional_edges(
        "call_tool",
        route_after_call_tool,
        {
            "respond": "respond",
            "format_response": "format_response",
        },
    )

    # format_response -> respond
    graph.add_edge(
        "format_response",
        "respond",
    )

    # respond -> END
    graph.add_edge(
        "respond",
        END,
    )

    return graph.compile()


# Compile once when the module is imported.
compiled_graph = _build_graph()


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

async def run_graph(
    seed_messages: list[dict],
) -> str:
    """
    Run the LangGraph agent.

    Args:
        seed_messages:
            Usually:
                [
                    {"role": "system", "content": "..."},
                    ...history,
                    {"role": "user", "content": "..."},
                ]

    Returns:
        Final user-facing response string.
    """

    initial_state = AgentState(
        messages=seed_messages
    )

    result = await compiled_graph.ainvoke(
        initial_state,
        config={
            "recursion_limit": RECURSION_LIMIT
        },
    )

    return result.get(
        "final_response",
        ""
    ) or ""