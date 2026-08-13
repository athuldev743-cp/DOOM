from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter()


@router.get("/manifest.json")
async def manifest():
    return FileResponse(
        "src/api/manifest.json",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/sw.js")
async def service_worker():
    return FileResponse("src/api/sw.js", media_type="application/javascript")


@router.get("/briefing")
async def get_briefing():
    from src.tools.briefing_tool import DailyBriefingTool

    tool = DailyBriefingTool()
    return {"briefing": tool.run()}


@router.get("/", response_class=HTMLResponse)
async def root():
    with open("src/api/index.html", "r", encoding="utf-8") as f:
        return f.read()