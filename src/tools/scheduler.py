import asyncio
import threading
from datetime import datetime, time
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

    def stop(self):
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
                    briefing = tool.run()
                    # Save to a file so app can serve it
                    with open("data/daily_briefing.txt", "w", encoding="utf-8") as f:
                        f.write(briefing)
                    last_briefing_date = now.date()
                    print(f"[Scheduler] Daily briefing generated at {now}")
                except Exception as e:
                    print(f"[Scheduler] Error: {e}")

            # Check every 30 seconds
            import time as t
            t.sleep(30)

scheduler = Scheduler()