import os
import requests
from datetime import datetime
from typing import Optional

from src.memory.profile import ProfileManager

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_URL = f"https://{JSEARCH_HOST}/search-v2"

MONTHLY_CALL_CAP = 200
SAFETY_MARGIN = 20

PRIORITY_ROLES = [
    "AI Engineer",
    "Python Developer",
    "Software Engineer",
    "Backend Developer",
    "Full Stack Developer",
]

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
    p = ProfileManager()
    used = _get_call_count(p)
    return {"used": used, "cap": MONTHLY_CALL_CAP, "remaining": max(0, MONTHLY_CALL_CAP - used)}


def search_jobs(query: str, num_pages: int = 1, date_posted: str = "all", country: str = "in") -> Optional[list]:
    """Calls JSearch's /search-v2 endpoint. Returns normalized job dicts, or
    None if the key is missing, quota guard trips, or the call fails.

    NOTE: response field names below are copied from JSearch's v1 /search
    docs. If v2 renames fields, the raw job.get(...) calls will just come
    back empty/None and get filtered out silently below — run the raw-dump
    diagnostic after this change to confirm field names still match before
    trusting real results.
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

    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": JSEARCH_HOST, "Content-Type": "application/json"}
    params = {
        "query": query,
        "num_pages": str(num_pages),
        "date_posted": date_posted,
        "country": country,
    }

    try:
        resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=15)
        _increment_call_count(p)

        if resp.status_code == 429:
            print("[JSearch] 429 — RapidAPI reports quota exceeded.")
            return None
        if resp.status_code != 200:
            print(f"[JSearch] Unexpected status {resp.status_code}: {resp.text[:300]}")
            return None

        payload = resp.json() or {}
        data_block = payload.get("data") or {}
        raw_jobs = data_block.get("jobs", []) or []
        next_cursor = data_block.get("cursor")
        print(f"[JSearch] {len(raw_jobs)} jobs returned | cursor present: {next_cursor is not None}")

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