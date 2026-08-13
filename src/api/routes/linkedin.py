from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/linkedin/auth")
async def linkedin_auth():
    from src.tools.linkedin_tool import get_auth_url
    return RedirectResponse(get_auth_url())


@router.get("/linkedin/callback")
async def linkedin_callback(code: str = None, error: str = None):
    from src.tools.linkedin_tool import exchange_code, save_token, get_profile

    if error:
        return HTMLResponse(f"<h2>❌ LinkedIn auth failed: {error}</h2>")

    if not code:
        return HTMLResponse("<h2>❌ No code received</h2>")

    try:
        token_data = exchange_code(code)
        save_token(token_data)

        profile = get_profile(token_data["access_token"])
        name = profile.get("name", "")

        from src.memory.profile import ProfileManager

        p = ProfileManager()
        p.set("linkedin_name", name, "linkedin")
        p.set("linkedin_email", profile.get("email", ""), "linkedin")

        return HTMLResponse(f"""
        <html>
        <body style="background:#080808;color:#e8e8e8;font-family:sans-serif;
                     display:flex;align-items:center;justify-content:center;height:100vh;">
          <div style="text-align:center">
            <h1 style="color:#ff3333">DOOM</h1>
            <h2>✅ LinkedIn Connected!</h2>
            <p>Welcome {name}</p>
            <p style="color:#555">You can close this tab and return to DOOM.</p>
          </div>
        </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h2>❌ Error: {str(e)}</h2>")


@router.get("/linkedin/status")
async def linkedin_status():
    from src.tools.linkedin_tool import get_token, get_profile

    token = get_token()
    if not token:
        return {"connected": False, "auth_url": "/linkedin/auth"}

    try:
        profile = get_profile(token)
        return {"connected": True, "name": profile.get("name", "")}
    except Exception:
        return {"connected": False, "auth_url": "/linkedin/auth"}