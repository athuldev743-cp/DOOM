import os
import json
import requests
from ddgs import DDGS
from bs4 import BeautifulSoup
from src.tools.base import BaseTool
from src.tools.schemas import (
    ToolResult, JobSearchArgs, CoverLetterArgs, ScoreJDArgs,
    TrackApplicationArgs, ListApplicationsArgs,
)
from src.memory.profile import ProfileManager
import re
from src.tools.company_extract import extract_company
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from src.memory.database import SessionLocal, DailyJobMatch, SeenUrl


def _load_applied_keys(p: ProfileManager) -> set:
    """Build a set of (company, role) pairs already applied to, so job_search can exclude them."""
    history_raw = p.get("application_history") or "[]"
    try:
        records = json.loads(history_raw)
    except Exception:
        records = []
    applied = set()
    for r in records:
        if str(r.get("status", "")).lower() != "applied":
            continue
        company = (r.get("company") or "").strip().lower()
        role = (r.get("role") or "").strip().lower()
        if company:
            applied.add((company, role))
    return applied


def _is_already_applied(company: str, title: str, applied_keys: set) -> bool:
    company_norm = (company or "").strip().lower()
    title_norm = (title or "").strip().lower()
    if not company_norm:
        return False
    for (a_company, a_role) in applied_keys:
        if a_company != company_norm:
            continue
        if not a_role or a_role in title_norm or title_norm in a_role:
            return True
    return False


JOB_PLATFORMS = {
    "naukri": {"domain": "naukri.com", "auto_apply": True},
    "wellfound": {"domain": "wellfound.com", "auto_apply": True},
    "indeed": {"domain": "indeed.com", "auto_apply": False},
    "linkedin": {"domain": "linkedin.com", "auto_apply": False},
}


def detect_platform(url: str) -> str:
    url = (url or "").lower()
    for platform, info in JOB_PLATFORMS.items():
        if info["domain"] in url:
            return platform
    return "web"


def is_real_listing_url(url: str, platform: str) -> bool:
    """Excludes category/landing/marketing pages that match a site: search
    but aren't an actual individual job posting."""
    url = (url or "").lower()

    if platform == "wellfound":
        return bool(re.search(r'wellfound\.com/jobs/(\d+)', url))
    if platform == "naukri":
        return bool(re.search(r'-\d{6,}$', url.split('?')[0]))
    if platform == "indeed":
        return any(marker in url for marker in ["/rc/clk", "/viewjob", "jk="])
    if platform == "linkedin":
        return bool(re.search(r'linkedin\.com/jobs/view/[\w-]*\d{6,}', url))


def extract_jsonld_jobposting(html: str) -> dict:
    """Parse Schema.org JobPosting structured data — the source these sites
    embed for Google's job search, and far more reliable than title-string
    parsing when present. Returns {} if no structured data found."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                candidates = data if isinstance(data, list) else [data]
                for item in candidates:
                    if item.get("@type") == "JobPosting":
                        org = item.get("hiringOrganization", {})
                        company = org.get("name") if isinstance(org, dict) else None
                        role_title = item.get("title")
                        return {
                            "company": (company or "").strip(),
                            "title": (role_title or "").strip(),
                        }
            except Exception:
                continue
    except Exception:
        pass
    return {}


def get_locations(p: ProfileManager) -> list:
    """Location is stored as a comma-separated string so multiple target
    locations (e.g. 'Kochi Kerala, NYC') all get searched, not just the last one set."""
    raw = p.get('location') or 'Kochi Kerala'
    return [loc.strip() for loc in raw.split(',') if loc.strip()]


class JobSearchTool(BaseTool):
    name = "job_search"
    description = "Search only real, previously-unseen job postings on Naukri, Wellfound, Indeed, LinkedIn"
    args_schema = JobSearchArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        # The LLM sends a plain query string, e.g. "backend developer Kochi"
        return {"query": raw.strip()}

    BROKEN_MARKERS = [
        "we cannot provide a description",
        "you don't have permission to access",
        "reference #",
        "the site owner hides",
    ]
    NO_FETCH_PLATFORMS = {"naukri", "indeed"}

    def _fetch_page(self, url: str) -> dict:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                return {"description": "", "jsonld": {}}
            raw_html = res.text
            jsonld = extract_jsonld_jobposting(raw_html)
            soup = BeautifulSoup(raw_html, "html.parser")
            for element in soup(["script", "style", "nav", "header", "footer", "form"]):
                element.decompose()
            text = " ".join(soup.stripped_strings)
            return {"description": text[:2500], "jsonld": jsonld}
        except Exception:
            return {"description": "", "jsonld": {}}

    def _collect_candidates(self, searches, applied_keys) -> list:
        """Phase 1: run all DDG searches, apply cheap filters (no network fetch yet).
        Returns a list of candidate dicts still needing a page fetch (or already resolved
        for NO_FETCH_PLATFORMS)."""
        from collections import defaultdict
        rejected = defaultdict(int)
        seen_urls = set()
        candidates = []

        with DDGS() as ddgs:
            for search_query, expected_platform in searches:
                try:
                    raw_results = list(ddgs.text(search_query, max_results=15))
                    print(f"[JobSearch] '{search_query}' -> {len(raw_results)} raw DDG results")
                    for r in raw_results:
                        url = r.get('href', '')
                        title = r.get('title', '')
                        body = r.get('body', '')

                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        platform = detect_platform(url)
                        if platform != expected_platform:
                            rejected["platform_mismatch"] += 1
                            print(f"[DEBUG mismatch] expected={expected_platform} got={platform} url={url}")
                            continue

                        if not is_real_listing_url(url, platform):
                            rejected["not_real_url"] += 1
                            print(f"[DEBUG not_real_url] platform={platform} url={url}")
                            continue

                        candidates.append({
                            "url": url, "title": title, "body": body, "platform": platform,
                        })
                except Exception as e:
                    print(f"[JobSearch] search failed for '{search_query}': {e}")
                    continue

        self._rejected = rejected
        return candidates

    def _resolve_candidate(self, c: dict, applied_keys):
        """Phase 2 per-candidate: does the (possibly concurrent) page fetch and
        applies the remaining filters. Returns a finished job dict, or None if rejected."""
        url, title, body, platform = c["url"], c["title"], c["body"], c["platform"]

        if platform in self.NO_FETCH_PLATFORMS:
            jsonld = {}
            description = body
        else:
            page_data = self._fetch_page(url)
            jsonld = page_data["jsonld"]
            description = page_data["description"] if len(page_data["description"]) > 200 else body

        company = jsonld.get("company") or extract_company(title, platform)
        final_title = jsonld.get("title") or title

        if not company:
            self._rejected["no_company"] += 1
            return None

        if final_title.lower().count(" at ") >= 2:
            self._rejected["duplicate_title"] += 1
            return None

        if _is_already_applied(company, final_title, applied_keys):
            self._rejected["already_applied"] += 1
            return None

        desc_lower = description.lower()
        if any(marker in desc_lower for marker in self.BROKEN_MARKERS):
            self._rejected["broken_page"] += 1
            return None

        return {
            "title": final_title,
            "company": company,
            "snippet": body,
            "description": description,
            "url": url,
            "platform": platform,
            "auto_apply": JOB_PLATFORMS.get(platform, {}).get("auto_apply", False),
        }

    def run(self, query: str = "", limit: int = 20) -> ToolResult:
        """Hybrid delivery: serves whatever's already in the pool (instant),
        then tops up with a LIVE search only for the shortfall if the pool
        has fewer than `limit` unsent jobs. Enforces a 24h cooldown between
        full deliveries.
        """
        try:
            p_check = ProfileManager()
            last_search_str = p_check.get("last_job_search_at")
            if last_search_str:
                try:
                    last_search_at = datetime.fromisoformat(last_search_str)
                    elapsed = datetime.utcnow() - last_search_at
                    if elapsed < timedelta(hours=24):
                        remaining = timedelta(hours=24) - elapsed
                        hours_left = int(remaining.total_seconds() // 3600)
                        minutes_left = int((remaining.total_seconds() % 3600) // 60)
                        return ToolResult(
                            success=True,
                            message=(
                                f"You already got today's batch of jobs. Next batch available in "
                                f"{hours_left}h {minutes_left}m — or check 'my applications' to review what's pending."
                            ),
                        )
                except Exception:
                    pass

            db = SessionLocal()

            try:
                pool_matches = (
                    db.query(DailyJobMatch)
                    .filter_by(sent=False)
                    .order_by(DailyJobMatch.score.desc())
                    .limit(limit)
                    .all()
                )

                jobs = []
                for m in pool_matches:
                    jobs.append({
                        "title": m.title,
                        "company": m.company,
                        "snippet": (m.description or "")[:200],
                        "description": m.description or "",
                        "url": m.url,
                        "platform": m.source,
                        "auto_apply": JOB_PLATFORMS.get(m.source, {}).get("auto_apply", False),
                        "score": m.score,
                    })
                    m.sent = True

                shortfall = limit - len(jobs)
                print(f"[JobSearch] Pool had {len(pool_matches)} unsent — shortfall of {shortfall}")

                if shortfall > 0:
                    p = ProfileManager()
                    applied_keys = _load_applied_keys(p)
                    locations = get_locations(p)

                    target_roles = (
                        query.strip() if query and query.strip()
                        else (p.get("target_roles") or "AI engineer software engineer backend fullstack developer")
                    )

                    searches = []
                    for location in locations[:1]:
                        searches.extend([
                            (f'site:naukri.com/job-listings "{target_roles}" {location}', "naukri"),
                            (f'site:wellfound.com/jobs "{target_roles}"', "wellfound"),
                            (f'site:indeed.com "{target_roles}" {location}', "indeed"),
                            (f'site:linkedin.com/jobs/view "{target_roles}" {location}', "linkedin"),
                        ])

                    candidates = self._collect_candidates(searches, applied_keys)

                    candidate_urls = [c["url"] for c in candidates if c.get("url")]
                    if candidate_urls:
                        already_seen = {
                            row.url for row in db.query(SeenUrl.url).filter(SeenUrl.url.in_(candidate_urls)).all()
                        }
                    else:
                        already_seen = set()
                    candidates = [c for c in candidates if c.get("url") not in already_seen]

                    resolved = []
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        futures = {
                            executor.submit(self._resolve_candidate, c, applied_keys): c for c in candidates
                        }
                        for future in as_completed(futures):
                            try:
                                result = future.result()
                                if result:
                                    resolved.append(result)
                                if len(resolved) >= shortfall:
                                    break
                            except Exception as e:
                                print(f"[JobSearch] Candidate resolution failed: {e}")
                                continue

                    top_up = resolved[:shortfall]
                    now = datetime.utcnow()

                    for job in top_up:
                        db.add(SeenUrl(url=job["url"], first_seen=now))
                        db.add(DailyJobMatch(
                            url=job["url"], title=job["title"], company=job["company"],
                            description=job["description"][:4000], source=job["platform"],
                            found_at=now, sent=True, applied=False,
                        ))
                        jobs.append({
                            "title": job["title"], "company": job["company"],
                            "snippet": job["description"][:200], "description": job["description"],
                            "url": job["url"], "platform": job["platform"],
                            "auto_apply": job["auto_apply"], "score": 0,
                        })

                    print(f"[JobSearch] Top-up added {len(top_up)} live-found jobs")

                db.commit()

                if not jobs:
                    return ToolResult(
                        success=False,
                        message="No jobs found right now, even after a live top-up search — try again shortly.",
                    )

                for i, job in enumerate(jobs):
                    job["id"] = f"job_{i}"
                    job["index"] = i

                p = ProfileManager()
                p.set("latest_job_search", json.dumps(jobs), "career")
                p.set("last_job_search_at", datetime.utcnow().isoformat(), "career")

                platform_counts = {}
                for job in jobs:
                    plat = job["platform"]
                    platform_counts[plat] = platform_counts.get(plat, 0) + 1

                print(f"[JobSearch] Returning {len(jobs)} jobs")
                return ToolResult(
                    success=True,
                    message=f"Found {len(jobs)} jobs.",
                    data={"jobs": jobs, "platform_counts": platform_counts},
                    prefix="JOBS_DATA",
                )

            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            print(f"[JobSearch] ERROR: {e}")
            return ToolResult(success=False, message=f"Job search error: {str(e)}")


def apply_to_single_job(index: int) -> dict:
    """Manual platform apply — user clicks through to the real listing.
    Called directly by the /api/apply-single-job route, NOT through the agent's
    tool dispatch — so it's outside the args_schema/ToolResult refactor and
    keeps returning a plain dict."""
    p = ProfileManager()
    latest = p.get("latest_job_search")
    if not latest:
        return {"success": False, "message": "No job search results found."}

    jobs = json.loads(latest)
    if index is None or not (0 <= index < len(jobs)):
        return {"success": False, "message": "Invalid job index."}

    job = jobs[index]
    company = job.get("company", "Hiring Company")
    title = job.get("title", "Developer")
    url = job.get("url", "")

    if not url:
        return {"success": False, "message": "No direct platform link available for this job."}

    TrackApplicationTool().run(company=company, role=title, status="applied")

    return {
        "success": True,
        "apply_url": url,
        "message": f"Marked applied — {title} at {company}",
    }


def email_only_for_job(index: int) -> dict:
    """Used by the 'Send Email' button — sends the resume email only.
    Also called directly by a route, not through the agent's tool dispatch."""
    p = ProfileManager()
    latest = p.get("latest_job_search")
    if not latest:
        return {"success": False, "message": "No job search results found."}

    jobs = json.loads(latest)
    if index is None or not (0 <= index < len(jobs)):
        return {"success": False, "message": "Invalid job index."}

    job = jobs[index]
    from src.tools.auto_apply_tool import AutoApplyTool
    result = AutoApplyTool().run(
        company=job.get("company", "Hiring Company"),
        role=job.get("title", "Developer"),
        job_index=index + 1,
        track=False,
    )
    return {"success": "✅" in result, "message": result}


class CoverLetterTool(BaseTool):
    name = "cover_letter"
    description = "Generate a highly tailored LLM-driven application email mapping projects to the full job description."
    args_schema = CoverLetterArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        # Today's format: "company | role" (jd is never sent via chat today)
        parts = raw.split("|")
        return {
            "company": parts[0].strip() if parts else "",
            "role": parts[1].strip() if len(parts) > 1 else "",
        }

    def run(self, company: str = "", role: str = "", jd: str = "") -> ToolResult:
        try:
            p = ProfileManager()
            name = p.get("name") or "Athul Dev"
            portfolio = p.get("portfolio") or "https://port-folio-phpa.vercel.app"
            github = p.get("github") or "https://github.com/athuldev743-cp"
            email = p.get("email") or "athuldev743@gmail.com"
            phone = p.get("phone") or "+91 70343 06102"
            projects = p.get_projects()

            try:
                import google.generativeai as genai
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel("gemini-2.5-flash")

                    prompt = f"""You are an elite software developer career assistant writing a highly tailored job application email for {name}.

Applicant Data:
- Name: {name}
- Email: {email}
- Phone: {phone}
- Links: Portfolio: {portfolio} | GitHub: {github}
- Stored Project Knowledge:
{json.dumps(projects, indent=2)}

Target Application Details:
- Target Company: {company if company else 'Hiring Team'}
- Target Role: {role if role else 'Full Stack / AI Developer'}
- Full Job Description Context:
\"\"\"
{jd if jd else 'Python, FastAPI, React, AI integrations, LLMs, WebSockets, Databases'}
\"\"\"

Formatting & Style Instructions:
1. Carefully analyze the Job Description Context. Identify key required skills (e.g., Python, FastAPI, React, AI/LLMs, RAG, WebSockets, Databases).
2. Directly map 2 to 3 relevant projects from {name}'s portfolio (DOOM AI Assistant, Instagram AI Agent, Ekabhumi) to those extracted requirements.
3. Keep the tone professional, direct, and technical.
4. Output structure:
   - Salutation & compelling opening statement.
   - Bulleted list of relevant projects showing technical impact matching the JD.
   - Brief closing alignment statement.
   - Clean professional signature ({name}, Email, Phone, Portfolio, GitHub).
5. DO NOT include email subject lines, bracketed placeholders like [Date], or conversational fluff outside the email text.
"""
                    response = model.generate_content(prompt)
                    if response and response.text:
                        return ToolResult(success=True, message=response.text.strip())
            except Exception as llm_err:
                print(f"[CoverLetterTool] LLM generation failed, switching to dynamic fallback: {llm_err}")

            fallback = f"""Dear Hiring Manager,

I am writing to express my strong interest in the {role if role else 'Full Stack AI Developer'} position at {company if company else 'your company'}.

As a Full Stack AI Developer specializing in Python, FastAPI, React, and autonomous AI systems, I build production-grade platforms that match your technical requirements:

- DOOM AI Assistant: Autonomous AI agent featuring tool-calling, RAG, WebSockets, persistent memory (PostgreSQL/ChromaDB), and Gmail API automation.
- Instagram AI Content Agent: Automated end-to-end media generation pipeline utilizing LLMs and the Instagram Graph API.
- Ekabhumi E-Commerce: Scalable e-commerce application built with React, FastAPI, Docker, and dual payment gateway integration (Razorpay & Worldline).

My background in high-throughput API architecture, vector databases, and full-stack engineering aligns directly with your engineering requirements.

Best regards,
{name}
📧 {email} | 📱 {phone}
🌐 Portfolio: {portfolio} | 💻 GitHub: {github}"""
            return ToolResult(success=True, message=fallback)

        except Exception as e:
            return ToolResult(success=False, message=f"Cover letter generation error: {str(e)}")


class ScoreJDTool(BaseTool):
    name = "score_jd"
    description = "Score a job description against Athul's resume and skills"
    args_schema = ScoreJDArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"jd": raw}

    def run(self, jd: str = "") -> ToolResult:
        try:
            p = ProfileManager()
            skills = p.get("skills") or "React, Python, FastAPI, PostgreSQL, MongoDB, Docker, LLM"
            jd_lower = jd.lower()

            skill_list = [s.strip().lower() for s in skills.split(",") if s.strip()]
            matched = [s for s in skill_list if s in jd_lower]
            missing = [s for s in skill_list if s not in jd_lower]
            score = int((len(matched) / len(skill_list)) * 100) if skill_list else 50

            return ToolResult(
                success=True,
                message=f"📊 Match Score: {score}%\nMatched: {', '.join(matched)}\nMissing: {', '.join(missing)}",
                data={"score": score, "matched": matched, "missing": missing},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Score error: {str(e)}")


class TrackApplicationTool(BaseTool):
    name = "track_application"
    description = "Record applied job to persistent tracking memory."
    args_schema = TrackApplicationArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        parts = raw.split("|")
        return {
            "company": parts[0].strip() if parts else "",
            "role": parts[1].strip() if len(parts) > 1 else "",
            "status": parts[2].strip() if len(parts) > 2 else "applied",
        }

    def run(self, company: str = "", role: str = "", status: str = "applied") -> ToolResult:
        try:
            p = ProfileManager()
            history = p.get("application_history") or "[]"
            try:
                records = json.loads(history)
            except Exception:
                records = []

            records.append({
                "company": company,
                "role": role,
                "status": status
            })
            p.set("application_history", json.dumps(records))
            return ToolResult(success=True, message=f"Recorded application for {role} at {company}.")
        except Exception as e:
            return ToolResult(success=False, message=f"Tracking error: {str(e)}")


class ListApplicationsTool(BaseTool):
    name = "list_applications"
    description = "List all tracked job applications"
    args_schema = ListApplicationsArgs

    def run(self) -> ToolResult:
        try:
            p = ProfileManager()
            existing = p.get("application_history")
            if not existing:
                return ToolResult(success=True, message="No applications tracked yet.")
            apps = json.loads(existing)
            if not apps:
                return ToolResult(success=True, message="No applications tracked yet.")
            listing = f"📋 Job Applications ({len(apps)} total):\n\n" + "\n".join(
                [f"• {a.get('role')} at {a.get('company')} ({a.get('status')})" for a in apps]
            )
            return ToolResult(success=True, message=listing, data={"applications": apps})
        except Exception as e:
            return ToolResult(success=False, message=f"List error: {str(e)}")