from src.memory.database import engine
from sqlalchemy import text
with engine.begin() as c:
    c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    print("pgvector enabled:", c.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")).scalar())
engine.dispose()
