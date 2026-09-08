from src.tools.search import WebSearchTool
from src.tools.datetime_tool import DateTimeTool
from src.tools.reminder import ReminderTool, ListRemindersTool
from src.tools.automation import AutomationTool
from src.tools.rag_tool import RAGSearchTool, IngestDocsTool, ListDocsTool
from src.tools.briefing_tool import DailyBriefingTool
from src.tools.auto_apply_tool import FindHREmailTool, AutoApplyTool, BulkApplyTool
from src.tools.visitor_tool import SaveLeadTool

from src.tools.contacts_tool import (
    CallContactTool, WhatsAppContactTool, WhatsAppResumeTool,
    AddContactTool, ListContactsTool,
    SetProfileTool, GetProfileTool
)

from src.tools.email_tool import (
    ReadEmailsTool, SendEmailTool,
    SendResumeEmailTool, SummarizeInboxTool,
    SendEmailWithResumeTool
)

from src.tools.jobs_tool import (
    JobSearchTool, ScoreJDTool, CoverLetterTool,
    TrackApplicationTool, ListApplicationsTool,
)


TOOLS = {
    "web_search": WebSearchTool(),
    "get_datetime": DateTimeTool(),
    "save_reminder": ReminderTool(),
    "list_reminders": ListRemindersTool(),
    "automate": AutomationTool(),
    "search_docs": RAGSearchTool(),
    "ingest_docs": IngestDocsTool(),
    "list_docs": ListDocsTool(),
    "call_contact": CallContactTool(),
    "whatsapp_contact": WhatsAppContactTool(),
    "add_contact": AddContactTool(),
    "list_contacts": ListContactsTool(),
    "set_profile": SetProfileTool(),
    "get_profile": GetProfileTool(),
    "whatsapp_resume": WhatsAppResumeTool(),
    "read_emails": ReadEmailsTool(),
    "send_email": SendEmailTool(),
    "send_resume_email": SendResumeEmailTool(),
    "summarize_inbox": SummarizeInboxTool(),
    "job_search": JobSearchTool(),
    "score_jd": ScoreJDTool(),
    "cover_letter": CoverLetterTool(),
    "track_application": TrackApplicationTool(),
    "list_applications": ListApplicationsTool(),
    "daily_briefing": DailyBriefingTool(),
    "find_hr_email": FindHREmailTool(),
    "auto_apply": AutoApplyTool(),
    "bulk_apply": BulkApplyTool(),
    "send_email_resume": SendEmailWithResumeTool(),
     "save_lead": SaveLeadTool(),
   
    
}


def get_tool(name: str):
    return TOOLS.get(name)


def list_tools() -> str:
    return "\n".join([f"- {name}: {tool.description}" for name, tool in TOOLS.items()])