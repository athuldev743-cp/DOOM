from datetime import datetime
from src.tools.base import BaseTool
from src.tools.schemas import ToolResult, GetDateTimeArgs

class DateTimeTool(BaseTool):
    name = "get_datetime"
    description = "Get the current date and time"
    args_schema = GetDateTimeArgs

    def run(self) -> ToolResult:
        now = datetime.now()
        return ToolResult(
            success=True,
            message=f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}",
        )