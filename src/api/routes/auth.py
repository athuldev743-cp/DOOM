from fastapi import APIRouter, Response, Request
from pydantic import BaseModel

from src.api.auth import verify_google_id_token, create_session_token, SESSION_MAX_AGE_SECONDS
from src.api.deps import SESSION_COOKIE_NAME, get_current_identity, Identity
from fastapi import Depends

router = APIRouter()


class GoogleSignInRequest(BaseModel):
    credential: str


@router.post("/auth/google")
async def google_sign_in(payload: GoogleSignInRequest, response: Response):
    idinfo = verify_google_id_token(payload.credential)

    if idinfo is None:
        # Don't reveal *why* it failed (wrong email vs bad token) — just
        # report that no session was created. No cookie is set either way.
        return {"status": "rejected"}

    name = idinfo.get("given_name") or idinfo.get("name") or ""
    token = create_session_token(idinfo["email"], name=name)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return {"status": "ok"}


@router.get("/auth/whoami")
async def whoami(identity: Identity = Depends(get_current_identity), request: Request = None):
    """Lets the frontend know, on page load, whether this browser already
    has a valid owner session (and their name) — used to drive the landing
    greeting without depending on Google's silent prompt firing."""
    if identity.is_owner:
        # decode_session_token already validated this cookie inside
        # get_current_identity — re-decode here just to surface the name,
        # which Identity itself doesn't currently carry.
        from src.api.auth import decode_session_token
        payload = decode_session_token(request.cookies.get(SESSION_COOKIE_NAME))
        name = payload.get("name") if payload else ""
        return {"is_owner": True, "name": name}
    return {"is_owner": False}