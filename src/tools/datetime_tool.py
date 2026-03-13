from datetime import datetime
from src.tools.base import BaseTool

class DateTimeTool(BaseTool):
    name = "get_datetime"
    description = "Get the current date and time"

    def run(self) -> str:
        now = datetime.now()
        return f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}"