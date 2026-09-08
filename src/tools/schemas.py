from typing import Any, Optional
from pydantic import BaseModel
import json


class ToolResult(BaseModel):
    """Every tool now returns this instead of a raw string."""
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    prefix: Optional[str] = None  # e.g. "JOBS_DATA" — JSON-payload style prefix
    raw: Optional[str] = None     # exact wire string for colon-delimited legacy
                                   # formats (e.g. "CALL:919999999999:John") that
                                   # aren't JSON — takes priority over prefix/data

    def to_wire(self) -> str:
        """Serializes back to the legacy string format the frontend already
        parses, so index.html doesn't need to change yet."""
        if self.raw is not None:
            return self.raw
        if self.prefix:
            return f"{self.prefix}:" + json.dumps(self.data or {})
        return self.message


# ---- Job tools args schemas ----

class JobSearchArgs(BaseModel):
    query: str = ""
    limit: int = 50

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


# ---- Contacts / profile tools args schemas ----

class CallContactArgs(BaseModel):
    name: str


class AddContactArgs(BaseModel):
    name: str
    phone: str = ""
    relationship: str = ""
    notes: str = ""


class ListContactsArgs(BaseModel):
    pass


class SetProfileArgs(BaseModel):
    key: str
    value: str
    category: str = "general"


class GetProfileArgs(BaseModel):
    key: str = ""


# ---- Automation tool args schema ----

class AutomationArgs(BaseModel):
    command: str
    args: str = ""


# ---- HR email / apply tools args schemas ----

class FindHREmailArgs(BaseModel):
    company: str = ""


class AutoApplyArgs(BaseModel):
    company: str = ""
    role: str = "Developer"
    job_index: Optional[int] = None
    track: bool = True
    jd: str = ""


class BulkApplyArgs(BaseModel):
    query: str = ""


# ---- Email tools args schemas ----

class ReadEmailsArgs(BaseModel):
    count: int = 5


class SendEmailArgs(BaseModel):
    to: str = ""
    subject: str = ""
    body: str = ""


class SendEmailWithResumeArgs(BaseModel):
    to: str = ""
    subject: str = ""
    body: str = ""
    role: str = ""


class SendResumeEmailArgs(BaseModel):
    to: str = ""
    role: str = "AI Engineer"
    name: str = "Hiring Manager"


class SummarizeInboxArgs(BaseModel):
    count: int = 10


# ---- Reminder / datetime / search tools args schemas ----

class SaveReminderArgs(BaseModel):
    title: str
    note: str = ""


class ListRemindersArgs(BaseModel):
    pass


class GetDateTimeArgs(BaseModel):
    pass


class WebSearchArgs(BaseModel):
    query: str = ""


# ---- RAG / briefing / naukri / linkedin tools args schemas ----

class RAGSearchArgs(BaseModel):
    query: str = ""


class IngestDocsArgs(BaseModel):
    pass


class ListDocsArgs(BaseModel):
    pass


class DailyBriefingArgs(BaseModel):
    pass


class NaukriSearchArgs(BaseModel):
    query: str = ""
    location: str = ""


class LinkedInProfileArgs(BaseModel):
    pass


class LinkedInJobSearchArgs(BaseModel):
    query: str = ""