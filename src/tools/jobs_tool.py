import os
import json
import re
from src.tools.base import BaseTool
from src.tools.schemas import (
    ToolResult, JobSearchArgs, CoverLetterArgs, ScoreJDArgs,
    TrackApplicationArgs, ListApplicationsArgs,
)
from src.memory.profile import ProfileManager
from datetime import datetime, timedelta

from src.memory.database import SessionLocal, DailyJobMatch, SeenUrl, JobApplication


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


def _parse_job_metadata(description: str):
    """Remove scanner metadata from the description and expose location fields."""
    text = description or ""
    match = re.search(
        r"\n\n\[Job Location: (.*?); Remote: (.*?); Search Market: (.*?)\]\s*$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return text, "", False, ""
    clean_description = text[:match.start()].rstrip()
    location = match.group(1).strip()
    is_remote = match.group(2).strip().lower() == "yes"
    market = match.group(3).strip()
    return clean_description, location, is_remote, market


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
    description = "Show the next 20 highest-scoring entry-level AI, automation and Python backend jobs from the international daily scan."
    args_schema = JobSearchArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"query": raw.strip()}

    def run(self, query: str = "", limit: int = 20) -> ToolResult:
        """Returns the next 20 unseen matches from the daily international scan.
        This chat-facing tool never makes a live JSearch call.
        """
        try:
            db = SessionLocal()
            try:
                pool_matches = (
                    db.query(DailyJobMatch)
                    .filter(
                        DailyJobMatch.applied.is_(False),
                        DailyJobMatch.found_at >= datetime.utcnow() - timedelta(days=14),
                    )
                    .order_by(DailyJobMatch.score.desc())
                    .limit(limit)
                    .all()
                )

                if not pool_matches:
                    return ToolResult(
                        success=False,
                        message="No new matches are available right now — the international scanner refreshes the pool daily.",
                    )

                jobs = []
                for i, m in enumerate(pool_matches):
                    clean_description, location, is_remote, market = _parse_job_metadata(m.description or "")
                    application = db.query(JobApplication).filter_by(job_id=m.id).first()
                    if application is None:
                        application = JobApplication(
                            job_id=m.id, job_url=m.url, title=m.title or "",
                            company=m.company or "", description=clean_description,
                            source=m.source, status="discovered",
                        )
                        db.add(application)
                        db.flush()
                    jobs.append({
                        "id": f"job_{i}",
                        "db_id": m.id,
                        "application_id": application.id,
                        "application_status": application.status,
                        "cv_url": f"/api/jobs/{m.id}/cv" if application.cv_path else None,
                        "cover_letter": application.cover_letter,
                        "recipient_email": application.recipient_email,
                        "opened_at": application.opened_at.isoformat() if application.opened_at else None,
                        "index": i,
                        "title": m.title,
                        "company": m.company,
                        "snippet": clean_description[:200],
                        "description": clean_description,
                        "location": location,
                        "is_remote": is_remote,
                        "market": market,
                        "url": m.url,
                        "platform": m.source,
                        "auto_apply": JOB_PLATFORMS.get(m.source, {}).get("auto_apply", False),
                        "score": m.score,
                    })

                # Persist newly created application rows before closing the session.
                db.commit()

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
    description = "Generate a factual cover letter from the master resume, tailored by job requirements."
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
            from src.tools.resume_builder import generate_cover_letter
            letter = generate_cover_letter(role or "Software Engineer", company or "your company", jd or "")
            return ToolResult(success=True, message=letter)
        except Exception as exc:
            return ToolResult(success=False, message=f"Cover letter generation error: {str(exc)}")


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
    description = "List applications stored in the reviewed application tracker"
    args_schema = ListApplicationsArgs

    def run(self) -> ToolResult:
        db = SessionLocal()
        try:
            records = db.query(JobApplication).order_by(JobApplication.created_at.desc()).limit(100).all()
            if not records:
                return ToolResult(success=True, message="No applications tracked yet.")
            lines = [
                f"• {item.title} at {item.company} — {item.status}"
                for item in records
            ]
            data = [{
                "job_id": item.job_id,
                "title": item.title,
                "company": item.company,
                "status": item.status,
                "job_url": item.job_url,
                "cv_available": bool(item.cv_content),
                "cv_url": f"/api/jobs/{item.job_id}/cv" if item.cv_content else None,
            } for item in records]
            return ToolResult(
                success=True,
                message=f"📋 Job Applications ({len(records)} total):\n\n" + "\n".join(lines),
                data={"applications": data},
            )
        except Exception as exc:
            return ToolResult(success=False, message=f"List error: {str(exc)}")
        finally:
            db.close()
