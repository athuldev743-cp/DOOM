import codecs
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.api.deps import require_owner

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _upload_max_bytes() -> int:
    try:
        configured = int(os.getenv("DOCS_UPLOAD_MAX_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)))
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES
    return configured if configured > 0 else DEFAULT_MAX_UPLOAD_BYTES


def _destination_for(filename: str) -> tuple[Path, str]:
    safe_filename = (filename or "").strip()
    normalized = safe_filename.replace("\\", "/")
    if (
        not safe_filename
        or "/" in normalized
        or ":" in safe_filename
        or "\x00" in safe_filename
        or Path(normalized).name != normalized
    ):
        raise HTTPException(status_code=422, detail="A plain filename is required.")

    extension = Path(safe_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Only PDF, TXT, and Markdown documents are supported.",
        )

    docs_root = Path(os.getenv("DOCS_PATH", "./data/documents")).resolve()
    destination = (docs_root / safe_filename).resolve()
    if not destination.is_relative_to(docs_root):
        raise HTTPException(status_code=422, detail="Invalid upload filename.")
    return destination, extension


def _validate_initial_content(extension: str, content: bytes) -> codecs.IncrementalDecoder | None:
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=422, detail="Uploaded PDF content is invalid.")
        return None

    decoder = codecs.getincrementaldecoder("utf-8")()
    if b"\x00" in content:
        raise HTTPException(status_code=422, detail="Text documents cannot contain binary data.")
    try:
        decoder.decode(content)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Text documents must be UTF-8 encoded.") from exc
    return decoder


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    _identity=Depends(require_owner),
):
    destination, extension = _destination_for(file.filename or "")
    max_upload_bytes = _upload_max_bytes()
    created = False

    try:
        first_chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if len(first_chunk) > max_upload_bytes:
            raise HTTPException(status_code=413, detail="Upload exceeds the configured size limit.")
        text_decoder = _validate_initial_content(extension, first_chunk)

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as handle:
                created = True
                handle.write(first_chunk)
                total_bytes = len(first_chunk)

                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail="Upload exceeds the configured size limit.",
                        )
                    if text_decoder is not None:
                        if b"\x00" in chunk:
                            raise HTTPException(
                                status_code=422,
                                detail="Text documents cannot contain binary data.",
                            )
                        text_decoder.decode(chunk)
                    handle.write(chunk)

                if text_decoder is not None:
                    text_decoder.decode(b"", final=True)
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409,
                detail="A document with this filename already exists.",
            ) from exc

        from src.memory.rag import ingest_pdf, ingest_text

        result = ingest_pdf(str(destination)) if extension == ".pdf" else ingest_text(str(destination))
        return {"result": result}
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Text documents must be UTF-8 encoded.") from exc
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/docs-list")
async def docs_list(_identity=Depends(require_owner)):
    from src.memory.rag import list_docs
    return {"docs": list_docs()}
