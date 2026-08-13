import base64
import tempfile
import os
from fastapi import APIRouter
from pydantic import BaseModel
from groq import Groq  # Import Groq instead of openai

router = APIRouter()

# Initialize Groq Client
# Ensure GROQ_API_KEY is in your Environment Variables (Local & Railway)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class TranscribeRequest(BaseModel):
    audio_b64: str
    format: str = "wav"

@router.post("/transcribe")
async def transcribe_audio(req: TranscribeRequest):
    tmp_path = None
    try:
        # 1. Decode base64 audio
        audio_bytes = base64.b64decode(req.audio_b64)
        
        # 2. Save to temp file
        suffix = f".{req.format}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        
        # 3. Transcribe with Groq (Whisper-large-v3)
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(tmp_path, f.read()), # Groq requires a tuple or file-like object
                model="whisper-large-v3",
                language="en",
                response_format="json"
            )
        
        return {"text": transcription.text}
    
    except Exception as e:
        return {"text": "", "error": str(e)}
    
    finally:
        # 4. Cleanup temp file regardless of success or failure
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)