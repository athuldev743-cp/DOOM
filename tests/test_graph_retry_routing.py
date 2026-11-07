import asyncio

from src.agent import graph


def make_state(**overrides):
    values = {
        "messages": [
            {"role": "system", "content": "Test system prompt"},
            {"role": "user", "content": "Search my documents"},
        ]
    }
    values.update(overrides)
    return graph.AgentState(**values)


def test_malformed_tool_format_sets_validation_error(monkeypatch):
    async def fake_chat(messages):
        return "Tool: search_file\nArgs: none"

    monkeypatch.setattr(graph, "chat", fake_chat)

    result = asyncio.run(graph.decide_node(make_state()))

    assert result["tool_name"] is None
    assert result["validation_error"] is not None
    assert "Malformed tool-call format" in result["validation_error"]


def test_malformed_tool_format_routes_to_retry():
    state = make_state(
        validation_error="Malformed tool-call format",
        retries=0,
    )

    assert graph.route_after_decide(state) == "retry"


def test_malformed_tool_format_stops_at_retry_limit():
    state = make_state(
        validation_error="Malformed tool-call format",
        retries=graph.MAX_RETRIES,
    )

    assert graph.route_after_decide(state) == "respond"


def test_normal_response_does_not_trigger_retry(monkeypatch):
    async def fake_chat(messages):
        return "Here is the information you requested."

    monkeypatch.setattr(graph, "chat", fake_chat)

    result = asyncio.run(graph.decide_node(make_state()))

    assert result["tool_name"] is None
    assert result["validation_error"] is None

    updated_state = make_state(
        validation_error=result["validation_error"]
    )
    assert graph.route_after_decide(updated_state) == "respond"


def test_valid_tool_call_routes_to_validation():
    state = make_state(
        tool_name="search_docs",
        tool_args_raw="DOOM architecture",
    )

    assert graph.route_after_decide(state) == "validate_args"


def test_retry_node_increments_retry_count():
    state = make_state(
        validation_error="Malformed tool-call format",
        retries=0,
    )

    result = asyncio.run(graph.retry_node(state))

    assert result["retries"] == 1
    assert result["tool_name"] is None
    assert result["validation_error"] is None
    assert "Malformed tool-call format" in result["messages"][-1]["content"]
