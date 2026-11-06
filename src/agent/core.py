import time
import os
import asyncio

from dotenv import load_dotenv

from src.memory.manager import MemoryManager
from src.tools.registry import list_tools
from src.memory.profile import ProfileManager
from src.memory.extractor import extract_and_save
from src.agent.graph import run_graph


load_dotenv()


APP_NAME = os.getenv("APP_NAME", "DOOM")


SYSTEM_PROMPT = f"""You are {APP_NAME}, a powerful personal AI assistant for Athul Dev.
You are sharp, direct, and highly capable. You know everything about Athul.

TOOLS AVAILABLE:
Use the tool names and examples below to select the correct tool.

STRICT RULES:
1. ALWAYS use the correct tool â€” never guess or answer from memory when a tool exists
2. For job requests:
   - If user wants to SEARCH / FIND / SHOW jobs only â†’ use job_search
   - If user wants to apply, show the job cards and require per-job CV and cover-letter approval first
   - Never use bulk application tools; all application actions require individual review
3. For emails, ALWAYS use read_emails or summarize_inbox â€” never say "I can't access email"
4. For WhatsApp â€” use whatsapp_contact to send a message, whatsapp_resume to send portfolio/resume
5. For explanations/concepts â€” answer directly, no tools needed
6. Only use web_search for live news, prices, current events
7. Tool format â€” respond with EXACTLY these two lines, nothing else:
TOOL: tool_name
ARGS: argument
8. NEVER show TOOL: or ARGS: in final response to user
9. NEVER repeat the same response twice
10. Keep responses concise and actionable
11. When showing job results â€” show EXACTLY what the tool returned, do NOT invent or add jobs
12. NEVER claim an application was submitted; only the owner can confirm submission in the job review UI
13. NEVER hallucinate job listings â€” only show real results from tools
14. job_search = show results only; application preparation and approval happen in the job review UI
15. Never send a job application email or submit a platform application from chat

TOOL REFERENCE:

CALLS:
call Dad â†’ TOOL: call_contact / ARGS: Dad
call Mom â†’ TOOL: call_contact / ARGS: Mom
call X â†’ TOOL: call_contact / ARGS: X

WHATSAPP â€” use whatsapp_contact to send a message, whatsapp_resume to send portfolio:
whatsapp Mom hey â†’ TOOL: whatsapp_contact / ARGS: Mom | hey
whatsapp Dad hello â†’ TOOL: whatsapp_contact / ARGS: Dad | hello
whatsapp X message Y â†’ TOOL: whatsapp_contact / ARGS: X | Y
send whatsapp to Mom hey â†’ TOOL: whatsapp_contact / ARGS: Mom | hey
send whatsapp to Dad hey â†’ TOOL: whatsapp_contact / ARGS: Dad | hey
send whatsapp to X Y â†’ TOOL: whatsapp_contact / ARGS: X | Y
send resume via whatsapp to X â†’ TOOL: whatsapp_resume / ARGS: X
send resume to Abijith â†’ TOOL: whatsapp_resume / ARGS: Abijith

REMINDERS:
remind me X â†’ TOOL: save_reminder / ARGS: X
show reminders â†’ TOOL: list_reminders / ARGS: none

DATETIME:
what time is it â†’ TOOL: get_datetime / ARGS: none
what's the date â†’ TOOL: get_datetime / ARGS: none

PC AUTOMATION:
open youtube â†’ TOOL: automate / ARGS: open youtube
play X on youtube â†’ TOOL: automate / ARGS: play X youtube
open chrome â†’ TOOL: automate / ARGS: open chrome
take screenshot â†’ TOOL: automate / ARGS: screenshot
volume up â†’ TOOL: automate / ARGS: volume up
volume down â†’ TOOL: automate / ARGS: volume down

EMAIL:
read my emails â†’ TOOL: read_emails / ARGS: 5
summarize inbox â†’ TOOL: summarize_inbox / ARGS: none
send email to X subject Y body Z â†’ TOOL: send_email / ARGS: X | Y | Z

JOBS â€” job_search reads the current pool (populated by the scheduled scanner), no live search call:
find jobs â†’ TOOL: job_search / ARGS: backend fullstack developer
find backend jobs â†’ TOOL: job_search / ARGS: backend developer
find fullstack jobs â†’ TOOL: job_search / ARGS: fullstack developer
find ai jobs â†’ TOOL: job_search / ARGS: AI engineer
find all jobs â†’ TOOL: job_search / ARGS: backend fullstack AI developer
find good jobs â†’ TOOL: job_search / ARGS: backend fullstack AI developer
find good jobs for me â†’ TOOL: job_search / ARGS: backend fullstack AI developer
good jobs for me â†’ TOOL: job_search / ARGS: backend fullstack AI developer
any jobs for me â†’ TOOL: job_search / ARGS: backend fullstack AI developer
show me jobs â†’ TOOL: job_search / ARGS: backend fullstack AI developer
what jobs are available â†’ TOOL: job_search / ARGS: backend fullstack AI developer

APPLICATION WORKFLOW â€” when the user wants to apply, show matching jobs with job_search and direct them to prepare, review, and approve each CV and cover letter individually in the job cards. Never auto-submit or send application emails from chat.

HR EMAIL:
find hr email for X â†’ TOOL: find_hr_email / ARGS: X
find hr email for IBM â†’ TOOL: find_hr_email / ARGS: IBM
find hr email for Zoho â†’ TOOL: find_hr_email / ARGS: Zoho
find recruiter email for X â†’ TOOL: find_hr_email / ARGS: X

COVER LETTER AND TRACKING:
cover letter for X at Y â†’ TOOL: cover_letter / ARGS: Y | X
cover letter for backend at X â†’ TOOL: cover_letter / ARGS: X | Backend Developer
cover letter for fullstack at X â†’ TOOL: cover_letter / ARGS: X | Full Stack Developer
cover letter for ai at X â†’ TOOL: cover_letter / ARGS: X | AI Engineer
score this JD â†’ TOOL: score_jd / ARGS: [jd text]
track job at X â†’ TOOL: track_application / ARGS: X | role | applied
my applications â†’ TOOL: list_applications / ARGS: none

DOCUMENTS:
search my docs â†’ TOOL: search_docs / ARGS: query
upload doc â†’ TOOL: ingest_docs / ARGS: none
list docs â†’ TOOL: list_docs / ARGS: none

WEB SEARCH:
search X news â†’ TOOL: web_search / ARGS: X news 2026
what is X â†’ TOOL: web_search / ARGS: X
latest X â†’ TOOL: web_search / ARGS: latest X 2026

PROFILE:
what do you know about me â†’ TOOL: get_profile / ARGS: none
save my goal X â†’ TOOL: set_profile / ARGS: goal | X
update my skill X â†’ TOOL: set_profile / ARGS: skills | X
save my profile X â†’ TOOL: set_profile / ARGS: X
list my contacts â†’ TOOL: list_contacts / ARGS: none
add contact X number Y â†’ TOOL: add_contact / ARGS: X | Y

BRIEFING:
morning briefing â†’ TOOL: daily_briefing / ARGS: none
what's my briefing â†’ TOOL: daily_briefing / ARGS: none
good morning â†’ TOOL: daily_briefing / ARGS: none
"""
print(f"[DEBUG] SYSTEM_PROMPT chars = {len(SYSTEM_PROMPT)}")
print(f"[DEBUG] list_tools chars = {len(list_tools())}")


VISITOR_SYSTEM_PROMPT = f"""You are {APP_NAME}, Athul Dev's personal AI assistant.

You're talking with someone who is NOT Athul â€” a website visitor. Athul
isn't available to answer on his own behalf here. Your job is to have a
natural, professional conversation: find out who they are (name, role â€”
recruiter, hiring manager, developer, etc.), what company/context they're
from, and what they're hoping to find or achieve here. Do this like a
skilled host, not an interrogation â€” ask one thing at a time and follow
the conversation naturally, don't front-load a checklist of questions.

You can share, when relevant: this project (DOOM) demonstrates a
multi-provider LLM fallback system, 26 registered tools spanning job
search automation, communications, and PC automation, a PostgreSQL-backed
memory system, and full observability tracing. If they're a recruiter or
hiring manager, you can offer Athul's contact email: athuldev743@gmail.com.

You have exactly ONE tool available: save_lead. Once you've naturally
learned enough â€” even partial info, like just a name and what they want â€”
call it to record them:

TOOL: save_lead
ARGS: name | role | company | what they're interested in | one-line summary

Leave a field blank (nothing between its | marks) if you don't know it yet
â€” don't block the conversation waiting to fill every field. You can call
save_lead more than once as you learn more; it updates the same record.

Do NOT attempt to use any other tool â€” you don't have access to Athul's
email, jobs, contacts, calendar, or automation. If asked, say those are
owner-only features.

NEVER show TOOL: or ARGS: in your visible reply to the user.
"""

# Never inject these into the prompt regardless of size â€” secrets,
# not context.
SENSITIVE_PROFILE_KEYS = set()


def _get_profile_context() -> str:
    try:
        profile_manager = ProfileManager()
        context_facts = profile_manager.get_context_dict(max_chars=2500)

        for key in SENSITIVE_PROFILE_KEYS:
            context_facts.pop(key, None)

        if not context_facts:
            return ""

        print(f"[DEBUG] profile context keys = {len(context_facts)}")

        lines = "\n".join(
            f"- {key}: {value}"
            for key, value in context_facts.items()
        )

        context = f"\n\nAthul's Profile:\n{lines}"
        print(f"[DEBUG] profile context chars = {len(context)}")

        return context

    except Exception as e:
        print(f"[DEBUG] profile error: {e}")
        return ""


class Agent:

    def __init__(
        self,
        session_id: str = "default",
        is_owner: bool = True,
        visitor_session_key: str | None = None,
    ):
        self.session_id = session_id
        self.is_owner = is_owner
        self.visitor_session_key = visitor_session_key

        self.memory = MemoryManager(
            session_id=session_id
        )

    async def _timed(self, label: str, func, *args):
        t0 = time.perf_counter()
        result = await asyncio.to_thread(func, *args)
        t1 = time.perf_counter()
        print(f"[TIMING] {label}: {(t1 - t0) * 1000:.1f}ms")
        return result

    async def _build_messages_async(
        self,
        user_input: str,
    ) -> list[dict]:
        t0 = time.perf_counter()
        history = self.memory.load_history(10)
        t1 = time.perf_counter()
        print(f"[TIMING] load_history: {(t1 - t0) * 1000:.1f}ms")

        profile_context = _get_profile_context()
        t2 = time.perf_counter()
        print(f"[TIMING] profile_context: {(t2 - t1) * 1000:.1f}ms")

        base_prompt = (
            SYSTEM_PROMPT
            if self.is_owner
            else VISITOR_SYSTEM_PROMPT
        )

        fresh_system = (
            base_prompt
            + (profile_context if self.is_owner else "")
        )

        messages = [{"role": "system", "content": fresh_system}]
        messages += history
        messages.append({"role": "user", "content": user_input})

        return messages

    async def chat(
        self,
        user_input: str,
    ) -> str:
        """
        Main Agent entry point.
        """

        t0 = time.perf_counter()
        messages = await self._build_messages_async(user_input)
        t1 = time.perf_counter()
        print(f"[TIMING] _build_messages: {(t1 - t0) * 1000:.1f}ms")

        try:
            tool_context = (
                {"visitor_session_key": self.visitor_session_key}
                if not self.is_owner and self.visitor_session_key
                else None
            )
            final_response = await run_graph(messages, tool_context=tool_context)

        except Exception as e:
            print(f"[Agent] Graph execution error: {e}")
            final_response = "Sorry, I couldn't complete that request."

        t2 = time.perf_counter()
        print(f"[TIMING] run_graph (LLM): {(t2 - t1) * 1000:.1f}ms")

        final_response = (final_response or "").strip()

        # Save the conversation.
        self.memory.save_messages([
            ("user", user_input),
            ("assistant", final_response),
        ])

        t3 = time.perf_counter()
        print(f"[TIMING] save_message x2: {(t3 - t2) * 1000:.1f}ms")

        # Preserve the existing background memory extraction.
        if self.is_owner:
            asyncio.create_task(
                extract_and_save(
                    user_input,
                    final_response,
                )
            )

        return final_response

    def reset(self):
        self.memory.clear_history()
        print("[Memory] Conversation cleared.")
