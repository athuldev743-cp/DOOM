import asyncio
from sqlalchemy import text
from src.tools.registry import TOOLS
from src.tools.mcp_server import _build_handler
from src.memory.database import engine

handler = _build_handler("ingest_docs", TOOLS["ingest_docs"])
for run in range(1, 3):
    result = asyncio.run(handler())
    print(f"INGEST RUN {run}: {result}")

with engine.connect() as conn:
    row = conn.execute(text("""
        SELECT COUNT(*), COUNT(DISTINCT source)
        FROM doom_document_chunks
    """)).one()

print(f"FINAL CHUNKS: {row[0]}")
print(f"FINAL SOURCES: {row[1]}")
assert row[0] == 8 and row[1] == 8, "Unexpected chunk/source count"
print("PASS: Repeated ingestion did not create duplicate chunks")
