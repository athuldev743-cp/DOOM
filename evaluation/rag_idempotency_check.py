import asyncio
from sqlalchemy import text
from src.memory.database import engine
from src.tools.registry import TOOLS
from src.tools.mcp_server import _build_handler

def counts():
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*), COUNT(DISTINCT source) FROM doom_document_chunks")).one()

before = counts()
result = asyncio.run(_build_handler("ingest_docs", TOOLS["ingest_docs"])())
after = counts()

print("BEFORE:", before)
print("AFTER: ", after)
assert before == after, "Duplicate chunks detected after re-ingestion"
assert after == (11, 9), f"Unexpected corpus size: {after}"
print("PASS: MCP ingestion is idempotent")
