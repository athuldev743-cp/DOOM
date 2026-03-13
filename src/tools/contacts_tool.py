from src.tools.base import BaseTool
from src.memory.profile import ProfileManager

profile = ProfileManager()

class CallContactTool(BaseTool):
    name = "call_contact"
    description = "Call someone by name using phone's native dialer"

    def run(self, name: str) -> str:
        contact = profile.find_contact(name)
        if not contact:
            return f"CALL_NOT_FOUND:{name}"
        return f"CALL:{contact.phone}:{contact.name}"

class WhatsAppContactTool(BaseTool):
    name = "whatsapp_contact"
    description = "Send WhatsApp message to contact by name"

    def run(self, name: str, message: str = "") -> str:
        # Check if sending resume
        resume_url = "https://port-folio-phpa.vercel.app"
        if any(word in message.lower() for word in ['resume', 'cv', 'portfolio']):
            message = f"Hi, I'm Athul Dev, a Full Stack Developer. Here's my portfolio: {resume_url}"

        contact = profile.find_contact(name)
        if not contact:
            # Try partial match on all contacts
            return f"WA_NOT_FOUND:{name}"
        
        number = contact.whatsapp or contact.phone
        number = number.replace("+", "").replace(" ", "").replace("-", "")
        
        if not message:
            message = ""
            
        return f"WHATSAPP:{number}:{message}"


class WhatsAppResumeTool(BaseTool):
    name = "whatsapp_resume"
    description = "Send resume/portfolio to a contact via WhatsApp"

    def run(self, name: str) -> str:
        contact = profile.find_contact(name)
        p = ProfileManager()
        portfolio = p.get('portfolio') or 'https://port-folio-phpa.vercel.app'
        github = p.get('github') or 'https://github.com/athuldev743-cp'
        
        if not contact:
            # Send to unknown number — ask user
            return f"WA_NOT_FOUND:{name}"
        
        number = contact.phone.replace("+", "").replace(" ", "")
        message = f"Hi! I'm Athul Dev, Full Stack Developer from Kochi.\n\n🌐 Portfolio: {portfolio}\n💻 GitHub: {github}\n📧 athuldev743@gmail.com\n\nLooking for backend/AI roles. Let's connect!"
        
        return f"WHATSAPP:{number}:{message}"

class AddContactTool(BaseTool):
    name = "add_contact"
    description = "Add or update a contact in DOOM's memory"

    def run(self, name: str, phone: str = "", relationship: str = "", notes: str = "") -> str:
        return profile.add_contact(name=name, phone=phone,
                                   relationship=relationship, notes=notes)

class ListContactsTool(BaseTool):
    name = "list_contacts"
    description = "List all saved contacts"

    def run(self) -> str:
        return profile.list_contacts()

class SetProfileTool(BaseTool):
    name = "set_profile"
    description = "Save personal information about Athul — goals, preferences, skills"

    def run(self, key: str, value: str, category: str = "general") -> str:
        profile.set(key, value, category)
        return f"✓ Saved: {key} = {value}"

class GetProfileTool(BaseTool):
    name = "get_profile"
    description = "Get Athul's personal information, goals, preferences"

    def run(self, key: str = "") -> str:
        if key:
            val = profile.get(key)
            return f"{key}: {val}" if val else f"No info saved for: {key}"
        all_p = profile.get_all()
        if not all_p:
            return "No profile info saved yet."
        return "\n".join(f"- {k}: {v}" for k, v in all_p.items())