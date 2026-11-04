import sys
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.database import SessionLocal, SeenUrl, DailyJobMatch, JobApplication, init_db
from src.memory.profile import ProfileManager
from src.tools.jobs_tool import _load_applied_keys, _is_already_applied
from src.tools.jsearch_client import search_jobs, build_combined_query
from src.tools.job_scoring import score_job

MAX_POOL_SIZE = 50  # keep the rolling pool capped — trim lowest-scored when exceeded


def run_scan():
    init_db()
    db = SessionLocal()
    p = ProfileManager()
    applied_keys = _load_applied_keys(p)

    # Keep application history, but expire stored PDF bytes 30 days after
    # a completed application. Active and pending applications are preserved.
    cutoff = datetime.utcnow() - timedelta(days=30)
    expired_count = 0
    for application in db.query(JobApplication).filter(JobApplication.cv_content.isnot(None)).all():
        closed_dates = [value for value in (application.submitted_at, application.email_sent_at) if value]
        if closed_dates and max(closed_dates) < cutoff:
            application.cv_content = None
            application.cv_path = None
            expired_count += 1
    if expired_count:
        db.commit()
        print(f"[Cleanup] Expired {expired_count} completed application PDFs older than 30 days.")

    # Remove orphaned temporary PDFs left by interrupted generation.
    temp_cv_dir = PROJECT_ROOT / "data" / "generated_cvs"
    if temp_cv_dir.exists():
        stale_before = datetime.utcnow() - timedelta(days=1)
        for temp_file in temp_cv_dir.glob("*.pdf"):
            if datetime.utcfromtimestamp(temp_file.stat().st_mtime) < stale_before:
                temp_file.unlink(missing_ok=True)

    existing_urls = {u.url for u in db.query(SeenUrl.url).all()}
    new_count = 0

    try:
        query = build_combined_query()  # nationwide — no location targeting
        live_jobs = search_jobs(query, num_pages=1) or []
        print(f"[Scan] JSearch returned {len(live_jobs)} jobs for '{query}'")

        now = datetime.utcnow()
        for job in live_jobs:
            url = job["url"]
            if not url or url in existing_urls:
                continue
            existing_urls.add(url)

            company = job["company"]
            title = job["title"]
            description = job["description"]

            if _is_already_applied(company, title, applied_keys):
                continue

            db.add(SeenUrl(url=url, first_seen=now))
            db.add(DailyJobMatch(
                url=url, title=title, company=company,
                description=description, source=job["platform"],
                score=score_job(title, description),
                sent=False, applied=False,
            ))
            new_count += 1

        db.commit()
        print(f"[Scan] Done. {new_count} new matches added.")

        unsent = db.query(DailyJobMatch).filter_by(applied=False).order_by(DailyJobMatch.score.desc()).all()
        if len(unsent) > MAX_POOL_SIZE:
            to_drop = unsent[MAX_POOL_SIZE:]
            for job in to_drop:
                db.delete(job)
            db.commit()
            print(f"[Scan] Pool exceeded {MAX_POOL_SIZE} — dropped {len(to_drop)} lowest-scored matches.")

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    run_scan()