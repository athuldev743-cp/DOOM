import os
from dataclasses import dataclass

from fastapi import Request

from src.agent.core import Agent
from src.memory.database import init_db
from src.api.auth import decode_session_token
import uuid  

os.makedirs("src/api/static", exist_ok=True)

init_db()
agent = Agent(session_id="athul-main")

SESSION_COOKIE_NAME = "doom_session"


VISITOR_COOKIE_NAME = "doom_visitor_id"


@dataclass
class Identity:
    is_owner: bool
    email: str | None = None
    visitor_key: str | None = None


def get_current_identity(request: Request) -> Identity:
    """FastAPI dependency: read the session cookie and resolve identity.

    Never raises — a missing, expired, or invalid owner cookie always
    resolves to is_owner=False, with a visitor_key so the non-owner still
    gets a stable identity across their turns (issued/refreshed as a
    cookie by the route itself, since only the route's actual Response
    object reliably carries Set-Cookie for a StreamingResponse).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_token(token)
    if payload is not None:
        return Identity(is_owner=True, email=payload.get("email"))

    visitor_key = request.cookies.get(VISITOR_COOKIE_NAME) or uuid.uuid4().hex
    return Identity(is_owner=False, visitor_key=visitor_key)