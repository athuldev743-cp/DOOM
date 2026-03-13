import os
import json
import tempfile
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from src.tools.base import BaseTool

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None

    # Load credentials.json from env (Railway)
    creds_json = os.getenv("GMAIL_CREDENTIALS_JSON")
    if creds_json:
        try:
            tmp_creds = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False
            )
            tmp_creds.write(creds_json)
            tmp_creds.close()
            os.environ['GOOGLE_CREDENTIALS_FILE'] = tmp_creds.name
        except Exception as e:
            print(f"[Gmail] Credentials env error: {e}")

    # Load token from env (Railway)
    token_json = os.getenv("GMAIL_TOKEN_JSON")
    if token_json:
        try:
            tmp_token = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False
            )
            tmp_token.write(token_json)
            tmp_token.close()
            creds = Credentials.from_authorized_user_file(tmp_token.name, SCOPES)
        except Exception as e:
            print(f"[Gmail] Token env error: {e}")

    # Fall back to local files
    if not creds and os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds:
        raise Exception("Gmail credentials not found. Set GMAIL_TOKEN_JSON on Railway.")

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if not token_json:
                with open('token.json', 'w') as f:
                    f.write(creds.to_json())

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

    def run(self, to: str, subject: str, body: str) -> str:
        try:
            service = get_gmail_service()
            if '@' not in to:
                from src.memory.profile import ProfileManager
                p = ProfileManager()
                contact = p.find_contact(to)
                if contact and contact.email:
                    to = contact.email
                else:
                    return f"No email found for {to}."
            msg = MIMEMultipart()
            msg['To'] = to
            msg['Subject'] = subject
            msg['From'] = 'athuldev743@gmail.com'
            msg.attach(MIMEText(body, 'plain'))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(
                userId='me', body={'raw': raw}
            ).execute()
            return f"✓ Email sent to {to}"
        except Exception as e:
            return f"Send error: {str(e)}"


class SendEmailWithResumeTool(BaseTool):
    name = "send_email_resume"
    description = "Send email with correct resume attached based on role"

    def run(self, to: str, subject: str, body: str, role: str = "") -> str:
        try:
            from src.tools.auto_apply_tool import get_resume_for_role
            service = get_gmail_service()

            resume_path, resume_label = get_resume_for_role(role)

            msg = MIMEMultipart()
            msg['To'] = to
            msg['Subject'] = subject
            msg['From'] = 'athuldev743@gmail.com'
            msg.attach(MIMEText(body, 'plain'))

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
                print(f"[Resume] Attached: {resume_label} — {filename}")
            else:
                print(f"[Resume] Not found: {resume_path} — sending without attachment")

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(
                userId='me', body={'raw': raw}
            ).execute()

            return f"✅ Sent to {to} with {resume_label} resume"

        except Exception as e:
            return f"Send error: {str(e)}"


class SendResumeEmailTool(BaseTool):
    name = "send_resume_email"
    description = "Send resume/portfolio via email"

    def run(self, to: str, name: str = "Hiring Manager") -> str:
        try:
            from src.memory.profile import ProfileManager
            p = ProfileManager()
            portfolio = p.get('portfolio') or 'https://port-folio-phpa.vercel.app'
            github = p.get('github') or 'https://github.com/athuldev743-cp'
            subject = "Application — Athul Dev | Full Stack Developer"
            body = f"""Dear {name},

I'm Athul Dev, a Full Stack Developer from Kochi, Kerala.

🌐 Portfolio: {portfolio}
💻 GitHub: {github}
📧 athuldev743@gmail.com
📱 +91 70343 06102

I'd love to discuss opportunities with your team.

Best regards,
Athul Dev"""
            tool = SendEmailTool()
            return tool.run(to=to, subject=subject, body=body)
        except Exception as e:
            return f"Error: {str(e)}"


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