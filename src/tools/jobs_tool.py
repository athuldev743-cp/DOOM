import os
import json
from src.tools.base import BaseTool
from src.tools.schemas import (
    ToolResult, JobSearchArgs, CoverLetterArgs, ScoreJDArgs,
    TrackApplicationArgs, ListApplicationsArgs,
)
from src.memory.profile import ProfileManager
from datetime import datetime

from src.memory.database import SessionLocal, DailyJobMatch, SeenUrl


def _load_applied_keys(p: ProfileManager) -> set:
    """Build a set of (company, role) pairs already applied to — used by
    scan_jobs.py to avoid re-adding jobs you've already gone after."""
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


def _mark_pool_job_applied(url: str) -> None:
    """Flips the matching DailyJobMatch row so it drops out of future
    'find jobs' pool listings once you've acted on it (emailed or
    clicked through to apply). Pool jobs otherwise stay visible across
    repeated 'find jobs' calls indefinitely."""
    if not url:
        return
    db = SessionLocal()
    try:
        match = db.query(DailyJobMatch).filter_by(url=url).first()
        if match:
            match.applied = True
            db.commit()
    finally:
        db.close()


JOB_PLATFORMS = {
    "naukri": {"domain": "naukri.com", "auto_apply": True},
    "wellfound": {"domain": "wellfound.com", "auto_apply": True},
    "indeed": {"domain": "indeed.com", "auto_apply": False},
    "linkedin": {"domain": "linkedin.com", "auto_apply": False},
    "glassdoor": {"domain": "glassdoor.com", "auto_apply": False},
    "ziprecruiter": {"domain": "ziprecruiter.com", "auto_apply": False},
    "monster": {"domain": "monster.com", "auto_apply": False},
    "web": {"domain": "", "auto_apply": False},
}


def get_locations(p: ProfileManager) -> list:
    """Kept for backward compatibility — no longer used by scan_jobs.py
    now that scans are nationwide, but left here in case anything else
    references it."""
    raw = p.get('location') or 'Kochi Kerala'
    return [loc.strip() for loc in raw.split(',') if loc.strip()]


class JobSearchTool(BaseTool):
    name = "job_search"
    description = "Show all currently open jobs in the pool (populated by the scheduled scanner) — no live search call, just reads what's already been found."
    args_schema = JobSearchArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"query": raw.strip()}

    def run(self, query: str = "", limit: int = 50) -> ToolResult:
        """Serves the entire current job pool. The pool is built exclusively
        by the scheduled scan_jobs.py scanner (6x/day) — this tool never
        makes its own JSearch call, so 'find jobs' costs zero API quota no
        matter how many times it's called. Jobs stay visible across repeated
        calls until marked applied (via _mark_pool_job_applied) or dropped
        by the scanner's score-based pool trim.
        """
        try:
            db = SessionLocal()
            try:
                pool_matches = (
                    db.query(DailyJobMatch)
                    .filter_by(applied=False)
                    .order_by(DailyJobMatch.score.desc())
                    .limit(limit)
                    .all()
                )

                if not pool_matches:
                    return ToolResult(
                        success=False,
                        message="No jobs in the pool right now — the scanner runs several times a day, check back soon.",
                    )

                jobs = []
                for i, m in enumerate(pool_matches):
                    jobs.append({
                        "id": f"job_{i}",
                        "index": i,
                        "title": m.title,
                        "company": m.company,
                        "snippet": (m.description or "")[:200],
                        "description": m.description or "",
                        "url": m.url,
                        "platform": m.source,
                        "auto_apply": JOB_PLATFORMS.get(m.source, {}).get("auto_apply", False),
                        "score": m.score,
                    })

                p = ProfileManager()
                p.set("latest_job_search", json.dumps(jobs), "career")

                platform_counts = {}
                for job in jobs:
                    plat = job["platform"]
                    platform_counts[plat] = platform_counts.get(plat, 0) + 1

                return ToolResult(
                    success=True,
                    message=f"Found {len(jobs)} jobs.",
                    data={"jobs": jobs, "platform_counts": platform_counts},
                    prefix="JOBS_DATA",
                )
            finally:
                db.close()

        except Exception as e:
            print(f"[JobSearch] ERROR: {e}")
            return ToolResult(success=False, message=f"Job search error: {str(e)}")


def apply_to_single_job(index: int) -> dict:
    """Manual platform apply — user clicks through to the real listing.
    Called directly by the /api/apply-single-job route, NOT through the
    agent's tool dispatch — so it's outside the args_schema/ToolResult
    refactor and keeps returning a plain dict."""
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
    _mark_pool_job_applied(url)

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
    if result.success:
        _mark_pool_job_applied(job.get("url", ""))
    return {"success": result.success, "message": result.message}


class CoverLetterTool(BaseTool):
    name = "cover_letter"
    description = "Generate a highly tailored LLM-driven application email mapping projects to the full job description."
    args_schema = CoverLetterArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
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