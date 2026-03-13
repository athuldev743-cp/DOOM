import os
import requests
from src.tools.base import BaseTool
from src.memory.profile import ProfileManager


def get_whatsapp_headers():
    token = os.getenv("WHATSAPP_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def send_whatsapp_message(to_number: str, message: str) -> dict:
    phone_id = os.getenv("WHATSAPP_PHONE_ID")
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }

    res = requests.post(url, json=payload, headers=get_whatsapp_headers())
    return res.json()


def send_whatsapp_template(to_number: str, template_name: str = "hello_world") -> dict:
    phone_id = os.getenv("WHATSAPP_PHONE_ID")
    
    url = f"https://graph.facebook.com/v22.0/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en_US"}
        }
    }

    res = requests.post(url, json=payload, headers=get_whatsapp_headers())
    return res.json()

class WhatsAppSendTool(BaseTool):
    name = "whatsapp_api_send"
    description = "Send WhatsApp message directly via API — no app needed"

    def run(self, name: str = "", message: str = "") -> str:
        try:
            p = ProfileManager()

            # Look up contact number
            contact = p.find_contact(name)
            if contact and contact.phone:
                number = contact.phone.replace("+", "").replace(" ", "").replace("-", "")
            elif name.replace("+", "").replace(" ", "").isdigit():
                number = name.replace("+", "").replace(" ", "")
            else:
                return f"WA_NOT_FOUND:{name}"

            print(f"[WhatsApp API] Sending to {number}: {message}")

            # Send hello_world template — works with test number
            result = send_whatsapp_template(number, "hello_world")
            print(f"[WhatsApp API] Template result: {result}")

            if result.get("messages"):
                msg_id = result["messages"][0].get("id", "")
                return f"✅ WhatsApp sent to {name}! (Message ID: {msg_id[:20]}...)"
            else:
                error = result.get("error", {}).get("message", "Unknown error")
                return f"❌ WhatsApp failed: {error}"

        except Exception as e:
            return f"WhatsApp API error: {str(e)}"


class WhatsAppBroadcastTool(BaseTool):
    name = "whatsapp_broadcast"
    description = "Send WhatsApp message to multiple contacts"

    def run(self, message: str = "", group: str = "all") -> str:
        try:
            p = ProfileManager()
            contacts = p.get_all_contacts()

            if not contacts:
                return "No contacts found."

            results = []
            tool = WhatsAppSendTool()

            for contact in contacts:
                if contact.phone:
                    result = tool.run(name=contact.name, message=message)
                    results.append(f"• {contact.name}: {'✅' if '✅' in result else '❌'}")

            return "Broadcast complete!\n" + "\n".join(results)

        except Exception as e:
            return f"Broadcast error: {str(e)}"
class WhatsAppResumeTool(BaseTool):
    name = "whatsapp_api_resume"
    description = "Send resume via WhatsApp API to a contact"

    def run(self, name: str = "") -> str:
        try:
            p = ProfileManager()
            portfolio = p.get('portfolio') or 'https://port-folio-phpa.vercel.app'
            github = p.get('github') or 'https://github.com/athuldev743-cp'

            message = (
                f"Hi! I'm Athul Dev, a Backend & AI Developer from Kochi.\n\n"
                f"🌐 Portfolio: {portfolio}\n"
                f"💻 GitHub: {github}\n"
                f"📧 athuldev743@gmail.com\n"
                f"📱 +91 70343 06102\n\n"
                f"Would love to connect about opportunities!"
            )

            tool = WhatsAppSendTool()
            return tool.run(name=name, message=message)

        except Exception as e:
            return f"WhatsApp resume error: {str(e)}"