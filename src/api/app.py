import asyncio
import json
import re
import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.agent.core import Agent
from src.memory.database import init_db


app = FastAPI(title="DOOM AI")

os.makedirs("src/api/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
agent = Agent(session_id="athul-main")

class ChatRequest(BaseModel):
    message: str

class CommandRequest(BaseModel):
    command: str
    args: str = ""

@app.get("/manifest.json")
async def manifest():
    return FileResponse(
        "src/api/manifest.json",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/sw.js")
async def service_worker():
    return FileResponse("src/api/sw.js", media_type="application/javascript")

@app.on_event("startup")
async def warmup_tts():
    from src.voice.tts_server import text_to_speech
    common = ["Got it.", "Done.", "Sure thing.", "Let me check.", "Here's what I found."]
    for phrase in common:
        await text_to_speech(phrase)
    print("[TTS] Warmup complete")

@app.on_event("startup")
async def startup():
    from src.tools.scheduler import scheduler
    scheduler.start()
    print("[DOOM] Scheduler started")


@app.get("/briefing")
async def get_briefing():
    from src.tools.briefing_tool import DailyBriefingTool
    tool = DailyBriefingTool()
    return {"briefing": tool.run()}        



@app.get("/", response_class=HTMLResponse)
async def root():
    with open("src/api/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    from src.voice.tts_server import text_to_speech
    import asyncio
    
    # Get LLM response
    response = await agent.chat(request.message)
    
    # Generate TTS in parallel immediately
    try:
        audio_path = await text_to_speech(response)
        audio_url = f"/static/tts_cache/{os.path.basename(audio_path)}" if audio_path else None
    except:
        audio_url = None
    
    return {"response": response, "audio_url": audio_url}

@app.post("/chat-stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        # Get LLM response first
        response = await agent.chat(request.message)
        
        # Send text immediately
        yield f"data: {json.dumps({'type': 'text', 'content': response})}\n\n"
        
        # Generate TTS sentence by sentence
        from src.voice.tts_server import text_to_speech
        sentences = re.split(r'(?<=[.!?])\s+', response)
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
                print(f"TTS error: {e}")
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/speak")
def speak_text(request: ChatRequest):
    from src.voice.tts_server import text_to_speech
    file_path = text_to_speech(request.message)
    if not file_path:
        return {"error": "empty"}
    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=3600"}
    )


@app.post("/command")
async def run_command(request: CommandRequest):
    from src.tools.automation import AutomationTool
    tool = AutomationTool()
    result = tool.run(command=request.command, args=request.args)
    return {"result": result}

@app.get("/reminders")
async def get_reminders():
    from src.tools.registry import get_tool
    tool = get_tool("list_reminders")
    result = tool.run()
    return {"reminders": result}

@app.delete("/reset")
async def reset():
    agent.reset()
    return {"status": "cleared"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    os.makedirs("data/documents", exist_ok=True)
    filepath = f"data/documents/{file.filename}"
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    from src.memory.rag import ingest_pdf, ingest_text
    if file.filename.endswith(".pdf"):
        result = ingest_pdf(filepath)
    else:
        result = ingest_text(filepath)
    return {"result": result}

@app.get("/docs-list")
async def docs_list():
    from src.memory.rag import list_docs
    return {"docs": list_docs()}



@app.get("/memory")
async def get_memory():
    from src.memory.profile import ProfileManager
    p = ProfileManager()
    profile = p.get_all()
    contacts = p.list_contacts()
    return {
        "profile": profile,
        "contacts": contacts
    }


@app.get("/linkedin/auth")
async def linkedin_auth():
    from src.tools.linkedin_tool import get_auth_url
    from fastapi.responses import RedirectResponse
    return RedirectResponse(get_auth_url())

@app.get("/linkedin/callback")
async def linkedin_callback(code: str = None, error: str = None):
    from src.tools.linkedin_tool import exchange_code, save_token, get_profile
    from fastapi.responses import HTMLResponse
    
    if error:
        return HTMLResponse(f"<h2>❌ LinkedIn auth failed: {error}</h2>")
    
    if not code:
        return HTMLResponse("<h2>❌ No code received</h2>")
    
    try:
        token_data = exchange_code(code)
        save_token(token_data)
        
        # Get profile
        profile = get_profile(token_data["access_token"])
        name = profile.get("name", "")
        
        # Save to profile
        from src.memory.profile import ProfileManager
        p = ProfileManager()
        p.set("linkedin_name", name, "linkedin")
        p.set("linkedin_email", profile.get("email", ""), "linkedin")
        
        return HTMLResponse(f"""
        <html>
        <body style="background:#080808;color:#e8e8e8;font-family:sans-serif;
                     display:flex;align-items:center;justify-content:center;height:100vh;">
          <div style="text-align:center">
            <h1 style="color:#ff3333">DOOM</h1>
            <h2>✅ LinkedIn Connected!</h2>
            <p>Welcome {name}</p>
            <p style="color:#555">You can close this tab and return to DOOM.</p>
          </div>
        </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h2>❌ Error: {str(e)}</h2>")

@app.get("/linkedin/status")
async def linkedin_status():
    from src.tools.linkedin_tool import get_token, get_profile
    token = get_token()
    if not token:
        return {"connected": False, "auth_url": "/linkedin/auth"}
    try:
        profile = get_profile(token)
        return {"connected": True, "name": profile.get("name", "")}
    except:
        return {"connected": False, "auth_url": "/linkedin/auth"}