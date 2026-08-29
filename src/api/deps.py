import os
from dataclasses import dataclass

from fastapi import Request

from src.agent.core import Agent
from src.memory.database import init_db
from src.api.auth import decode_session_token

os.makedirs("src/api/static", exist_ok=True)

init_db()
agent = Agent(session_id="athul-main")

SESSION_COOKIE_NAME = "doom_session"


@dataclass
class Identity:
    is_owner: bool
    email: str | None = None


def get_current_identity(request: Request) -> Identity:
    """FastAPI dependency: read the session cookie and resolve identity.

    Never raises — a missing, expired, or invalid cookie always resolves to
    is_owner=False. The chat routes use that to fall back to the static
    HR response instead of erroring out, so a stranger visiting the site
    gets a clean answer rather than a 401.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_token(token)
    if payload is None:
        return Identity(is_owner=False)
    return Identity(is_owner=True, email=payload.get("email"))