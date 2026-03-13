from datetime import datetime
from src.tools.base import BaseTool
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

    def run(self, title: str, note: str = "") -> str:
        try:
            db = SessionLocal()
            reminder = Reminder(title=title, note=note)
            db.add(reminder)
            db.commit()
            db.close()
            return f"Reminder saved: '{title}'"
        except Exception as e:
            return f"Failed to save reminder: {str(e)}"

class ListRemindersTool(BaseTool):
    name = "list_reminders"
    description = "List all saved reminders"

    def run(self) -> str:
        try:
            db = SessionLocal()
            reminders = db.query(Reminder).order_by(Reminder.created_at.desc()).limit(10).all()
            db.close()
            if not reminders:
                return "No reminders found."
            output = "Your reminders:\n"
            for r in reminders:
                output += f"- {r.title}"
                if r.note:
                    output += f": {r.note}"
                output += "\n"
            return output
        except Exception as e:
            return f"Failed to load reminders: {str(e)}"