import os
from src.agent.core import Agent
from src.memory.database import init_db

os.makedirs("src/api/static", exist_ok=True)

init_db()
agent = Agent(session_id="athul-main")