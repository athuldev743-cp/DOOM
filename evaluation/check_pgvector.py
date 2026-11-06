from src.memory.database import engine
from sqlalchemy import text
with engine.connect() as c:
    print("Available pgvector:", c.execute(text("SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector'")).fetchall())
    print("Current database user:", c.execute(text("SELECT current_user")).scalar())
    print("Can create:", c.execute(text("SELECT has_database_privilege(current_user, current_database(), 'CREATE')")).scalar())
engine.dispose()
