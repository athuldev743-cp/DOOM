from typing import Any, Optional
from pydantic import BaseModel
import json


class ToolResult(BaseModel):
    """Every tool now returns this instead of a raw string."""
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    prefix: Optional[str] = None  # e.g. "JOBS_DATA" — preserves the frontend's existing contract

    def to_wire(self) -> str:
        """Serializes back to the legacy prefixed-string format the frontend
        already parses, so index.html doesn't need to change yet."""
        if self.prefix:
            return f"{self.prefix}:" + json.dumps(self.data or {})
        return self.message


# ---- Job tools args schemas ----

class JobSearchArgs(BaseModel):
    query: str = ""
    limit: int = 20


class CoverLetterArgs(BaseModel):
    company: str = ""
    role: str = ""
    jd: str = ""


class ScoreJDArgs(BaseModel):
    jd: str = ""


class TrackApplicationArgs(BaseModel):
    company: str = ""
    role: str = ""
    status: str = "applied"


class ListApplicationsArgs(BaseModel):
    pass