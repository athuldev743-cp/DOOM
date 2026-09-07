import os
import re
import subprocess
import webbrowser
from src.tools.base import BaseTool
from src.tools.schemas import ToolResult, AutomationArgs


class AutomationTool(BaseTool):
    name = "automate"
    description = "Control the PC — open apps, websites, search, volume, screenshot"
    args_schema = AutomationArgs

    @classmethod
    def parse_args(cls, raw: str) -> dict:
        return {"command": raw.strip()}

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

    def _youtube_play(self, query: str) -> dict:
        """Returns {'url': str, 'title': str | None} — title is set only
        when the YouTube API found a direct video match; run() builds the
        final ToolResult (and its legacy wire string) from this."""
        api_key = os.getenv("YOUTUBE_API_KEY")
        if api_key:
            try:
                from googleapiclient.discovery import build

                youtube = build("youtube", "v3", developerKey=api_key)
                response = (
                    youtube.search()
                    .list(
                        part="snippet",
                        q=query,
                        maxResults=1,
                        type="video",
                    )
                    .execute()
                )

                if response.get("items"):
                    video_id = response["items"][0]["id"]["videoId"]
                    title = response["items"][0]["snippet"]["title"]
                    return {"url": f"https://www.youtube.com/watch?v={video_id}", "title": title}

            except Exception as e:
                print(f"YouTube API error: {e}")

        return {
            "url": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}",
            "title": None,
        }

    def run(self, command: str, args: str = "") -> ToolResult:
        full = f"{command} {args}".lower().strip()

        # --- YOUTUBE ---
        # Check before generic site loop
        if "youtube" in full or "play" in full:
            query = self._extract_query(
                full,
                ["search", "youtube", "open", "play", "find", "for", "me", "on"],
            )
            if query:
                yt = self._youtube_play(query)
                if yt["title"]:
                    return ToolResult(
                        success=True,
                        message=f"Playing: {yt['title']}",
                        raw=f"YOUTUBE:{yt['url']}|{yt['title']}",
                    )
                return ToolResult(
                    success=True,
                    message="Opening YouTube search results",
                    raw=f"YOUTUBE:{yt['url']}",
                )
            return ToolResult(success=True, message="Opening YouTube", raw="APP:https://youtube.com")

        # --- GOOGLE SEARCH ---
        if "search" in full or "google" in full:
            query = self._extract_query(full, ["search", "google", "for", "me", "on"])
            if query:
                url = f"https://google.com/search?q={query.replace(' ', '+')}"
                return ToolResult(success=True, message=f"Searching Google for: {query}", raw=f"APP:{url}")
            return ToolResult(success=True, message="Opening Google", raw="APP:https://google.com")

        # --- SITES ---
        for site, url in self.SITES.items():
            if re.search(rf"\b{re.escape(site)}\b", full):
                return ToolResult(success=True, message=f"Opening {site}", raw=f"APP:{url}")

        # --- APPS ---
        for app_name, exe in self.APPS.items():
            if re.search(rf"\b{re.escape(app_name)}\b", full):
                subprocess.Popen(exe, shell=True)
                return ToolResult(success=True, message=f"✓ Opened {app_name}")

        # --- VOLUME ---
        if "volume up" in full or "increase volume" in full:
            import pyautogui

            for _ in range(5):
                pyautogui.press("volumeup")
            return ToolResult(success=True, message="✓ Volume increased")

        if "volume down" in full or "decrease volume" in full:
            import pyautogui

            for _ in range(5):
                pyautogui.press("volumedown")
            return ToolResult(success=True, message="✓ Volume decreased")

        if "mute" in full:
            import pyautogui

            pyautogui.press("volumemute")
            return ToolResult(success=True, message="✓ Muted")

        # --- SCREENSHOT ---
        if "screenshot" in full:
            import pyautogui
            from datetime import datetime

            path = os.path.expanduser("~/Desktop")
            filename = os.path.join(
                path, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            pyautogui.screenshot(filename)
            return ToolResult(
                success=True,
                message=f"✓ Screenshot saved to Desktop: {os.path.basename(filename)}",
            )

        # --- SYSTEM ---
        if "lock" in full:
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
            return ToolResult(success=True, message="✓ PC locked")

        if "cancel shutdown" in full:
            subprocess.run("shutdown /a", shell=True)
            return ToolResult(success=True, message="✓ Shutdown cancelled")

        if "shutdown" in full:
            subprocess.run("shutdown /s /t 10", shell=True)
            return ToolResult(success=True, message="✓ Shutting down in 10 seconds — say 'cancel shutdown' to stop")

        if "restart" in full:
            subprocess.run("shutdown /r /t 10", shell=True)
            return ToolResult(success=True, message="✓ Restarting in 10 seconds")

        return ToolResult(success=False, message=f"I don't know how to do: {command}")