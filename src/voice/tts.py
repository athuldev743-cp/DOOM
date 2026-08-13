import os
import edge_tts

try:
    import pyttsx3
    _engine = pyttsx3.init()
    _engine.setProperty('rate', 175)
    _engine.setProperty('volume', 1.0)
    _PYTTSX3_AVAILABLE = True
except Exception:
    _PYTTSX3_AVAILABLE = False


def speak_local(text: str):
    """Fallback for offline local terminal testing."""
    if not _PYTTSX3_AVAILABLE:
        print("[Voice] pyttsx3 / espeak unavailable in this environment.")
        return
    print(f"[Voice] Speaking locally...")
    _engine.say(text)
    _engine.runAndWait()


async def speak(text: str, output_path: str = "src/api/static/speech.mp3") -> str:
    """Cloud-friendly async TTS."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+15%")
    await communicate.save(output_path)
    return output_path