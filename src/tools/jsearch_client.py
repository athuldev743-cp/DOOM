import os
import requests
from datetime import datetime
from typing import Optional

from src.memory.profile import ProfileManager

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_URL = f"https://{JSEARCH_HOST}/search"

# RapidAPI's free JSearch tier is hard-capped at 200 requests/month.
# SAFETY_MARGIN keeps us from ever bumping the actual ceiling — once we're
# this close, calls are skipped rather than risking a 429 mid-run.
MONTHLY_CALL_CAP = 200
SAFETY_MARGIN = 20

# Priority-ordered role terms — AI Engineer / Python Developer / Software
# Engineer come first in the combined query string since JSearch has no
# explicit weighting param; term order is the only lever we have.
PRIORITY_ROLES = [
    "AI Engineer",
    "Python Developer",
    "Software Engineer",
    "Backend Developer",
    "Full Stack Developer",
]

# job_publisher values JSearch returns -> our internal platform tag.
PUBLISHER_PLATFORM_MAP = {
    "naukri": "naukri",
    "wellfound": "wellfound",
    "angellist": "wellfound",
    "indeed": "indeed",
    "linkedin": "linkedin",
    "glassdoor": "glassdoor",
    "ziprecruiter": "ziprecruiter",
    "monster": "monster",
}
AUTO_APPLY_PLATFORMS = {"naukri", "wellfound"}


def build_combined_query(location: str) -> str:
    """One query string covering every priority role, so a full scan costs
    a single JSearch call instead of one per role."""
    roles_clause = " OR ".join(PRIORITY_ROLES)
    return f"{roles_clause} in {location}"


def detect_platform_from_publisher(publisher: str) -> str:
    publisher_lower = (publisher or "").lower()
    for key, platform in PUBLISHER_PLATFORM_MAP.items():
        if key in publisher_lower:
            return platform
    return "web"


def _usage_key_for_month() -> str:
    return f"jsearch_calls_{datetime.utcnow().strftime('%Y_%m')}"


def _get_call_count(p: ProfileManager) -> int:
    raw = p.get(_usage_key_for_month())
    try:
        return int(raw) if raw else 0
    except (TypeError, ValueError):
        return 0


def _increment_call_count(p: ProfileManager) -> int:
    count = _get_call_count(p) + 1
    p.set(_usage_key_for_month(), str(count), "system")
    return count


def get_usage() -> dict:
    """Diagnostics — how much of this month's free quota has been used."""
    p = ProfileManager()
    used = _get_call_count(p)
    return {"used": used, "cap": MONTHLY_CALL_CAP, "remaining": max(0, MONTHLY_CALL_CAP - used)}


def search_jobs(query: str, num_pages: int = 1, date_posted: str = "week") -> Optional[list]:
    """Calls JSearch and returns a list of normalized job dicts:
    {title, company, description, snippet, url, platform, auto_apply}

    Returns None (not an exception) if the key is missing, the quota guard
    trips, or the call fails — callers should treat None the same as
    "no new jobs this round," never as a crash condition.
    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        print("[JSearch] RAPIDAPI_KEY not set — skipping live job search.")
        return None

    p = ProfileManager()
    used = _get_call_count(p)
    if used >= MONTHLY_CALL_CAP - SAFETY_MARGIN:
        print(f"[JSearch] Quota guard tripped ({used}/{MONTHLY_CALL_CAP}) — skipping call.")
        return None

    headers = {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": JSEARCH_HOST}
    params = {"query": query, "page": "1", "num_pages": str(num_pages), "date_posted": date_posted}

    try:
        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=15)
        _increment_call_count(p)

        if resp.status_code == 429:
            print("[JSearch] 429 — RapidAPI reports quota exceeded.")
            return None
        if resp.status_code != 200:
            print(f"[JSearch] Unexpected status {resp.status_code}: {resp.text[:300]}")
            return None

        raw_jobs = (resp.json() or {}).get("data", []) or []
        normalized = []
        for job in raw_jobs:
            url = job.get("job_apply_link") or job.get("job_google_link") or ""
            title = (job.get("job_title") or "").strip()
            company = (job.get("employer_name") or "").strip()
            description = (job.get("job_description") or "").strip()

            if not url or not title or not company:
                continue

            platform = detect_platform_from_publisher(job.get("job_publisher", ""))
            normalized.append({
                "title": title,
                "company": company,
                "description": description[:4000],
                "snippet": description[:200],
                "url": url,
                "platform": platform,
                "auto_apply": platform in AUTO_APPLY_PLATFORMS,
            })

        return normalized

    except Exception as e:
        print(f"[JSearch] Request failed: {e}")
        return None