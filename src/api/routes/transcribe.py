import base64
import os
import tempfile

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from groq import Groq

router = APIRouter()

_client = None


def _get_groq_client():
    """Create the transcription client only when the endpoint is used."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Audio transcription is unavailable: GROQ_API_KEY is not configured.",
            )
        _client = Groq(api_key=api_key)
    return _client


class TranscribeRequest(BaseModel):
    audio_b64: str
    format: str = "wav"


@router.post("/transcribe")
async def transcribe_audio(req: TranscribeRequest):
    client = _get_groq_client()
    tmp_path = None

    try:
        audio_bytes = base64.b64decode(req.audio_b64, validate=True)
        suffix = f".{req.format.lstrip('.')}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio_bytes)
            tmp_path = handle.name

        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(tmp_path, audio_file.read()),
                model="whisper-large-v3",
                language="en",
                response_format="json",
            )

        return {"text": transcription.text}

    except Exception as exc:
        return {"text": "", "error": str(exc)}

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
