import os
import sys
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ddgs import DDGS
from src.memory.database import SessionLocal, SeenUrl, DailyJobMatch, init_db
from src.memory.profile import ProfileManager
from src.tools.jobs_tool import (
    JobSearchTool, detect_platform, is_real_listing_url,
    extract_jsonld_jobposting, JOB_PLATFORMS,
    _load_applied_keys, _is_already_applied,
)
from src.tools.company_extract import extract_company
from src.tools.job_scoring import score_job
from src.tools.jobs_tool import get_locations

ROLE_QUERIES = [
    "AI Engineer", "Software Engineer", "AI Architect",
    "Backend Developer", "Full Stack Developer",
]
MAX_POOL_SIZE = 50  # keep the rolling pool capped — trim lowest-scored when exceeded



def run_scan():
    init_db()
    db = SessionLocal()
    p = ProfileManager()
    locations = get_locations(p)
    applied_keys = _load_applied_keys(p)
    tool = JobSearchTool()

    # Rotate through locations by hour-of-day, so 7 locations still get
    # full coverage across 24 hourly runs without multiplying query volume
    current_location = locations[datetime.utcnow().hour % len(locations)]
    print(f"[Scan] This hour's location: {current_location}")

    existing_urls = {u.url for u in db.query(SeenUrl.url).all()}
    new_count = 0

    try:
        with DDGS() as ddgs:
            for role in ROLE_QUERIES:
                platform_queries = [
                    (f'site:naukri.com/job-listings "{role}" {current_location}', "naukri"),
                    (f'site:indeed.com "{role}" {current_location}', "indeed"),
                    (f'site:linkedin.com/jobs/view "{role}" {current_location}', "linkedin"),
                    (f'site:wellfound.com/jobs "{role}"', "wellfound"),
                ]

               

                for query, expected_platform in platform_queries:
                    try:
                        time.sleep(1.5)  # pace requests, avoid DDG throttling
                        results = list(ddgs.text(query, max_results=10))
                        print(f"[Scan] '{query}' -> {len(results)} raw results")

                        for r in results:
                            url = r.get("href", "")
                            title = r.get("title", "")
                            body = r.get("body", "")

                            if not url or url in existing_urls:
                                continue
                            existing_urls.add(url)

                            platform = detect_platform(url)
                            if platform != expected_platform:
                                continue
                            if not is_real_listing_url(url, platform):
                                continue

                            if platform in JobSearchTool.NO_FETCH_PLATFORMS:
                                jsonld = {}
                                description = body
                            else:
                                page_data = tool._fetch_page(url)
                                jsonld = page_data["jsonld"]
                                description = page_data["description"] if len(page_data["description"]) > 200 else body

                            company = jsonld.get("company") or extract_company(title, platform)
                            final_title = jsonld.get("title") or title

                            if not company:
                                continue
                            if final_title.lower().count(" at ") >= 2:
                                continue
                            if _is_already_applied(company, final_title, applied_keys):
                                continue

                            desc_lower = description.lower()
                            if any(m in desc_lower for m in JobSearchTool.BROKEN_MARKERS):
                                continue

                            db.add(SeenUrl(url=url))
                            db.add(DailyJobMatch(
                                url=url, title=final_title, company=company,
                                description=description, source=platform,
                                score=score_job(final_title, description),
                                sent=False, applied=False,
                            ))
                            new_count += 1

                    except Exception as e:
                        print(f"[Scan Error] '{query}': {e}")

        db.commit()
        print(f"[Scan] Done. {new_count} new matches added.")

        # Compare/replace — keep only the top MAX_POOL_SIZE-scored unsent jobs
        unsent = db.query(DailyJobMatch).filter_by(sent=False).order_by(DailyJobMatch.score.desc()).all()
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