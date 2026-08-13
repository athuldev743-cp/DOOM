import os
import json
import base64
import re
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.tools.base import BaseTool

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


EMAIL_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f4f7; margin: 0; padding: 0; }
  .container { max-width: 600px; margin: 24px auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .header { background: #0f172a; padding: 24px 32px; }
  .header h1 { color: #ffffff; font-size: 18px; margin: 0; letter-spacing: 0.02em; }
  .header p { color: #94a3b8; font-size: 12px; margin: 4px 0 0; font-family: monospace; }
  .body { padding: 28px 32px; color: #1e293b; font-size: 14px; line-height: 1.7; }
  .footer { padding: 20px 32px; background: #f8fafc; border-top: 1px solid #e2e8f0; }
  .footer-links { font-size: 12px; color: #64748b; }
  .footer-links a { color: #2563eb; text-decoration: none; margin-right: 12px; }
  .badge { display: inline-block; background: #eff6ff; color: #2563eb; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 12px; font-family: monospace; margin-top: 6px; }
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{{name}}</h1>
      <p>Backend & AI Systems Engineer</p>
      <span class="badge">APPLICATION &mdash; {{role}}</span>
    </div>
    <div class="body">{{cover_letter_body}}</div>
    <div class="footer">
      <div class="footer-links">
        &#128231; {{email}} &nbsp;|&nbsp; &#128241; {{phone}} &nbsp;|&nbsp;
        <a href="{{portfolio}}">Portfolio</a>
        <a href="{{github}}">GitHub</a>
      </div>
    </div>
  </div>
</body>
</html>"""


def build_html_email(name: str, role: str, email: str, phone: str,
                      portfolio: str, github: str, cover_letter_body: str) -> str:
    html_body = cover_letter_body.replace("\n", "<br>")
    html = EMAIL_TEMPLATE
    for key, val in {
        "name": name, "role": role, "email": email, "phone": phone,
        "portfolio": portfolio, "github": github, "cover_letter_body": html_body,
    }.items():
        html = html.replace("{{" + key + "}}", val or "")
    return html


def sanitize_email(email_str: str) -> str:
    """Sanitize email string to remove quotes, extra arguments, and whitespace."""
    if not email_str:
        return ""
    cleaned = str(email_str).strip()
    
    # Handle pipe-separated parameters if LLM passes "email | role"
    if "|" in cleaned:
        cleaned = cleaned.split("|")[0].strip()
        
    cleaned = cleaned.strip("'\"`<>")
    if "<" in cleaned and ">" in cleaned:
        cleaned = cleaned.split("<")[1].split(">")[0].strip()
        
    # Extract only the valid email token if extra words remain
    tokens = cleaned.split()
    for token in tokens:
        if "@" in token:
            return token.strip("'\"`<>,;")
            
    return cleaned


def get_gmail_service():
    creds = None
    token_json_str = (
        os.getenv("GMAIL_TOKEN_JSON")
        or os.getenv("GMAIL_CREDENTIALS_JSON")
    )

    if token_json_str:
        try:
            cleaned_token_str = token_json_str.strip()
            if cleaned_token_str.startswith("'") and cleaned_token_str.endswith("'"):
                cleaned_token_str = cleaned_token_str[1:-1]
            if cleaned_token_str.startswith('"') and cleaned_token_str.endswith('"'):
                cleaned_token_str = cleaned_token_str[1:-1]

            token_info = json.loads(cleaned_token_str)
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            print("[Gmail] Successfully loaded token from Environment Variable")
        except Exception as e:
            print(f"[Gmail] Token parsing error from ENV: {e}")

    if not creds and os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            print("[Gmail] Loaded token from local token.json")
        except Exception as e:
            print(f"[Gmail] Error reading local token.json: {e}")

    if not creds:
        raise Exception("Gmail credentials not found. Set GMAIL_TOKEN_JSON environment variable.")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[Gmail] Token refreshed successfully")
            except Exception as refresh_err:
                raise Exception(f"Failed to refresh Gmail token: {refresh_err}")
        else:
            raise Exception("Gmail token is invalid or expired without a valid refresh_token.")

    return build('gmail', 'v1', credentials=creds)


class ReadEmailsTool(BaseTool):
    name = "read_emails"
    description = "Read latest unread emails from Gmail"

    def run(self, count: int = 5) -> str:
        try:
            service = get_gmail_service()
            results = service.users().messages().list(
                userId='me', labelIds=['UNREAD'], maxResults=count
            ).execute()
            messages = results.get('messages', [])
            if not messages:
                return "No unread emails."
            emails = []
            for msg in messages[:count]:
                m = service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()
                headers = {h['name']: h['value'] for h in m['payload']['headers']}
                snippet = m.get('snippet', '')[:150]
                emails.append(
                    f"From: {headers.get('From', 'Unknown')}\n"
                    f"Subject: {headers.get('Subject', 'No subject')}\n"
                    f"Preview: {snippet}"
                )
            return f"You have {len(messages)} unread emails:\n\n" + "\n\n---\n\n".join(emails)
        except Exception as e:
            return f"Email error: {str(e)}"


class SendEmailTool(BaseTool):
    name = "send_email"
    description = "Send an email via Gmail"

    def run(self, to: str = "", subject: str = "", body: str = "") -> str:
        clean_to = sanitize_email(to)
        try:
            service = get_gmail_service()
            if '@' not in clean_to:
                from src.memory.profile import ProfileManager
                p = ProfileManager()
                contact = p.find_contact(to)
                if contact and contact.email:
                    clean_to = sanitize_email(contact.email)
                else:
                    return f"No email found for {to}."

            msg = MIMEMultipart()
            msg['To'] = clean_to
            msg['Subject'] = subject
            msg['From'] = 'athuldev743@gmail.com'
            msg.attach(MIMEText(body, 'plain'))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(
                userId='me', body={'raw': raw}
            ).execute()
            return f"✓ Email sent to {clean_to}"
        except Exception as e:
            return f"Send error: {str(e)}"


class SendEmailWithResumeTool(BaseTool):
    name = "send_email_resume"
    description = "Send email with correct resume attached based on role"

    def run(self, *args, **kwargs) -> str:
        to = kwargs.get("to") or (args[0] if len(args) > 0 else "")
        subject = kwargs.get("subject") or (args[1] if len(args) > 1 else "")
        body = kwargs.get("body") or (args[2] if len(args) > 2 else "")
        role = kwargs.get("role") or (args[3] if len(args) > 3 else "")

        # Always sanitize the target recipient email FIRST
        clean_to = sanitize_email(to)

        # Handle edge case where recipient and role swapped positions
        if not clean_to or '@' not in clean_to:
            all_vals = [str(to), str(subject), str(body), str(role)]
            found_email = next((v for v in all_vals if '@' in v), "")
            if found_email:
                clean_to = sanitize_email(found_email)

        print(f"[SendEmailWithResume] Resolved -> 'to': '{clean_to}', 'role': '{role}', 'subject': '{subject}'")

        if not clean_to or '@' not in clean_to:
            err_msg = f"Send error: Invalid recipient email address provided ('{to}')."
            print(f"[SendEmailWithResume] ERROR: {err_msg}")
            return err_msg

        try:
            from src.tools.auto_apply_tool import get_resume_for_role
            from src.memory.profile import ProfileManager
            service = get_gmail_service()

            resume_path, resume_label = get_resume_for_role(role)

            p = ProfileManager()
            display_name = p.get("name") or "Athul Dev"
            display_email = p.get("email") or "athuldev743@gmail.com"
            display_phone = p.get("phone") or "+91 70343 06102"
            portfolio = p.get("portfolio") or "https://port-folio-phpa.vercel.app"
            github = p.get("github") or "https://github.com/athuldev743-cp"

            plain_body = body or "Please find my attached resume."
            display_role = role or "AI Engineer"

            msg = MIMEMultipart('mixed')
            # CRITICAL: Always use clean_to here!
            msg['To'] = clean_to
            msg['From'] = 'athuldev743@gmail.com'
            msg['Subject'] = subject if subject and '@' not in subject else f"Application for {display_role} — {display_name}"

            alt_part = MIMEMultipart('alternative')
            alt_part.attach(MIMEText(plain_body, 'plain'))

            html_body = build_html_email(
                name=display_name, role=display_role, email=display_email,
                phone=display_phone, portfolio=portfolio, github=github,
                cover_letter_body=plain_body,
            )
            alt_part.attach(MIMEText(html_body, 'html'))

            msg.attach(alt_part)

            if os.path.exists(resume_path):
                with open(resume_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    filename = os.path.basename(resume_path)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{filename}"'
                    )
                    msg.attach(part)

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            response = service.users().messages().send(
                userId='me', body={'raw': raw}
            ).execute()

            return f"✅ Email successfully dispatched to {clean_to} with {resume_label} attached."

        except Exception as e:
            stack_trace = traceback.format_exc()
            print(f"[SendEmailWithResume] CRITICAL ERROR: {str(e)}\n{stack_trace}")
            return f"Send error: {str(e)}"


class SendResumeEmailTool(BaseTool):
    name = "send_resume_email"
    description = "Send resume/portfolio via email to a person or recruiter"

    def run(self, *args, **kwargs) -> str:
        to_arg = kwargs.get("to") or (args[0] if len(args) > 0 else "")
        role_arg = kwargs.get("role") or (args[1] if len(args) > 1 else "AI Engineer")
        name_arg = kwargs.get("name") or (args[2] if len(args) > 2 else "Hiring Manager")

        print(f"[SendResumeEmailTool] Intercepted call with args={args}, kwargs={kwargs}")
        print(f"[SendResumeEmailTool] Resolved -> to: '{to_arg}', role: '{role_arg}', name: '{name_arg}'")

        clean_to = sanitize_email(to_arg)
        if not clean_to:
            return "Send error: Destination email address is required."

        try:
            from src.memory.profile import ProfileManager
            p = ProfileManager()
            portfolio = p.get('portfolio') or 'https://port-folio-phpa.vercel.app'
            github = p.get('github') or 'https://github.com/athuldev743-cp'

            subject = f"Application for {role_arg} — Athul Dev"
            body = f"""Dear {name_arg},

I am writing to express my strong interest in the {role_arg} role.

Specializing in Python, FastAPI, React, and autonomous AI systems, I build production-grade platforms with tools integration, memory management, and scalable API architecture.

🌐 Portfolio: {portfolio}
💻 GitHub: {github}
📧 athuldev743@gmail.com
📱 +91 70343 06102

Best regards,
Athul Dev"""

            return SendEmailWithResumeTool().run(
                to=clean_to,
                subject=subject,
                body=body,
                role=role_arg
            )
        except Exception as e:
            print(f"[SendResumeEmailTool] Error: {str(e)}")
            return f"Send error: {str(e)}"


class SummarizeInboxTool(BaseTool):
    name = "summarize_inbox"
    description = "Summarize recent emails from Gmail inbox"

    def run(self, count: int = 10) -> str:
        try:
            service = get_gmail_service()
            results = service.users().messages().list(
                userId='me', maxResults=count
            ).execute()
            messages = results.get('messages', [])
            if not messages:
                return "Inbox is empty."
            summaries = []
            for msg in messages[:count]:
                m = service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata',
                    metadataHeaders=['From', 'Subject']
                ).execute()
                headers = {h['name']: h['value'] for h in m['payload']['headers']}
                summaries.append(
                    f"- {headers.get('Subject', 'No subject')} "
                    f"from {headers.get('From', 'Unknown')}"
                )
            return "Recent inbox:\n" + "\n".join(summaries)
        except Exception as e:
            return f"Error: {str(e)}"