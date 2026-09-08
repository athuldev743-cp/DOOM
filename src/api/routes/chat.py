import json
import os
import asyncio
import re
from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse, StreamingResponse
from src.api.schemas import ChatRequest, CommandRequest, ApplyJobRequest
from src.api.deps import agent, get_current_identity, Identity, VISITOR_COOKIE_NAME
from src.agent.core import Agent

router = APIRouter()

VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days — long enough to reconnect the same visitor


def _visitor_agent(identity: Identity) -> Agent:
    # A fresh Agent per request is fine here: MemoryManager loads/saves
    # history from the DB keyed by session_id, so there's no in-memory
    # state worth caching, and it guarantees no cross-visitor bleed.
    return Agent(session_id=f"visitor-{identity.visitor_key}", is_owner=False)


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    response: Response,
    identity: Identity = Depends(get_current_identity),
):
    if not identity.is_owner:
        response.set_cookie(
            VISITOR_COOKIE_NAME, identity.visitor_key,
            max_age=VISITOR_COOKIE_MAX_AGE, httponly=True, samesite="lax",
        )
        text_response = await _visitor_agent(identity).chat(request.message)
        # No TTS for visitor chat — keeps their responses fast, and voice
        # output isn't needed for an unauthenticated conversation.
        return {"response": text_response, "audio_url": None, "status": "ok"}

    from src.voice.tts_server import text_to_speech

    # Get text response immediately
    text_response = await agent.chat(request.message)

    # Generate TTS in background — don't block text response
    audio_url = None
    try:
        audio_path = await asyncio.wait_for(
            text_to_speech(text_response), timeout=5.0
        )
        if audio_path:
            filename = os.path.basename(audio_path)
            audio_url = f"/static/tts_cache/{filename}"
    except asyncio.TimeoutError:
        print("[TTS] Timeout — returning text only")
    except Exception as e:
        print(f"[TTS] Error: {e}")

    return {
        "response": text_response,
        "audio_url": audio_url,
        "status": "ok"
    }


@router.post("/chat-stream")
async def chat_stream(
    request: ChatRequest,
    identity: Identity = Depends(get_current_identity),
):
    async def generate():
        if not identity.is_owner:
            text_response = await _visitor_agent(identity).chat(request.message)
            yield f"data: {json.dumps({'type': 'text', 'content': text_response})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        response = await agent.chat(request.message)
        yield f"data: {json.dumps({'type': 'text', 'content': response})}\n\n"

        # Skip TTS entirely for structured/raw payloads — nothing here is speakable text
        SPECIAL_PREFIXES = ("JOBS_DATA:", "CALL:", "WHATSAPP:", "YOUTUBE:", "APP:")
        is_special = response.startswith(SPECIAL_PREFIXES) or "NOT_FOUND" in response

        if not is_special:
            from src.voice.tts_server import text_to_speech
            sentences = re.split(r"(?<=[.!?])\s+", response)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence or len(sentence) < 3:
                    continue
                try:
                    audio_path = await text_to_speech(sentence)
                    if audio_path:
                        filename = os.path.basename(audio_path)
                        yield f"data: {json.dumps({'type': 'audio', 'url': f'/static/tts_cache/{filename}'})}\n\n"
                except Exception as e:
                    print(f"[TTS] Sentence error: {e}")

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    resp = StreamingResponse(generate(), media_type="text/event-stream")
    if not identity.is_owner:
        # Set directly on this Response object — a dependency-injected
        # Response's Set-Cookie is dropped when the route returns its own
        # Response subclass (StreamingResponse here), so it has to happen
        # at this level to actually reach the browser.
        resp.set_cookie(
            VISITOR_COOKIE_NAME, identity.visitor_key,
            max_age=VISITOR_COOKIE_MAX_AGE, httponly=True, samesite="lax",
        )
    return resp


@router.post("/tts")
async def tts_endpoint(request: ChatRequest):
    """Generate TTS for any text — returns audio URL"""
    from src.voice.tts_server import text_to_speech
    try:
        audio_path = await text_to_speech(request.message)
        if audio_path:
            filename = os.path.basename(audio_path)
            return {
                "audio_url": f"/static/tts_cache/{filename}",
                "status": "ok"
            }
        return {"audio_url": None, "status": "empty"}
    except Exception as e:
        return {"audio_url": None, "status": "error", "error": str(e)}

@router.post("/api/apply-single-job")
async def apply_single_job(payload: dict):
    from src.tools.jobs_tool import apply_to_single_job
    return apply_to_single_job(payload.get("index"))


@router.post("/api/send-email-job")
async def send_email_job(payload: dict):
    from src.tools.jobs_tool import email_only_for_job
    return email_only_for_job(payload.get("index"))
    

@router.post("/api/send-email-all")
async def send_email_all():
    from src.tools.jobs_tool import JobSearchTool
    from src.tools.auto_apply_tool import BulkApplyTool
    JobSearchTool().run()  # ensures latest_job_search reflects the current pool
    result = BulkApplyTool().run()
    return {"result": result.message, "success": result.success}


@router.post("/speak")
async def speak_text(request: ChatRequest):
    from src.voice.tts_server import text_to_speech
    file_path = await text_to_speech(request.message)
    if not file_path:
        return {"error": "empty"}
    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/command")
async def run_command(request: CommandRequest):
    from src.tools.automation import AutomationTool
    tool = AutomationTool()
    result = tool.run(command=request.command, args=request.args)
    return {"result": result}


@router.get("/reminders")
async def get_reminders():
    from src.tools.registry import get_tool
    tool = get_tool("list_reminders")
    result = tool.run()
    return {"reminders": result}


@router.delete("/reset")
async def reset(identity: Identity = Depends(get_current_identity)):
    if identity.is_owner:
        agent.reset()
    else:
        _visitor_agent(identity).reset()
    return {"status": "cleared"}

@router.post("/api/apply-job")
async def apply_job(request: ApplyJobRequest):
    """Direct apply — bypasses the agent/LLM pipeline entirely for speed,
    since the frontend already knows exactly which job and args to send."""
    from src.tools.auto_apply_tool import AutoApplyTool
    tool = AutoApplyTool()
    result = tool.run(company=request.company, role=request.role, job_index=request.job_index)
    success = not ("❌" in result or "error" in result.lower())
    return {"result": result, "success": success}


@router.get("/api/stats/success-rate")
async def success_rate():
    import json
    from src.memory.profile import ProfileManager
    p = ProfileManager()
    history_raw = p.get("application_history") or "[]"
    try:
        records = json.loads(history_raw)
    except Exception:
        records = []

    total = len(records)
    applied = len([r for r in records if r.get("status") == "applied"])
    rate = round((applied / total) * 100, 1) if total else 0

    return {"total": total, "applied": applied, "failed": total - applied, "rate": rate}