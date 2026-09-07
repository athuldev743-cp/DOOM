from src.tools.base import BaseTool
from src.memory.profile import ProfileManager
from src.tools.schemas import (
    ToolResult, CallContactArgs, AddContactArgs,
    ListContactsArgs, SetProfileArgs, GetProfileArgs,
)

profile = ProfileManager()


class CallContactTool(BaseTool):
    name = "call_contact"
    description = "Call someone by name using phone's native dialer"
    args_schema = CallContactArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"name": raw.strip()}

    def run(self, name: str) -> ToolResult:
        contact = profile.find_contact(name)
        if not contact:
            return ToolResult(
                success=False,
                message=f"Contact '{name}' not found.",
                raw=f"CALL_NOT_FOUND:{name}",
            )
        return ToolResult(
            success=True,
            message=f"Calling {contact.name}",
            raw=f"CALL:{contact.phone}:{contact.name}",
        )


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
    args_schema = AddContactArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        parts = raw.split("|")
        return {
            "name": parts[0].strip() if parts else "",
            "phone": parts[1].strip() if len(parts) > 1 else "",
            "relationship": parts[2].strip() if len(parts) > 2 else "",
            "notes": parts[3].strip() if len(parts) > 3 else "",
        }

    def run(self, name: str, phone: str = "", relationship: str = "", notes: str = "") -> ToolResult:
        result = profile.add_contact(name=name, phone=phone,
                                      relationship=relationship, notes=notes)
        return ToolResult(success=True, message=str(result))


class ListContactsTool(BaseTool):
    name = "list_contacts"
    description = "List all saved contacts"
    args_schema = ListContactsArgs

    def run(self) -> ToolResult:
        return ToolResult(success=True, message=profile.list_contacts())


class SetProfileTool(BaseTool):
    name = "set_profile"
    description = "Save personal information about Athul — goals, preferences, skills"
    args_schema = SetProfileArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        parts = raw.split("|")
        return {
            "key": parts[0].strip() if parts else "",
            "value": parts[1].strip() if len(parts) > 1 else "",
        }

    def run(self, key: str, value: str, category: str = "general") -> ToolResult:
        profile.set(key, value, category)
        return ToolResult(success=True, message=f"✓ Saved: {key} = {value}")


class GetProfileTool(BaseTool):
    name = "get_profile"
    description = "Get Athul's personal information, goals, preferences"
    args_schema = GetProfileArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"key": raw.strip() if raw and raw != "none" else ""}

    def run(self, key: str = "") -> ToolResult:
        if key:
            val = profile.get(key)
            if val:
                return ToolResult(success=True, message=f"{key}: {val}")
            return ToolResult(success=False, message=f"No info saved for: {key}")

        all_p = profile.get_all()
        if not all_p:
            return ToolResult(success=True, message="No profile info saved yet.")

        listing = "\n".join(f"- {k}: {v}" for k, v in all_p.items())
        return ToolResult(success=True, message=listing, data={"profile": all_p})