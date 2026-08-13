import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.database import SessionLocal, DailyJobMatch, init_db
from src.tools.auto_apply_tool import AutoApplyTool
from src.tools.whatsapp_api_tool import WhatsAppSendTool
from src.memory.profile import ProfileManager

MAX_APPLIES_PER_DAY = 15  # safety cap — keeps activity pattern human-like


def run_digest():
    init_db()
    db = SessionLocal()
    p = ProfileManager()

    try:
        # Highest-scored jobs first — these are the ones that should
        # consume the daily apply cap, not whatever order the DB returns
        matches = db.query(DailyJobMatch).filter_by(sent=False).order_by(DailyJobMatch.score.desc()).all()
        if not matches:
            print("[Digest] No new matches to process.")
            return

        applied, skipped = 0, 0
        summary_lines = [f"📋 Morning Job Digest — {len(matches)} matches (top-scored first)\n"]
        auto_apply = AutoApplyTool()

        for job in matches:
            if applied < MAX_APPLIES_PER_DAY:
                result = auto_apply.run(
                    company=job.company,
                    role=job.title,
                    jd=job.description,  # actual scanned JD — real cover-letter context now
                )
                success = "✅" in result
                if success:
                    applied += 1
                    job.applied = True
                    summary_lines.append(f"✅ Applied ({job.score}%) — {job.title} @ {job.company}")
                else:
                    skipped += 1
                    # No verified email found — hand back the real listing URL so
                    # this is actually actionable, not just a dead-end notification
                    summary_lines.append(f"⏭️ No email found ({job.score}%) — {job.title} @ {job.company}\n   {job.url}")
            else:
                # Over today's cap — still worth surfacing with the link for manual follow-up
                summary_lines.append(f"ℹ️ Not sent today ({job.score}%) — {job.title} @ {job.company}\n   {job.url}")

            job.sent = True
            db.commit()

        summary_lines.append(f"\n📊 {applied} applied, {skipped} no-email, {len(matches) - applied - skipped} deferred")
        summary_text = "\n".join(summary_lines)

        my_name = p.get("whatsapp_self_name") or "Athul"
        WhatsAppSendTool().run(name=my_name, message=summary_text)

        print(f"[Digest] Complete. {applied} applied, {skipped} skipped, {len(matches)} total processed.")

    finally:
        db.close()


if __name__ == "__main__":
    run_digest()