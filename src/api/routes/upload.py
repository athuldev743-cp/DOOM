import os
import shutil
from fastapi import APIRouter, File, UploadFile

router = APIRouter()


@router.post("/upload")
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


@router.get("/docs-list")
async def docs_list():
    from src.memory.rag import list_docs
    return {"docs": list_docs()}