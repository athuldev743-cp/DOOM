from sqlalchemy import text
from src.memory.database import engine

TABLE = "doom_document_chunks"
INDEX = f"ix_{TABLE}_search_vector_gin"

try:
    with engine.begin() as conn:
        conn.execute(text(f"""
            ALTER TABLE {TABLE}
            ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
            GENERATED ALWAYS AS (
                to_tsvector('english', COALESCE(content, ''))
            ) STORED
        """))

        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS {INDEX}
            ON {TABLE} USING GIN (search_vector)
        """))

        column = conn.execute(text("""
            SELECT data_type, is_generated, generation_expression
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
              AND column_name = 'search_vector'
        """), {"table": TABLE}).mappings().first()

        index = conn.execute(text("""
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = :table
              AND indexname = :index
        """), {"table": TABLE, "index": INDEX}).scalar()

        print("FTS column:", dict(column) if column else "MISSING")
        print("GIN index:", index or "MISSING")

        if not column:
            raise RuntimeError("FTS column is missing.")

        if column["data_type"] != "tsvector" or column["is_generated"] != "ALWAYS":
            raise RuntimeError("FTS column is not the expected generated TSVECTOR.")

        if not index or "USING gin (search_vector)" not in index.lower():
            raise RuntimeError("Expected GIN index on search_vector is missing.")

    print("PASS: PostgreSQL FTS schema verified.")

finally:
    engine.dispose()
