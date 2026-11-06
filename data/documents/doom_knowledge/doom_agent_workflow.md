# DOOM Agent and LangGraph Workflow

## Main components
- Agent core: `src/agent/core.py`.
- LangGraph workflow: `src/agent/graph.py`.
- Tool registry: `src/tools/registry.py`.
- MCP adapter: `src/tools/mcp_server.py`.

LangGraph is already integrated in the project. The workflow is intended to coordinate user requests, routing, tool selection, and execution.

## Engineering approach
A useful design separates model reasoning from privileged application actions:
1. Parse and validate the request.
2. Select an allowed action or tool.
3. Validate tool arguments against a schema.
4. Apply authorization and policy checks.
5. Execute the tool in the application layer.
6. Normalize the result and return it to the user.
7. Record traces and evaluation outcomes where configured.

Prefer deterministic or hybrid routing for high-impact actions. Do not allow an LLM's free-form output to bypass application-layer validation or authorization.

## Evaluation dimensions
- Intent/routing accuracy.
- Tool-selection accuracy.
- Tool-argument validity.
- Multi-step task completion rate.
- Correct handling of missing information.
- Safe refusal or confirmation for side-effecting actions.
- Provider fallback success rate.
- End-to-end latency and token usage.

Keep deterministic test results separate from LLM-as-judge scores. Record the test set, expected outcome, model/provider, and evaluation date.
