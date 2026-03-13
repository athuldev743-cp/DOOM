import os
import re
import subprocess
import webbrowser
from src.tools.base import BaseTool


class AutomationTool(BaseTool):
    name = "automate"
    description = "Control the PC — open apps, websites, search, volume, screenshot"

    SITES = {
        "youtube": "https://youtube.com",
        "google": "https://google.com",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "calendar": "https://calendar.google.com",
        "maps": "https://maps.google.com",
        "linkedin": "https://linkedin.com",
        "twitter": "https://twitter.com",
        "whatsapp": "https://web.whatsapp.com",
        "chatgpt": "https://chat.openai.com",
        "netflix": "https://netflix.com",
        "spotify": "https://open.spotify.com",
    }

    APPS = {
        "calculator": "calc.exe",
        "notepad": "notepad.exe",
        "explorer": "explorer.exe",
        "vscode": "code",
        "terminal": "cmd.exe",
        "powershell": "powershell.exe",
        "paint": "mspaint.exe",
        "task manager": "taskmgr.exe",
    }

    def _open_in_chrome(self, url: str):
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        for path in chrome_paths:
            if os.path.exists(path):
                subprocess.Popen([path, url])
                return
        webbrowser.open(url)

    def _extract_query(self, full: str, remove_words: list) -> str:
        query = full
        for word in remove_words:
            query = re.sub(rf"\b{re.escape(word)}\b", "", query)
        return re.sub(r"\s+", " ", query).strip()

    def _youtube_play(self, query: str) -> str:
     api_key = os.getenv("YOUTUBE_API_KEY")
     if api_key:
        try:
            from googleapiclient.discovery import build
            youtube = build('youtube', 'v3', developerKey=api_key)
            response = youtube.search().list(
                part='snippet',
                q=query,
                maxResults=1,
                type='video'
            ).execute()
            if response.get('items'):
                video_id = response['items'][0]['id']['videoId']
                title = response['items'][0]['snippet']['title']
                self._open_in_chrome(f"https://www.youtube.com/watch?v={video_id}")
                return f"🎵 Playing: {title}"
        except Exception as e:
            print(f"YouTube API error: {e}")
     self._open_in_chrome(f"https://youtube.com/results?search_query={query.replace(' ', '+')}")


    def run(self, command: str, args: str = "") -> str:
        full = f"{command} {args}".lower().strip()

        # --- SITES ---
        # YouTube (check before generic site loop)
        if "youtube" in full or "play" in full:
         query = self._extract_query(full, ["search", "youtube", "open", "play", "find", "for", "me", "on"])
        if query:
         return self._youtube_play(query)
        else:
         self._open_in_chrome("https://youtube.com")
        return "✓ Opened YouTube in Chrome"

        # Google search
        if "search" in full or "google" in full:
            query = self._extract_query(full, ["search", "google", "for", "me", "on"])
            if query:
                self._open_in_chrome(
                    f"https://google.com/search?q={query.replace(' ', '+')}"
                )
                return f"✓ Searched Google for: {query}"
            else:
                self._open_in_chrome("https://google.com")
                return "✓ Opened Google in Chrome"

        # Other sites
        for site, url in self.SITES.items():
            if re.search(rf"\b{re.escape(site)}\b", full):
                self._open_in_chrome(url)
                return f"✓ Opened {site} in Chrome"

        # --- APPS ---
        for app_name, exe in self.APPS.items():
            if re.search(rf"\b{re.escape(app_name)}\b", full):
                subprocess.Popen(exe, shell=True)
                return f"✓ Opened {app_name}"

        # --- VOLUME ---
        if "volume up" in full or "increase volume" in full:
            import pyautogui

            for _ in range(5):
                pyautogui.press("volumeup")
            return "✓ Volume increased"

        if "volume down" in full or "decrease volume" in full:
            import pyautogui

            for _ in range(5):
                pyautogui.press("volumedown")
            return "✓ Volume decreased"

        if "mute" in full:
            import pyautogui

            pyautogui.press("volumemute")
            return "✓ Muted"

        # --- SCREENSHOT ---
        if "screenshot" in full:
            import pyautogui
            from datetime import datetime

            path = os.path.expanduser("~/Desktop")
            filename = os.path.join(
                path, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            pyautogui.screenshot(filename)
            return f"✓ Screenshot saved to Desktop: {os.path.basename(filename)}"

        # --- SYSTEM ---
        if "lock" in full:
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
            return "✓ PC locked"

        if "cancel shutdown" in full:
            subprocess.run("shutdown /a", shell=True)
            return "✓ Shutdown cancelled"

        if "shutdown" in full:
            subprocess.run("shutdown /s /t 10", shell=True)
            return "✓ Shutting down in 10 seconds — say 'cancel shutdown' to stop"

        if "restart" in full:
            subprocess.run("shutdown /r /t 10", shell=True)
            return "✓ Restarting in 10 seconds"

        return f"I don't know how to do: {command}"