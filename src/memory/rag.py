"""PostgreSQL + pgvector document retrieval for DOOM.

Uses the existing SQLAlchemy engine and the dedicated doom_document_chunks table.
The table is created by evaluation/seed_doom_knowledge.py.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

DOCS_PATH = os.getenv("DOCS_PATH", "./data/documents")
TABLE = "doom_document_chunks"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

try:
    from fastembed import TextEmbedding
    from src.memory.database import engine

    RAG_AVAILABLE = True
except ImportError:
    TextEmbedding = None
    engine = None
    RAG_AVAILABLE = False


@lru_cache(maxsize=1)
def _embedder():
    if not RAG_AVAILABLE:
        raise RuntimeError("FastEmbed or the DOOM database is unavailable.")
    return TextEmbedding(model_name=MODEL_NAME)


def chunk_text(content: str, chunk_size: int = 450, overlap: int = 60) -> list[str]:
    if chunk_size <= overlap or overlap < 0:
        raise ValueError("chunk_size must be greater than overlap >= 0")
    words = content.split()
    step = chunk_size - overlap
    return [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), step)]


def _vector_literal(values) -> str:
    values = list(values)
    if len(values) != EMBEDDING_DIM:
        raise ValueError(f"Expected {EMBEDDING_DIM} embedding dimensions, got {len(values)}")
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def _ingest_content(filename: str, content: str) -> str:
    if not RAG_AVAILABLE:
        return "RAG unavailable: FastEmbed or PostgreSQL dependencies are missing."
    chunks = chunk_text(content)
    if not chunks:
        return f"No text content found in {filename}."

    vectors = list(_embedder().embed(chunks))
    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding count does not match chunk count.")

    rows = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        digest = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
        rows.append({
            "source": filename,
            "chunk_index": index,
            "content": chunk,
            "content_hash": digest,
            "embedding": _vector_literal(vector),
        })

    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {TABLE} WHERE source = :source"),
            {"source": filename},
        )
        conn.execute(text(f"""
            INSERT INTO {TABLE}
                (source, chunk_index, content, content_hash, embedding)
            VALUES
                (:source, :chunk_index, :content, :content_hash, CAST(:embedding AS vector))
        """), rows)

    return f"Ingested {filename} — {len(chunks)} chunks indexed."


def ingest_pdf(filepath: str) -> str:
    if not RAG_AVAILABLE:
        return "RAG not available: required dependencies are missing."
    try:
        import pymupdf
    except ImportError:
        return "PDF ingestion unavailable: install pymupdf."
    path = Path(filepath)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return "Invalid PDF file path."
    try:
        with pymupdf.open(path) as doc:
            content = "\n".join(page.get_text() for page in doc)
        return _ingest_content(path.name, content)
    except Exception as exc:
        return f"PDF ingestion error: {type(exc).__name__}: {exc}"


def ingest_text(filepath: str) -> str:
    path = Path(filepath)
    if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
        return "Invalid text or Markdown file path."
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return _ingest_content(path.name, content)
    except Exception as exc:
        return f"Document ingestion error: {type(exc).__name__}: {exc}"


def ingest_folder(folder: str = DOCS_PATH) -> str:
    if not RAG_AVAILABLE:
        return "RAG not available: required dependencies are missing."
    root = Path(folder)
    if not root.is_dir():
        return f"Documents folder not found: {root}"
    results = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            results.append(ingest_pdf(str(path)))
        elif path.suffix.lower() in {".txt", ".md"}:
            results.append(ingest_text(str(path)))
    return "\n".join(results) if results else "No PDF, TXT, or Markdown documents found."



def search_docs(query: str, n_results: int = 3) -> str:
    import logging
    import time

    logger = logging.getLogger(__name__)
    total_start = time.perf_counter()
    stage = "validation"

    timings = {
        "embedding_ms": 0.0,
        "db_acquire_ms": 0.0,
        "sql_execution_ms": 0.0,
    }

    if not RAG_AVAILABLE:
        return "Document search unavailable: required dependencies are missing."

    query = (query or "").strip()
    if not query:
        return "Please provide a search query."

    try:
        limit = max(1, min(int(n_results), 20))
        candidate_limit = min(max(limit * 5, 20), 100)

        query_text = "Represent this sentence for searching relevant passages: " + query

        stage = "embedding"
        started = time.perf_counter()
        vector = next(_embedder().embed([query_text]))
        vector_sql = _vector_literal(vector)
        timings["embedding_ms"] = round(
            (time.perf_counter() - started) * 1000, 2
        )

        stage = "db_acquire"
        started = time.perf_counter()

        with engine.connect() as conn:
            timings["db_acquire_ms"] = round(
                (time.perf_counter() - started) * 1000, 2
            )

            stage = "sql_execution"
            started = time.perf_counter()

            rows = conn.execute(text(f"""
                WITH vector_candidates AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               ORDER BY embedding <=> CAST(:embedding AS vector)
                           ) AS position_rank
                    FROM {TABLE}
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :candidate_limit
                ),
                lexical_candidates AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank_cd(
                                   search_vector,
                                   websearch_to_tsquery('english', :query)
                               ) DESC
                           ) AS position_rank
                    FROM {TABLE}
                    WHERE search_vector @@ websearch_to_tsquery('english', :query)
                    ORDER BY ts_rank_cd(
                        search_vector,
                        websearch_to_tsquery('english', :query)
                    ) DESC
                    LIMIT :candidate_limit
                ),
                combined_ranks AS (
                    SELECT id, position_rank FROM vector_candidates
                    UNION ALL
                    SELECT id, position_rank FROM lexical_candidates
                ),
                fused_results AS (
                    SELECT id,
                           SUM(1.0 / (60.0 + position_rank)) AS rrf_score
                    FROM combined_ranks
                    GROUP BY id
                )
                SELECT d.source, d.content, d.chunk_index, f.rrf_score
                FROM fused_results f
                JOIN {TABLE} d ON d.id = f.id
                ORDER BY f.rrf_score DESC, d.source, d.chunk_index
                LIMIT :limit
            """), {
                "embedding": vector_sql,
                "query": query,
                "candidate_limit": candidate_limit,
                "limit": limit,
            }).mappings().all()

            timings["sql_execution_ms"] = round(
                (time.perf_counter() - started) * 1000, 2
            )

        total_ms = round((time.perf_counter() - total_start) * 1000, 2)

        logger.info(
            "[RAG_TIMING] embedding_ms=%.2f db_acquire_ms=%.2f "
            "sql_execution_ms=%.2f total_ms=%.2f rows=%d",
            timings["embedding_ms"],
            timings["db_acquire_ms"],
            timings["sql_execution_ms"],
            total_ms,
            len(rows),
        )

        if not rows:
            return "No relevant documents found."

        return "\n\n".join(
            f"[{row['source']} | chunk {row['chunk_index']}]\n{row['content']}"
            for row in rows
        )

    except Exception as exc:
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)

        logger.exception(
            "[RAG_FAILURE] stage=%s total_ms=%.2f timings=%s",
            stage,
            total_ms,
            timings,
        )

        return f"Search error: {type(exc).__name__}: {exc}"





def list_docs() -> str:
    if not RAG_AVAILABLE:
        return "Document listing unavailable: required dependencies are missing."
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT source, COUNT(*) AS chunks
                FROM {TABLE}
                GROUP BY source
                ORDER BY source
            """)).mappings().all()
        if not rows:
            return "No documents indexed yet."
        return "Indexed documents:\n" + "\n".join(
            f"- {row['source']} ({row['chunks']} chunks)" for row in rows
        )
    except Exception as exc:
        return f"Document listing error: {type(exc).__name__}: {exc}"
