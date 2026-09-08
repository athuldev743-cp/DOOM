import os
import re
import asyncio
from dotenv import load_dotenv

from src.agent.llm import chat
from src.memory.manager import MemoryManager
from src.tools.registry import get_tool, list_tools
from src.tools.schemas import ToolResult
from src.memory.profile import ProfileManager
from src.memory.extractor import extract_and_save

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "DOOM")

SYSTEM_PROMPT = f"""You are {APP_NAME}, a powerful personal AI assistant for Athul Dev.
You are sharp, direct, and highly capable. You know everything about Athul.

TOOLS AVAILABLE:
{list_tools()}

STRICT RULES:
1. ALWAYS use the correct tool — never guess or answer from memory when a tool exists
2. For job requests:
   - If user wants to SEARCH / FIND / SHOW jobs only → use job_search
   - If user explicitly says APPLY → use auto_apply or bulk_apply
   - NEVER use bulk_apply unless user clearly wants applications sent
3. For emails, ALWAYS use read_emails or summarize_inbox — never say "I can't access email"
4. For WhatsApp — use whatsapp_contact to send a message, whatsapp_resume to send portfolio/resume
5. For explanations/concepts — answer directly, no tools needed
6. Only use web_search for live news, prices, current events
7. Tool format — respond with EXACTLY these two lines, nothing else:
TOOL: tool_name
ARGS: argument
8. NEVER show TOOL: or ARGS: in final response to user
9. NEVER repeat the same response twice
10. Keep responses concise and actionable
11. When showing job results — show EXACTLY what the tool returned, do NOT invent or add jobs
12. NEVER say "I applied" unless bulk_apply or auto_apply tool was actually used
13. NEVER hallucinate job listings — only show real results from tools
14. job_search = show results only, NEVER apply
15. bulk_apply = search AND apply, ONLY when user says apply

TOOL REFERENCE:

CALLS:
call Dad → TOOL: call_contact / ARGS: Dad
call Mom → TOOL: call_contact / ARGS: Mom
call X → TOOL: call_contact / ARGS: X

WHATSAPP — use whatsapp_contact to send a message, whatsapp_resume to send portfolio:
whatsapp Mom hey → TOOL: whatsapp_contact / ARGS: Mom | hey
whatsapp Dad hello → TOOL: whatsapp_contact / ARGS: Dad | hello
whatsapp X message Y → TOOL: whatsapp_contact / ARGS: X | Y
send whatsapp to Mom hey → TOOL: whatsapp_contact / ARGS: Mom | hey
send whatsapp to Dad hey → TOOL: whatsapp_contact / ARGS: Dad | hey
send whatsapp to X Y → TOOL: whatsapp_contact / ARGS: X | Y
send resume via whatsapp to X → TOOL: whatsapp_resume / ARGS: X
send resume to Abijith → TOOL: whatsapp_resume / ARGS: Abijith

REMINDERS:
remind me X → TOOL: save_reminder / ARGS: X
show reminders → TOOL: list_reminders / ARGS: none

DATETIME:
what time is it → TOOL: get_datetime / ARGS: none
what's the date → TOOL: get_datetime / ARGS: none

PC AUTOMATION:
open youtube → TOOL: automate / ARGS: open youtube
play X on youtube → TOOL: automate / ARGS: play X youtube
open chrome → TOOL: automate / ARGS: open chrome
take screenshot → TOOL: automate / ARGS: screenshot
volume up → TOOL: automate / ARGS: volume up
volume down → TOOL: automate / ARGS: volume down

EMAIL:
read my emails → TOOL: read_emails / ARGS: 5
summarize inbox → TOOL: summarize_inbox / ARGS: none
send email to X subject Y body Z → TOOL: send_email / ARGS: X | Y | Z
send resume email to X → TOOL: send_resume_email / ARGS: X

JOBS — job_search reads the current pool (populated by the scheduled scanner), no live search call:
find jobs → TOOL: job_search / ARGS: backend fullstack developer
find backend jobs → TOOL: job_search / ARGS: backend developer
find fullstack jobs → TOOL: job_search / ARGS: fullstack developer
find ai jobs → TOOL: job_search / ARGS: AI engineer
find all jobs → TOOL: job_search / ARGS: backend fullstack AI developer
find good jobs → TOOL: job_search / ARGS: backend fullstack AI developer
find good jobs for me → TOOL: job_search / ARGS: backend fullstack AI developer
good jobs for me → TOOL: job_search / ARGS: backend fullstack AI developer
any jobs for me → TOOL: job_search / ARGS: backend fullstack AI developer
show me jobs → TOOL: job_search / ARGS: backend fullstack AI developer
what jobs are available → TOOL: job_search / ARGS: backend fullstack AI developer

APPLY — only when user explicitly says apply:
apply for backend at X → TOOL: auto_apply / ARGS: X | Backend Developer
apply for fullstack at X → TOOL: auto_apply / ARGS: X | Full Stack Developer
apply for ai engineer at X → TOOL: auto_apply / ARGS: X | AI Engineer
apply for backend at IBM → TOOL: auto_apply / ARGS: IBM | Backend Developer
apply for ai engineer at Zoho → TOOL: auto_apply / ARGS: Zoho | AI Engineer
apply for fullstack at Razorpay → TOOL: auto_apply / ARGS: Razorpay | Full Stack Developer
apply to 3 jobs today → TOOL: bulk_apply / ARGS: backend fullstack AI developer
apply to backend jobs → TOOL: bulk_apply / ARGS: backend developer
apply to fullstack jobs → TOOL: bulk_apply / ARGS: fullstack developer
apply to ai jobs → TOOL: bulk_apply / ARGS: AI engineer
apply to all jobs → TOOL: bulk_apply / ARGS: backend fullstack AI developer
apply to backend jobs today → TOOL: bulk_apply / ARGS: backend developer
apply to fullstack jobs today → TOOL: bulk_apply / ARGS: fullstack developer
apply to ai jobs today → TOOL: bulk_apply / ARGS: AI engineer
find and apply best backend jobs → TOOL: bulk_apply / ARGS: backend developer
find and apply best fullstack jobs → TOOL: bulk_apply / ARGS: fullstack developer
find and apply best ai jobs → TOOL: bulk_apply / ARGS: AI engineer
find and apply all jobs → TOOL: bulk_apply / ARGS: backend fullstack AI developer

HR EMAIL:
find hr email for X → TOOL: find_hr_email / ARGS: X
find hr email for IBM → TOOL: find_hr_email / ARGS: IBM
find hr email for Zoho → TOOL: find_hr_email / ARGS: Zoho
find recruiter email for X → TOOL: find_hr_email / ARGS: X

COVER LETTER AND TRACKING:
cover letter for X at Y → TOOL: cover_letter / ARGS: Y | X
cover letter for backend at X → TOOL: cover_letter / ARGS: X | Backend Developer
cover letter for fullstack at X → TOOL: cover_letter / ARGS: X | Full Stack Developer
cover letter for ai at X → TOOL: cover_letter / ARGS: X | AI Engineer
score this JD → TOOL: score_jd / ARGS: [jd text]
track job at X → TOOL: track_application / ARGS: X | role | applied
my applications → TOOL: list_applications / ARGS: none

DOCUMENTS:
search my docs → TOOL: search_docs / ARGS: query
upload doc → TOOL: ingest_docs / ARGS: none
list docs → TOOL: list_docs / ARGS: none

WEB SEARCH:
search X news → TOOL: web_search / ARGS: X news 2026
what is X → TOOL: web_search / ARGS: X
latest X → TOOL: web_search / ARGS: latest X 2026

PROFILE:
what do you know about me → TOOL: get_profile / ARGS: none
save my goal X → TOOL: set_profile / ARGS: goal | X
update my skill X → TOOL: set_profile / ARGS: skills | X
save my profile X → TOOL: set_profile / ARGS: X
list my contacts → TOOL: list_contacts / ARGS: none
add contact X number Y → TOOL: add_contact / ARGS: X | Y

BRIEFING:
morning briefing → TOOL: daily_briefing / ARGS: none
what's my briefing → TOOL: daily_briefing / ARGS: none
good morning → TOOL: daily_briefing / ARGS: none"""

VISITOR_SYSTEM_PROMPT = f"""You are {APP_NAME}, Athul Dev's personal AI assistant.

You're talking with someone who is NOT Athul — a website visitor. Athul
isn't available to answer on his own behalf here. Your job is to have a
natural, professional conversation: find out who they are (name, role —
recruiter, hiring manager, developer, etc.), what company/context they're
from, and what they're hoping to find or achieve here. Do this like a
skilled host, not an interrogation — ask one thing at a time and follow
the conversation naturally, don't front-load a checklist of questions.

You can share, when relevant: this project (DOOM) demonstrates a
multi-provider LLM fallback system, 25+ integrated tools spanning job
search automation, communications, and PC automation, a PostgreSQL-backed
memory system, and full observability tracing. If they're a recruiter or
hiring manager, you can offer Athul's contact email: athuldev743@gmail.com.

You have exactly ONE tool available: save_lead. Once you've naturally
learned enough — even partial info, like just a name and what they want —
call it to record them:
TOOL: save_lead
ARGS: name | role | company | what they're interested in | one-line summary

Leave a field blank (nothing between its | marks) if you don't know it yet
— don't block the conversation waiting to fill every field. You can call
save_lead more than once as you learn more; it updates the same record.

Do NOT attempt to use any other tool — you don't have access to Athul's
email, jobs, contacts, calendar, or automation. If asked, say those are
owner-only features.

NEVER show TOOL: or ARGS: in your visible reply to the user."""



def _get_profile_context() -> str:
    try:
        p = ProfileManager()
        profile = p.get_all()
        if not profile:
            return ""
        lines = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        return f"\n\nAthul's Profile:\n{lines}"
    except Exception:
        return ""


class Agent:
    def __init__(self, session_id: str = "default", is_owner: bool = True):
        self.session_id = session_id
        self.is_owner = is_owner
        self.memory = MemoryManager(session_id=session_id)
        base_prompt = SYSTEM_PROMPT if is_owner else VISITOR_SYSTEM_PROMPT
        self.system = base_prompt + (_get_profile_context() if is_owner else "")

    def _build_messages(self, user_input: str) -> list:
        history = self.memory.load_history(limit=10)
        base_prompt = SYSTEM_PROMPT if self.is_owner else VISITOR_SYSTEM_PROMPT
        fresh_system = base_prompt + (_get_profile_context() if self.is_owner else "")
        messages = [{"role": "system", "content": fresh_system}]
        messages += history
        messages.append({"role": "user", "content": user_input})
        return messages

    def _parse_tool_call(self, response: str):
        response = response.strip()
        if "TOOL:" in response:
            try:
                tool_match = re.search(r"TOOL:\s*(\S+)", response)
                args_match = re.search(r"ARGS:\s*(.+?)(?:\n|$)", response, re.DOTALL)
                if tool_match:
                    tool_name = tool_match.group(1).strip()
                    args = args_match.group(1).strip() if args_match else ""
                    return tool_name, args
            except Exception:
                pass
        return None, None

    def _clean_response(self, response: str) -> str:
        lines = response.split("\n")
        clean = [
            l for l in lines
            if not l.strip().startswith("TOOL:")
            and not l.strip().startswith("ARGS:")
        ]
        return "\n".join(clean).strip()

    def _unwrap(self, result):
        """Bridge for the Pydantic tool migration: every tool now returns
        ToolResult except the two WhatsApp tools (intentionally left as
        plain strings, WhatsApp out of scope). This makes both work through
        the same dispatch unchanged."""
        if isinstance(result, ToolResult):
            return result.to_wire()
        return result

    async def _run_tool(self, tool_name: str, args: str) -> str:
     tool = get_tool(tool_name)

     if not tool:
        return f"Unknown tool: {tool_name}"

     try:
        if tool_name == "save_reminder":
            return self._unwrap(tool.run(title=args))

        elif tool_name == "web_search":
            return self._unwrap(tool.run(query=args))

        elif tool_name == "automate":
            return self._unwrap(tool.run(command=args))

        elif tool_name == "search_docs":
            return self._unwrap(tool.run(query=args))

        elif tool_name == "call_contact":
            return self._unwrap(tool.run(name=args))

        elif tool_name == "whatsapp_contact":
            parts = args.split("|")
            name = parts[0].strip()
            message = parts[1].strip() if len(parts) > 1 else ""
            return self._unwrap(tool.run(name=name, message=message))

        elif tool_name == "whatsapp_resume":
            return self._unwrap(tool.run(name=args.strip()))

        elif tool_name == "add_contact":
            parts = args.split("|")
            name = parts[0].strip()
            phone = parts[1].strip() if len(parts) > 1 else ""
            relationship = parts[2].strip() if len(parts) > 2 else ""
            notes = parts[3].strip() if len(parts) > 3 else ""

            return self._unwrap(tool.run(
                name=name,
                phone=phone,
                relationship=relationship,
                notes=notes
            ))

        elif tool_name == "set_profile":
            parts = args.split("|")
            key = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ""
            return self._unwrap(tool.run(key=key, value=value))

        elif tool_name == "get_profile":
            return self._unwrap(tool.run(key=args if args != "none" else ""))

        elif tool_name == "read_emails":
            count = int(args) if args and args.isdigit() else 5
            return self._unwrap(tool.run(count=count))

        elif tool_name == "send_email":
            parts = args.split("|")
            to = parts[0].strip()
            subject = parts[1].strip() if len(parts) > 1 else "Hello"
            body = parts[2].strip() if len(parts) > 2 else ""
            return self._unwrap(tool.run(to=to, subject=subject, body=body))

        elif tool_name == "send_resume_email":
            return self._unwrap(tool.run(to=args.strip()))

        elif tool_name == "summarize_inbox":
            return self._unwrap(tool.run())

        elif tool_name == "job_search":
            return self._unwrap(tool.run(query=args))

        elif tool_name == "score_jd":
            return self._unwrap(tool.run(jd=args))

        elif tool_name == "cover_letter":
            parts = args.split("|")
            company = parts[0].strip() if parts else ""
            role = parts[1].strip() if len(parts) > 1 else ""
            return self._unwrap(tool.run(company=company, role=role))

        elif tool_name == "track_application":
            parts = args.split("|")
            company = parts[0].strip() if parts else ""
            role = parts[1].strip() if len(parts) > 1 else ""
            status = parts[2].strip() if len(parts) > 2 else "applied"
            return self._unwrap(tool.run(company=company, role=role, status=status))

        elif tool_name == "find_hr_email":
            return self._unwrap(tool.run(company=args))

        elif tool_name == "auto_apply":
            parts = args.split("|")
            company = parts[0].strip()
            role = parts[1].strip() if len(parts) > 1 else "Developer"
            return self._unwrap(tool.run(company=company, role=role))

        elif tool_name == "bulk_apply":
            return self._unwrap(tool.run(query=args))

        elif tool_name == "list_applications":
            return self._unwrap(tool.run())

        elif tool_name == "save_lead":
                    parts = args.split("|")
                    name = parts[0].strip() if len(parts) > 0 else ""
                    role = parts[1].strip() if len(parts) > 1 else ""
                    company = parts[2].strip() if len(parts) > 2 else ""
                    interest = parts[3].strip() if len(parts) > 3 else ""
                    summary = parts[4].strip() if len(parts) > 4 else ""
                    return self._unwrap(tool.run(
                        session_key=self.session_id, name=name, role=role,
                        company=company, interest=interest, summary=summary,
                    ))

        elif tool_name == "daily_briefing":
            return self._unwrap(tool.run())

        

        elif tool_name in [
            "list_contacts",
            "list_reminders",
            "list_docs",
            "ingest_docs",
            "get_datetime",
        ]:
            return self._unwrap(tool.run())

        else:
            return self._unwrap(tool.run())

     except Exception as e:
        return f"Tool error: {str(e)}"

    async def chat(self, user_input: str) -> str:
        messages = self._build_messages(user_input)
        response = await chat(messages)
        print(f"[Agent] Raw LLM response: {response!r}") 

        tool_name, args = self._parse_tool_call(response)

        if tool_name:
            tool = get_tool(tool_name)
            if tool:
                print(f"[TOOL] {tool_name} | {args}")
                tool_result = await self._run_tool(tool_name, args)

                if (
    tool_result.startswith("CALL:")
    or tool_result.startswith("WHATSAPP:")
    or tool_result.startswith("YOUTUBE:")
    or tool_result.startswith("APP:")
    or tool_result.startswith("JOBS_DATA:")
    or tool_result.startswith("APPLY_REPORT:")
    or "NOT_FOUND" in tool_result
):
                    self.memory.save_message("user", user_input)
                    self.memory.save_message("assistant", tool_result)
                    return tool_result

                messages.append({"role": "assistant", "content": response})
                messages.append({
    "role": "user",
    "content": (
        f"Tool result: {tool_result}\n\n"
        "STRICT INSTRUCTIONS:\n"
        "1. Present ONLY the information from the tool result above\n"
        "2. Do NOT add, invent, or hallucinate any jobs, companies, or details\n"
        "3. Do NOT say 'I applied' unless the tool result contains '✅ Applied'\n"
        "4. List jobs cleanly — just number, title, company if visible, and link\n"
        "5. End with: 'To apply to any of these: say apply for [role] at [company]'\n"
        "6. Never show TOOL: or ARGS: in response\n"
        "7. Keep response concise and factual — no extra commentary"
    ),
})

                final_response = await chat(messages)
                final_response = self._clean_response(final_response)
                self.memory.save_message("user", user_input)
                self.memory.save_message("assistant", final_response)
                asyncio.create_task(extract_and_save(user_input, final_response))
                return final_response

            else:
                clean = self._clean_response(response)
                self.memory.save_message("user", user_input)
                self.memory.save_message("assistant", clean)
                return clean

        clean = self._clean_response(response)
        self.memory.save_message("user", user_input)
        self.memory.save_message("assistant", clean)
        asyncio.create_task(extract_and_save(user_input, clean))
        return clean

    def reset(self):
        self.memory.clear_history()
        print("[Memory] Conversation cleared.")