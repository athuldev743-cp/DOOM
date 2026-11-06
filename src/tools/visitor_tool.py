from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from src.tools.base import BaseTool
from src.tools.schemas import SaveLeadArgs, ToolResult
from src.memory.database import SessionLocal, Visitor


_visitor_session_key: ContextVar[str | None] = ContextVar(
    "visitor_session_key",
    default=None,
)


@contextmanager
def visitor_lead_context(session_key: str):
    """Bind a request-derived visitor identity for one lead-tool execution."""
    token = _visitor_session_key.set(session_key)
    try:
        yield
    finally:
        _visitor_session_key.reset(token)


class SaveLeadTool(BaseTool):
    name = "save_lead"
    description = (
        "Save what you've learned about a non-owner visitor (name, role, "
        "company, what they want) into the leads pool. Call this as soon "
        "as you have anything useful — partial info is fine, you can call "
        "it again later in the same conversation to fill in more."
    )
    args_schema = SaveLeadArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        parts = raw.split("|")
        fields = ("name", "role", "company", "interest", "summary")
        return {
            field: parts[index].strip() if index < len(parts) else ""
            for index, field in enumerate(fields)
        }

    def run(
        self,
        name: str = "",
        role: str = "",
        company: str = "",
        interest: str = "",
        summary: str = "",
    ) -> ToolResult:
        session_key = _visitor_session_key.get()
        if not session_key:
            return ToolResult(
                success=False,
                message="Lead capture is only available in a visitor conversation.",
            )
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
            return ToolResult(success=True, message="Lead saved.")
        except Exception as e:
            db.rollback()
            return ToolResult(success=False, message=f"Could not save lead: {e}")
        finally:
            db.close()
