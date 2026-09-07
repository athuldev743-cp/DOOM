from datetime import datetime
from src.tools.base import BaseTool
from src.tools.schemas import ToolResult, SaveReminderArgs, ListRemindersArgs
from src.memory.database import SessionLocal
from sqlalchemy import Column, Integer, String, Text, DateTime
from src.memory.database import Base

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class ReminderTool(BaseTool):
    name = "save_reminder"
    description = "Save a reminder or note for the user"
    args_schema = SaveReminderArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"title": raw.strip()}

    def run(self, title: str, note: str = "") -> ToolResult:
        try:
            db = SessionLocal()
            reminder = Reminder(title=title, note=note)
            db.add(reminder)
            db.commit()
            db.close()
            return ToolResult(success=True, message=f"Reminder saved: '{title}'")
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to save reminder: {str(e)}")

class ListRemindersTool(BaseTool):
    name = "list_reminders"
    description = "List all saved reminders"
    args_schema = ListRemindersArgs

    def run(self) -> ToolResult:
        try:
            db = SessionLocal()
            reminders = db.query(Reminder).order_by(Reminder.created_at.desc()).limit(10).all()
            db.close()
            if not reminders:
                return ToolResult(success=True, message="No reminders found.")
            output = "Your reminders:\n"
            for r in reminders:
                output += f"- {r.title}"
                if r.note:
                    output += f": {r.note}"
                output += "\n"
            return ToolResult(success=True, message=output)
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to load reminders: {str(e)}")