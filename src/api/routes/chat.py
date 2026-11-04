import json
import os
import asyncio
import re
from fastapi import APIRouter, Depends, Response, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from src.api.schemas import ChatRequest, CommandRequest, ApplyJobRequest, OpenJobRequest, PrepareJobRequest, ApproveJobRequest, SendJobEmailRequest
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

@router.post("/api/jobs/prepare")
async def prepare_job(payload: PrepareJobRequest, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from datetime import datetime
    from src.memory.database import SessionLocal, JobApplication
    from src.tools.resume_builder import generate_tailored_cv, generate_cover_letter

    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter_by(job_id=payload.job_id).first()
        if application is None:
            raise HTTPException(status_code=404, detail="Job application record not found")
        if application.status in ("approved", "opened", "email_sent", "submitted"):
            raise HTTPException(status_code=409, detail="This application has already been approved or submitted")
        try:
            cv_path = generate_tailored_cv(
                application.id, application.title, application.company, application.description or ""
            )
            cover_letter = generate_cover_letter(
                application.title, application.company, application.description or ""
            )
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Could not generate application documents: {str(exc)}")
        application.cv_path = cv_path
        application.cover_letter = cover_letter
        application.status = "prepared"
        application.prepared_at = datetime.utcnow()
        db.commit()
        return {
            "success": True,
            "status": application.status,
            "cv_url": f"/api/jobs/{application.job_id}/cv",
            "cover_letter": application.cover_letter,
            "title": application.title,
            "company": application.company,
        }
    finally:
        db.close()


@router.get("/api/jobs/{job_id}/cv")
async def download_job_cv(job_id: int, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from pathlib import Path
    from src.memory.database import SessionLocal, JobApplication
    from src.tools.resume_builder import generated_cv_path

    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter_by(job_id=job_id).first()
        if application is None or not application.cv_path:
            raise HTTPException(status_code=404, detail="Generated CV not found")
        try:
            cv_path = generated_cv_path(application.cv_path)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid generated CV path")
        if not cv_path.is_file():
            raise HTTPException(status_code=404, detail="Generated CV file is missing")
        return FileResponse(str(cv_path), media_type="application/pdf", filename=cv_path.name)
    finally:
        db.close()


@router.post("/api/jobs/approve")
async def approve_job(payload: ApproveJobRequest, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from datetime import datetime
    from src.memory.database import SessionLocal, JobApplication
    from src.tools.resume_builder import generated_cv_path, is_valid_recipient_email

    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter_by(job_id=payload.job_id).first()
        if application is None:
            raise HTTPException(status_code=404, detail="Job application record not found")
        if application.status != "prepared" or not application.cv_path or not application.cover_letter:
            raise HTTPException(status_code=409, detail="Prepare the CV and cover letter before approval")
        try:
            cv_path = generated_cv_path(application.cv_path)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid generated CV path")
        if not cv_path.is_file():
            raise HTTPException(status_code=404, detail="Generated CV file is missing")
        if payload.recipient_email:
            recipient = payload.recipient_email.strip()
            if not is_valid_recipient_email(recipient):
                raise HTTPException(status_code=422, detail="Recipient email is invalid")
            application.recipient_email = recipient
        if payload.cover_letter is not None:
            if not payload.cover_letter.strip():
                raise HTTPException(status_code=422, detail="Cover letter cannot be empty")
            application.cover_letter = payload.cover_letter.strip()
        application.status = "approved"
        application.approved_at = datetime.utcnow()
        db.commit()
        return {"success": True, "status": application.status, "recipient_email": application.recipient_email}
    finally:
        db.close()


@router.post("/api/jobs/send-email")
async def send_application_email(payload: SendJobEmailRequest, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from datetime import datetime
    from src.memory.database import SessionLocal, JobApplication
    from src.tools.email_tool import send_approved_application_email

    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter_by(job_id=payload.job_id).first()
        if application is None:
            raise HTTPException(status_code=404, detail="Job application record not found")
        if application.approved_at is None or application.status not in ("approved", "opened"):
            raise HTTPException(status_code=409, detail="Approve this application before sending an email")
        if application.email_sent_at is not None:
            raise HTTPException(status_code=409, detail="Application email has already been sent")
        if not application.recipient_email:
            raise HTTPException(status_code=422, detail="Add and approve a recipient email first")
        if not application.cv_path or not application.cover_letter:
            raise HTTPException(status_code=409, detail="Approved CV and cover letter are required")

        subject = f"Application for {application.title} — Athul Dev"
        result = send_approved_application_email(
            application.recipient_email, subject, application.cover_letter, application.cv_path
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.message)
        application.status = "email_sent"
        application.email_sent_at = datetime.utcnow()
        db.commit()
        return {"success": True, "status": application.status, "message": result.message}
    finally:
        db.close()


@router.post("/api/jobs/open")
async def open_job(payload: OpenJobRequest, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from datetime import datetime
    from urllib.parse import urlparse
    from src.memory.database import SessionLocal, JobApplication
    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter_by(job_id=payload.job_id).first()
        if application is None:
            raise HTTPException(status_code=404, detail="Job application record not found")
        if application.approved_at is None or application.status not in ("approved", "opened", "email_sent"):
            raise HTTPException(status_code=409, detail="Prepare and approve this application before opening the listing")
        parsed_url = urlparse(application.job_url or "")
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Job listing URL is invalid")
        if application.status == "approved":
            application.status = "opened"
        application.opened_at = application.opened_at or datetime.utcnow()
        db.commit()
        return {"success": True, "apply_url": application.job_url, "status": application.status}
    finally:
        db.close()


@router.post("/api/jobs/confirm-submitted")
async def confirm_job_submitted(payload: OpenJobRequest, identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from datetime import datetime
    from src.memory.database import SessionLocal, JobApplication
    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter_by(job_id=payload.job_id).first()
        if application is None:
            raise HTTPException(status_code=404, detail="Job application record not found")
        if application.approved_at is None or application.opened_at is None:
            raise HTTPException(status_code=409, detail="Approve and open the job listing before confirming submission")
        if application.status == "submitted":
            raise HTTPException(status_code=409, detail="Submission is already recorded")
        application.status = "submitted"
        application.submitted_at = datetime.utcnow()
        db.commit()
        return {"success": True, "status": application.status}
    finally:
        db.close()


@router.get("/api/jobs/applications")
async def list_job_applications(identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from src.memory.database import SessionLocal, JobApplication
    db = SessionLocal()
    try:
        records = db.query(JobApplication).order_by(JobApplication.created_at.desc()).limit(100).all()
        return {"applications": [{
            "id": item.id, "job_id": item.job_id, "title": item.title,
            "company": item.company, "job_url": item.job_url,
            "status": item.status, "cv_path": item.cv_path,
            "recipient_email": item.recipient_email,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "prepared_at": item.prepared_at.isoformat() if item.prepared_at else None,
            "approved_at": item.approved_at.isoformat() if item.approved_at else None,
            "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
            "email_sent_at": item.email_sent_at.isoformat() if item.email_sent_at else None,
        } for item in records]}
    finally:
        db.close()


@router.post("/api/apply-single-job")
async def apply_single_job():
    raise HTTPException(status_code=410, detail="Use the reviewed job-open and submission-confirmation workflow")


@router.post("/api/send-email-job")
async def send_email_job(identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    raise HTTPException(status_code=410, detail="Email applications are disabled until per-job CV approval is implemented")


@router.post("/api/send-email-all")
async def send_email_all(identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    raise HTTPException(status_code=410, detail="Bulk application emails are disabled; each application requires individual approval")


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
async def apply_job(identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    raise HTTPException(status_code=410, detail="Automatic sending is disabled; use the reviewed application workflow")


@router.get("/api/stats/success-rate")
async def success_rate(identity: Identity = Depends(get_current_identity)):
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")
    from src.memory.database import SessionLocal, JobApplication
    db = SessionLocal()
    try:
        total = db.query(JobApplication).count()
        submitted = db.query(JobApplication).filter_by(status="submitted").count()
        rate = round((submitted / total) * 100, 1) if total else 0
        return {"total": total, "applied": submitted, "failed": total - submitted, "rate": rate}
    finally:
        db.close()
