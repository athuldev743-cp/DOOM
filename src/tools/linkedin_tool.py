import os
import requests
from src.tools.base import BaseTool
from src.memory.profile import ProfileManager

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/linkedin/callback"
SCOPES = "openid profile email"

def get_auth_url():
    return (
        f"https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code"
        f"&client_id={LINKEDIN_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPES.replace(' ', '%20')}"
    )

def exchange_code(code: str) -> dict:
    res = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": LINKEDIN_CLIENT_ID,
            "client_secret": LINKEDIN_CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    return res.json()

def get_profile(access_token: str) -> dict:
    res = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    return res.json()

def save_token(token_data: dict):
    p = ProfileManager()
    p.set("linkedin_access_token", token_data.get("access_token", ""), "linkedin")
    p.set("linkedin_token_expires", str(token_data.get("expires_in", 0)), "linkedin")

def get_token() -> str:
    p = ProfileManager()
    return p.get("linkedin_access_token") or ""

class LinkedInProfileTool(BaseTool):
    name = "linkedin_profile"
    description = "Get Athul's LinkedIn profile info"

    def run(self) -> str:
        try:
            token = get_token()
            if not token:
                return "LINKEDIN_AUTH_REQUIRED"
            profile = get_profile(token)
            name = profile.get("name", "")
            email = profile.get("email", "")
            picture = profile.get("picture", "")
            return f"LinkedIn Profile:\nName: {name}\nEmail: {email}"
        except Exception as e:
            return f"LinkedIn error: {str(e)}"

class LinkedInJobSearchTool(BaseTool):
    name = "linkedin_jobs"
    description = "Search LinkedIn jobs for Athul"

    def run(self, query: str = "") -> str:
        try:
            from ddgs import DDGS
            p = ProfileManager()
            location = p.get('location') or 'Kochi Kerala'
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(
                    f"site:linkedin.com/jobs {query} {location}",
                    max_results=5
                ):
                    title = r.get('title', '')
                    url = r.get('href', '')
                    body = r.get('body', '')[:200]
                    results.append(f"🏢 {title}\n🔗 {url}\n📝 {body}")

            if not results:
                url = f"https://www.linkedin.com/jobs/search/?keywords={query.replace(' ', '%20')}&location=Kochi"
                return f"No results found. Search directly:\n{url}"

            return "LinkedIn Jobs:\n\n" + "\n\n---\n\n".join(results[:5])
        except Exception as e:
            return f"LinkedIn jobs error: {str(e)}"