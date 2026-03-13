from src.tools.search import WebSearchTool
from src.tools.datetime_tool import DateTimeTool
from src.tools.reminder import ReminderTool, ListRemindersTool
from src.tools.automation import AutomationTool
from src.tools.rag_tool import RAGSearchTool, IngestDocsTool, ListDocsTool
from src.tools.briefing_tool import DailyBriefingTool
from src.tools.linkedin_tool import LinkedInProfileTool, LinkedInJobSearchTool
from src.tools.naukri_tool import NaukriSearchTool, NaukriScrapeTool
from src.tools.auto_apply_tool import FindHREmailTool, AutoApplyTool, BulkApplyTool
from src.tools.whatsapp_api_tool import WhatsAppSendTool, WhatsAppBroadcastTool, WhatsAppResumeTool

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
    TrackApplicationTool, ListApplicationsTool
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
    "linkedin_profile": LinkedInProfileTool(),
    "linkedin_jobs": LinkedInJobSearchTool(),
    "naukri_search": NaukriSearchTool(),
    "naukri_scrape": NaukriScrapeTool(),
    "find_hr_email": FindHREmailTool(),
    "auto_apply": AutoApplyTool(),
    "bulk_apply": BulkApplyTool(),
    "send_email_resume": SendEmailWithResumeTool(),
    "whatsapp_api_send": WhatsAppSendTool(),
    "whatsapp_broadcast": WhatsAppBroadcastTool(),
    "whatsapp_api_resume": WhatsAppResumeTool(),

}





def get_tool(name: str):
    return TOOLS.get(name)

def list_tools() -> str:
    return "\n".join([f"- {name}: {tool.description}" for name, tool in TOOLS.items()])