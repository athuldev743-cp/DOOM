import threading
from datetime import datetime
import time as t
from src.tools.briefing_tool import DailyBriefingTool


class Scheduler:
    def __init__(self):
        self.running = False
        self.thread = None
        self.briefing_hour = 8  # 8 AM daily briefing

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print(f"[Scheduler] Started — daily briefing at {self.briefing_hour}:00 AM")

    def shutdown(self):
        self.running = False

    def _run(self):
        last_briefing_date = None
        while self.running:
            now = datetime.now()
            # Send briefing at 8 AM once per day
            if (now.hour == self.briefing_hour and
                now.minute == 0 and
                last_briefing_date != now.date()):
                try:
                    tool = DailyBriefingTool()
                    result = tool.run()
                    if result.success:
                        with open("data/daily_briefing.txt", "w", encoding="utf-8") as f:
                            f.write(result.message)
                        print(f"[Scheduler] Daily briefing generated at {now}")
                    else:
                        print(f"[Scheduler] Briefing generation failed: {result.message}")
                    last_briefing_date = now.date()
                except Exception as e:
                    print(f"[Scheduler] Error: {e}")
            t.sleep(30)


scheduler = Scheduler()