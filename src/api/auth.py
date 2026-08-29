import os
import time

import jwt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
SESSION_SECRET = os.getenv("SESSION_SECRET")
OWNER_EMAIL = "athuldev743@gmail.com"
SESSION_ALGORITHM = "HS256"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 180  # 180 days

_google_request = google_requests.Request()


def verify_google_id_token(token: str) -> dict | None:
    """Verify a Google ID token server-side and confirm it belongs to the owner.

    Returns the decoded token payload only if the signature/audience/expiry
    check passes AND the email matches the single authorized owner exactly.
    Never raises to the caller — any failure just returns None, which the
    route treats as "no session created."
    """
    if not GOOGLE_CLIENT_ID:
        print("[auth] GOOGLE_CLIENT_ID is not set — refusing to verify")
        return None

    try:
        idinfo = id_token.verify_oauth2_token(
            token, _google_request, GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        # Covers bad signature, expired token, wrong audience, malformed token
        print(f"[auth] Google token verification failed: {e}")
        return None

    if idinfo.get("email") != OWNER_EMAIL or not idinfo.get("email_verified"):
        print(f"[auth] Rejected sign-in from non-owner email: {idinfo.get('email')}")
        return None

    return idinfo


def create_session_token(email: str) -> str:
    """Issue DOOM's own signed session token, used after Google verification
    succeeds so we don't have to re-verify a Google token on every request."""
    if not SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET is not set")

    now = int(time.time())
    payload = {
        "email": email,
        "is_owner": True,
        "iat": now,
        "exp": now + SESSION_MAX_AGE_SECONDS,
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm=SESSION_ALGORITHM)


def decode_session_token(token: str | None) -> dict | None:
    """Decode and validate DOOM's own session token. Returns None on any
    failure — missing cookie, expired token, bad signature, wrong email."""
    if not token or not SESSION_SECRET:
        return None

    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=[SESSION_ALGORITHM])
    except jwt.PyJWTError as e:
        print(f"[auth] Session token invalid: {e}")
        return None

    if payload.get("email") != OWNER_EMAIL or not payload.get("is_owner"):
        return None

    return payload


HR_FALLBACK_RESPONSE = (
    "Hi, I'm DOOM — Athul Dev's personal AI system, currently gated to "
    "owner-only access for chat features.\n\n"
    "While I can't answer questions on his behalf here, this project "
    "demonstrates: a custom multi-provider LLM fallback chain across 4 "
    "providers and 14 models, 35+ integrated tools spanning job search "
    "automation, WhatsApp/email integration, and PC automation, a "
    "PostgreSQL-backed memory system, ChromaDB retrieval-augmented search, "
    "and full observability via Langfuse tracing.\n\n"
    "If you're a recruiter or hiring manager, reach Athul directly at "
    "athuldev743@gmail.com."
)