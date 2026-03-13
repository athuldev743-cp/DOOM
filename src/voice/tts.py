import pyttsx3

engine = pyttsx3.init()

# Set voice properties
engine.setProperty('rate', 175)
engine.setProperty('volume', 1.0)

# Use a better voice if available
voices = engine.getProperty('voices')
for voice in voices:
    if 'david' in voice.name.lower() or 'mark' in voice.name.lower():
        engine.setProperty('voice', voice.id)
        break

def speak(text: str):
    print(f"[Voice] Speaking...")
    engine.say(text)
    engine.runAndWait()

def list_voices():
    for i, voice in enumerate(voices):
        print(f"{i}: {voice.name} — {voice.id}")