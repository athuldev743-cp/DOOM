from src.tools.base import BaseTool
from src.memory.profile import ProfileManager
from datetime import datetime

class DailyBriefingTool(BaseTool):
    name = "daily_briefing"
    description = "Generate Athul's personalized morning briefing"

    def run(self) -> str:
        try:
            p = ProfileManager()
            now = datetime.now()
            hour = now.hour

            if hour < 12:
                greeting = "Good morning"
            elif hour < 17:
                greeting = "Good afternoon"
            else:
                greeting = "Good evening"

            name = p.get('name') or 'Athul'
            day = now.strftime("%A, %B %d %Y")
            time_str = now.strftime("%I:%M %p")

            briefing = f"{greeting} {name}! 🔥\n"
            briefing += f"📅 {day} — {time_str}\n\n"

            # Reminders — fast DB call
            try:
                from src.tools.registry import get_tool
                reminder_tool = get_tool('list_reminders')
                reminders = reminder_tool.run()
                if 'No reminders' not in reminders:
                    briefing += f"⏰ REMINDERS:\n{reminders}\n"
            except:
                pass

            # Job applications
            try:
                import json
                apps = p.get('job_applications')
                if apps:
                    app_list = json.loads(apps)
                    pending = [a for a in app_list if a.get('status') == 'applied']
                    if pending:
                        briefing += f"💼 {len(pending)} job application(s) pending response\n"
            except:
                pass

            # Career goal
            goal = p.get('career_goal')
            if goal:
                briefing += f"\n🎯 GOAL: {goal}\n"

            # Daily tip
            tips = [
                "Apply to 2 jobs today.",
                "Follow up on pending applications.",
                "Update your LinkedIn profile.",
                "Learn one new Docker concept today.",
                "Push code to GitHub today.",
                "Reach out to one recruiter today.",
                "Practice one DSA problem today.",
            ]
            tip = tips[now.weekday() % len(tips)]
            briefing += f"💡 TODAY: {tip}"

            return briefing

        except Exception as e:
            return f"Briefing error: {str(e)}"