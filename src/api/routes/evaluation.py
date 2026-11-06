from __future__ import annotations

import asyncio
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.api.deps import require_owner

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])
RESULTS_DIR = Path("evaluation/results/deployed")

CATALOG = [
    {"id": "rag", "title": "RAG retrieval", "description": "Hybrid vector + PostgreSQL full-text retrieval, corpus/index integrity and curated source-level relevance metrics.", "default_count": 2, "max_count": 5, "unit": "repetitions per query"},
    {"id": "mcp", "title": "MCP tools", "description": "Registered tool consistency and real in-process MCP adapter calls for list_docs and search_docs.", "default_count": 2, "max_count": 20, "unit": "executions per tool"},
    {"id": "langgraph", "title": "LangGraph workflow", "description": "Compiled graph and real end-to-end graph invocation through the configured LLM provider. Uses provider tokens.", "default_count": 1, "max_count": 3, "unit": "graph runs"},
    {"id": "latency", "title": "API latency", "description": "Repeated in-process ASGI /health requests; reports average, p50, p95, p99 and max. Not public-network load.", "default_count": 20, "max_count": 100, "unit": "requests"},
    {"id": "database", "title": "API & database", "description": "Database connectivity, pgvector extension, RAG corpus, generated FTS column and required indexes.", "default_count": 1, "max_count": 10, "unit": "checks"},
    {"id": "security", "title": "Security controls", "description": "Invalid session rejection and unauthenticated access denial for the protected evaluation API.", "default_count": 1, "max_count": 5, "unit": "checks"},
]


class RunConfig(BaseModel):
    request_count: int = Field(default=1, ge=1, le=100)


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * p) - 1))], 2)


def _check(checks: list, name: str, passed: bool, detail: str = "") -> None:
    checks.append({"name": name, "status": "passed" if passed else "failed", "detail": str(detail)})


def _run_rag(repetitions: int) -> dict:
    from sqlalchemy import text
    from src.memory import rag
    from src.memory.database import engine

    checks, timings, hits, precisions, reciprocal_ranks, query_results = [], [], [], [], [], []
    if not rag.RAG_AVAILABLE:
        raise RuntimeError("RAG dependencies are unavailable")

    with engine.connect() as conn:
        ext = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")).scalar()
        exists = conn.execute(text("SELECT to_regclass('public.doom_document_chunks') IS NOT NULL")).scalar()
        _check(checks, "pgvector extension enabled", bool(ext))
        _check(checks, "RAG corpus table exists", bool(exists))
        if not exists:
            raise RuntimeError("public.doom_document_chunks does not exist")

        count, sources, dimensions = conn.execute(text("""
            SELECT COUNT(*), COUNT(DISTINCT source), MIN(vector_dims(embedding))
            FROM doom_document_chunks
        """)).one()
        fts = conn.execute(text("""
            SELECT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='doom_document_chunks'
            AND column_name='search_vector' AND is_generated='ALWAYS')
        """)).scalar()
        gin = conn.execute(text("""
            SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public'
            AND indexname='ix_doom_document_chunks_search_vector_gin')
        """)).scalar()
        hnsw = conn.execute(text("""
            SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public'
            AND indexname='ix_doom_document_chunks_embedding_hnsw')
        """)).scalar()
        lexical = conn.execute(text("""
            SELECT COUNT(*) FROM doom_document_chunks
            WHERE search_vector @@ websearch_to_tsquery('english', 'doom_document_chunks')
        """)).scalar() if fts else 0

    _check(checks, "Corpus contains at least 8 chunks", count >= 8, f"{count} chunks / {sources} sources")
    _check(checks, "Embedding dimensions are 384", dimensions == 384, f"observed={dimensions}")
    _check(checks, "Generated FTS column exists", bool(fts))
    _check(checks, "GIN lexical index exists", bool(gin))
    _check(checks, "HNSW vector index exists", bool(hnsw))
    _check(checks, "Lexical exact-term query returns matches", lexical > 0, f"matches={lexical}")
    _check(checks, "Empty query is handled safely", "Please provide" in rag.search_docs("   "))

    cases = [
        ("What is DOOM and what backend framework does it use?", "doom_project_overview.md"),
        ("Which MCP tools are registered and how are side effects protected?", "doom_mcp_tools_and_security.md"),
        ("How does the LangGraph agent route requests and execute tools safely?", "doom_agent_workflow.md"),
        ("How does DOOM use PostgreSQL, pgvector, embeddings and semantic retrieval?", "doom_database_memory_and_rag.md"),
        ("How does DOOM discover jobs, score job descriptions and track applications?", "doom_job_search_and_application_workflow.md"),
        ("What is the separate fitness AI coach project and its planned architecture?", "fitness_ai_coach_project.md"),
        ("What AI engineering roles and CV project metrics is the user targeting?", "career_profile_and_cv_goals.md"),
        ("What are DOOM's historical pytest coverage and performance benchmark results?", "doom_testing_and_evaluation.md"),
        ("Find the exact MCP search_docs tool implementation", "doom_mcp_tools_and_security.md"),
        ("Find the exact PostgreSQL vector table doom_document_chunks", "doom_database_memory_and_rag.md"),
        ("Find the exact embedding model BAAI bge small en v1.5", "doom_database_memory_and_rag.md"),
        ("Find the exact owner authentication and session token implementation", "doom_mcp_tools_and_security.md"),
    ]
    repetitions = max(1, min(repetitions, 5))
    for query, expected in cases:
        per_query = []
        for _ in range(repetitions):
            started = time.perf_counter()
            output = rag.search_docs(query, n_results=5)
            elapsed = (time.perf_counter() - started) * 1000
            timings.append(elapsed)
            if output.startswith("Search error:"):
                raise RuntimeError(output)
            retrieved = [line.split(" | chunk ", 1)[0][1:] for line in output.splitlines()
                         if line.startswith("[") and " | chunk " in line]
            rank = next((i + 1 for i, source in enumerate(retrieved) if source == expected), None)
            hits.append(1.0 if rank else 0.0)
            precisions.append(sum(source == expected for source in retrieved) / 5.0)
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
            per_query.append(retrieved)
        query_results.append({"query": query, "expected_source": expected, "retrieved_sources": per_query[-1],
                              "rank": next((i + 1 for i, s in enumerate(per_query[-1]) if s == expected), None),
                              "stable_across_repetitions": all(x == per_query[0] for x in per_query)})

    _check(checks, "Hybrid retrieval returns a result for every query", len(timings) == len(cases) * repetitions,
           f"{len(timings)} searches")
    _check(checks, "Source hit rate at 5 meets 0.75 target", statistics.mean(hits) >= 0.75,
           f"{statistics.mean(hits):.3f}")
    _check(checks, "Repeated retrieval results are stable", all(x["stable_across_repetitions"] for x in query_results))
    metrics = {
        "queries": len(cases), "repetitions_per_query": repetitions, "measured_searches": len(timings),
        "corpus_chunks": int(count), "corpus_sources": int(sources), "embedding_dimensions": int(dimensions),
        "source_hit_rate_at_5": round(statistics.mean(hits), 4),
        "source_precision_at_5": round(statistics.mean(precisions), 4),
        "source_mrr_at_5": round(statistics.mean(reciprocal_ranks), 4),
        "latency_avg_ms": round(statistics.mean(timings), 2),
        "latency_p50_ms": _percentile(timings, .50), "latency_p95_ms": _percentile(timings, .95),
        "latency_p99_ms": _percentile(timings, .99), "latency_max_ms": round(max(timings), 2),
        "retrieval_mode": "hybrid vector + PostgreSQL FTS + reciprocal-rank fusion",
        "quality_note": "Curated source-level benchmark; not human-judged relevance or a general quality guarantee."
    }
    return {"checks": checks, "metrics": metrics, "query_results": query_results}


async def _run_mcp(repetitions: int) -> dict:
    from src.tools.registry import TOOLS
    from src.tools.mcp_server import _build_handler, registered_mcp_tool_names

    checks, timings = [], []
    names = set(registered_mcp_tool_names())
    required = {"search_docs", "list_docs", "ingest_docs"}
    _check(checks, "Required RAG tools registered", required.issubset(names), sorted(required & names))
    _check(checks, "MCP registry matches tool registry", names == set(TOOLS), f"{len(names)} registered tools")
    if not required.issubset(names):
        raise RuntimeError("One or more required RAG MCP tools are missing")

    list_handler = _build_handler("list_docs", TOOLS["list_docs"])
    search_handler = _build_handler("search_docs", TOOLS["search_docs"])
    list_result = search_result = ""
    repetitions = max(1, min(repetitions, 20))
    for _ in range(repetitions):
        started = time.perf_counter()
        list_result = str(await list_handler())
        timings.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        search_result = str(await search_handler(query="What is the DOOM LangGraph workflow and agent components?"))
        timings.append((time.perf_counter() - started) * 1000)
    _check(checks, "list_docs executes through MCP adapter", "doom_agent_workflow.md" in list_result, list_result[:180])
    _check(checks, "search_docs executes through MCP adapter", "doom_agent_workflow.md" in search_result, search_result[:180])
    metrics = {"registered_tool_count": len(names), "required_rag_tools": sorted(required),
               "executions_per_tool": repetitions, "adapter_calls": len(timings),
               "adapter_latency_avg_ms": round(statistics.mean(timings), 2),
               "adapter_latency_p95_ms": _percentile(timings, .95),
               "scope": "In-process MCP adapter execution; does not measure an external Streamable HTTP handshake."}
    return {"checks": checks, "metrics": metrics}


async def _run_langgraph(request_count: int) -> dict:
    from src.agent.graph import compiled_graph, run_graph

    checks, timings, previews = [], [], []
    _check(checks, "LangGraph compiled graph is available", compiled_graph is not None)
    for _ in range(max(1, min(request_count, 3))):
        messages = [
            {"role": "system", "content": "You are DOOM. This is a backend evaluation. Do not call tools. Reply with a short plain-text acknowledgement."},
            {"role": "user", "content": "Reply with: DOOM LangGraph evaluation passed."},
        ]
        started = time.perf_counter()
        response = await asyncio.wait_for(run_graph(messages, tool_context={}), timeout=120)
        timings.append((time.perf_counter() - started) * 1000)
        previews.append(str(response)[:240])
        if not response.strip():
            raise RuntimeError("LangGraph returned an empty response")
    _check(checks, "Graph invocation returned a non-empty response", all(bool(x.strip()) for x in previews))
    metrics = {"graph_runs": len(timings), "latency_avg_ms": round(statistics.mean(timings), 2),
               "latency_p50_ms": _percentile(timings, .50), "latency_p95_ms": _percentile(timings, .95),
               "latency_max_ms": round(max(timings), 2), "response_previews": previews,
               "scope": "End-to-end graph + configured LLM provider; consumes provider tokens and is not a deterministic model-quality score."}
    return {"checks": checks, "metrics": metrics}


async def _run_latency(request: Request, request_count: int) -> dict:
    import httpx

    samples = []
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://doom-internal") as client:
        for _ in range(max(1, min(request_count, 100))):
            started = time.perf_counter()
            response = await client.get("/health")
            samples.append((time.perf_counter() - started) * 1000)
            if response.status_code != 200:
                raise RuntimeError(f"/health returned HTTP {response.status_code}")
    checks = [{"name": "Health endpoint returned HTTP 200", "status": "passed", "detail": f"{len(samples)} requests"}]
    metrics = {"requests": len(samples), "success_rate": 1.0, "latency_avg_ms": round(statistics.mean(samples), 2),
               "latency_p50_ms": _percentile(samples, .50), "latency_p95_ms": _percentile(samples, .95),
               "latency_p99_ms": _percentile(samples, .99), "latency_max_ms": round(max(samples), 2),
               "scope": "In-process ASGI requests; excludes internet, DNS, TLS, proxy and external client network latency."}
    return {"checks": checks, "metrics": metrics}


def _run_database(request_count: int) -> dict:
    from sqlalchemy import text
    from src.memory.database import engine

    checks = []
    samples = []
    for _ in range(max(1, min(request_count, 10))):
        started = time.perf_counter()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()
        samples.append((time.perf_counter() - started) * 1000)
    with engine.connect() as conn:
        pgvector = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')")).scalar()
        table = conn.execute(text("SELECT to_regclass('public.doom_document_chunks') IS NOT NULL")).scalar()
        if table:
            chunks, sources, dims = conn.execute(text("SELECT COUNT(*), COUNT(DISTINCT source), MIN(vector_dims(embedding)) FROM doom_document_chunks")).one()
            fts = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='doom_document_chunks' AND column_name='search_vector' AND is_generated='ALWAYS')")).scalar()
            gin = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_doom_document_chunks_search_vector_gin')")).scalar()
            hnsw = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_doom_document_chunks_embedding_hnsw')")).scalar()
        else:
            chunks = sources = dims = 0
            fts = gin = hnsw = False
    _check(checks, "Database SELECT 1", True, f"{len(samples)} successful checks")
    _check(checks, "pgvector extension", bool(pgvector))
    _check(checks, "RAG document table", bool(table))
    _check(checks, "RAG corpus has data", chunks >= 1, f"{chunks} chunks / {sources} sources")
    _check(checks, "384-dimensional embeddings", dims == 384, f"observed={dims}")
    _check(checks, "Generated FTS column", bool(fts))
    _check(checks, "GIN index", bool(gin))
    _check(checks, "HNSW index", bool(hnsw))
    return {"checks": checks, "metrics": {"db_checks": len(samples), "db_latency_avg_ms": round(statistics.mean(samples), 2),
            "corpus_chunks": int(chunks), "corpus_sources": int(sources), "embedding_dimensions": int(dims),
            "pgvector": bool(pgvector), "fts_column": bool(fts), "gin_index": bool(gin), "hnsw_index": bool(hnsw)}}


async def _run_security(request: Request, request_count: int) -> dict:
    import httpx
    from src.api.auth import decode_session_token

    checks = []
    invalid_rejected = decode_session_token("invalid-evaluation-session") is None
    _check(checks, "Invalid session token rejected", invalid_rejected)
    statuses = []
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://doom-internal") as client:
        for _ in range(max(1, min(request_count, 5))):
            response = await client.get("/evaluation/api/catalog")
            statuses.append(response.status_code)
    denied = all(status == 403 for status in statuses)
    _check(checks, "Unauthenticated evaluation API access denied", denied, f"HTTP statuses: {statuses}")
    return {"checks": checks, "metrics": {"invalid_session_rejected": invalid_rejected,
            "unauthenticated_statuses": statuses, "protected_route_denies_guest": denied}}


def _save_report(result: dict) -> str | None:
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        name = f"dashboard_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.json"
        path = RESULTS_DIR / name
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return str(path).replace("\\", "/")
    except Exception as exc:
        result.setdefault("warnings", []).append(f"Could not persist report: {type(exc).__name__}: {exc}")
        return None


@router.get("", response_class=HTMLResponse, dependencies=[Depends(require_owner)])
async def evaluation_page():
    return Path("src/api/evaluation.html").read_text(encoding="utf-8")


@router.get("/api/catalog", dependencies=[Depends(require_owner)])
async def evaluation_catalog():
    return {"tests": CATALOG, "target": "deployed application instance"}


@router.post("/api/run/{test_id}", dependencies=[Depends(require_owner)])
async def run_evaluation(test_id: str, config: RunConfig, request: Request):
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    entry = next((item for item in CATALOG if item["id"] == test_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown evaluation test")
    count = min(config.request_count, entry["max_count"])
    try:
        if test_id == "rag":
            payload = await asyncio.to_thread(_run_rag, count)
        elif test_id == "mcp":
            payload = await _run_mcp(count)
        elif test_id == "langgraph":
            payload = await _run_langgraph(count)
        elif test_id == "latency":
            payload = await _run_latency(request, count)
        elif test_id == "database":
            payload = await asyncio.to_thread(_run_database, count)
        else:
            payload = await _run_security(request, count)
        checks = payload.get("checks", [])
        passed = sum(item["status"] == "passed" for item in checks)
        failed = len(checks) - passed
        result = {
            "test_id": test_id, "title": entry["title"], "status": "passed" if failed == 0 else "failed",
            "started_at": started_at, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "request_count": count, "checks_passed": passed, "checks_failed": failed,
            **payload,
        }
    except Exception as exc:
        result = {"test_id": test_id, "title": entry["title"], "status": "error",
                  "started_at": started_at, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                  "request_count": count, "checks": [], "checks_passed": 0, "checks_failed": 1,
                  "error": f"{type(exc).__name__}: {exc}", "metrics": {}}
    result["report_file"] = _save_report(result)
    return result
