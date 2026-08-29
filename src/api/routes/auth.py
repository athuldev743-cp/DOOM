from fastapi import APIRouter, Response
from pydantic import BaseModel

from src.api.auth import verify_google_id_token, create_session_token, SESSION_MAX_AGE_SECONDS
from src.api.deps import SESSION_COOKIE_NAME

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

    token = create_session_token(idinfo["email"])
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return {"status": "ok"}