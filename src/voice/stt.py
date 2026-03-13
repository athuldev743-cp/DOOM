import speech_recognition as sr

recognizer = sr.Recognizer()

def listen() -> str:
    with sr.Microphone() as source:
        print("[Voice] Adjusting for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("[Voice] Listening... speak now!")
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            print("[Voice] Processing speech...")
            text = recognizer.recognize_google(audio)
            print(f"[Voice] You said: {text}")
            return text
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[Voice] STT error: {e}")
            return ""