import asyncio
from src.tools.registry import TOOLS
from src.tools.mcp_server import _build_handler, registered_mcp_tool_names

required = {"search_docs", "list_docs", "ingest_docs"}
assert required.issubset(set(registered_mcp_tool_names()))

docs = asyncio.run(_build_handler("list_docs", TOOLS["list_docs"])())
assert "doom_agent_workflow.md" in str(docs), docs

result = asyncio.run(_build_handler("search_docs", TOOLS["search_docs"])(query="What is the DOOM LangGraph workflow and agent components?"))
assert "doom_agent_workflow.md" in str(result), result

print("PASS: All 3 RAG tools registered with MCP")
print("PASS: list_docs executed through MCP adapter")
print("PASS: search_docs executed through MCP adapter")
print("PASS: Expected Neon document retrieved")
