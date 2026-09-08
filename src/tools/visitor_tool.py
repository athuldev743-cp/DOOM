from datetime import datetime
from src.memory.database import SessionLocal, Visitor


class SaveLeadTool:
    description = (
        "Save what you've learned about a non-owner visitor (name, role, "
        "company, what they want) into the leads pool. Call this as soon "
        "as you have anything useful — partial info is fine, you can call "
        "it again later in the same conversation to fill in more."
    )

    def run(self, session_key: str, name: str = "", role: str = "",
            company: str = "", interest: str = "", summary: str = "") -> str:
        db = SessionLocal()
        try:
            visitor = db.query(Visitor).filter_by(session_key=session_key).first()
            if visitor:
                visitor.name = name or visitor.name
                visitor.role = role or visitor.role
                visitor.company = company or visitor.company
                visitor.interest = interest or visitor.interest
                visitor.summary = summary or visitor.summary
                visitor.last_seen = datetime.utcnow()
            else:
                visitor = Visitor(
                    session_key=session_key, name=name, role=role,
                    company=company, interest=interest, summary=summary,
                )
                db.add(visitor)
            db.commit()
            return "Lead saved."
        except Exception as e:
            db.rollback()
            return f"Could not save lead: {e}"
        finally:
            db.close()