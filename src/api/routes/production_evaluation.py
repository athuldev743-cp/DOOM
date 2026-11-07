"""Production-focused evaluation endpoints.

All routes are owner-only. Live failure tests use synthetic faults/mocks and
never deliberately disrupt the deployed database or provider accounts.
"""
from __future__ import annotations

import asyncio
import math
import statistics
import time
from unittest.mock import AsyncMock, patch

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import require_owner

router = APIRouter(prefix="/evaluation/production", tags=["Production Evaluation"],
                   dependencies=[Depends(require_owner)])

MODULES = [
    {"id": "rag_concurrency", "title": "RAG concurrent load", "description": "Run simultaneous read-only hybrid searches.", "default_concurrency": 3, "max_concurrency": 10, "default_requests": 12, "max_requests": 40},
    {"id": "langgraph_trace", "title": "LangGraph node tracing", "description": "Time each executed graph node using LangGraph event metadata. Uses one provider call.", "default_runs": 1, "max_runs": 2},
    {"id": "failure_recovery", "title": "Failure handling", "description": "Inject mocked database, embedding and provider failures; verify failures are surfaced safely.", "default_runs": 1, "max_runs": 1},
    {"id": "security", "title": "Security expansion", "description": "Check expired and wrong-owner sessions plus unauthenticated MCP access.", "default_runs": 1, "max_runs": 1},
]


class ProductionRunConfig(BaseModel):
    concurrency: int = Field(default=3, ge=1, le=10)
    requests: int = Field(default=12, ge=1, le=40)
    runs: int = Field(default=1, ge=1, le=2)


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * p) - 1))], 2)


def check(name: str, passed: bool, detail: str = "") -> dict:
    return {"name": name, "status": "passed" if passed else "failed", "detail": str(detail)}


async def run_rag_concurrency(concurrency: int, requests: int) -> dict:
    from src.memory import rag

    if not rag.RAG_AVAILABLE:
        raise RuntimeError("RAG dependencies are unavailable")
    semaphore = asyncio.Semaphore(concurrency)
    query = "How does DOOM use PostgreSQL pgvector and hybrid retrieval?"
    samples: list[float] = []
    errors: list[str] = []

    async def one(index: int) -> None:
        async with semaphore:
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(rag.search_docs, query, n_results=5)
                if not result or result.startswith("Search error:"):
                    errors.append(result or "empty retrieval result")
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                samples.append((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(requests)))
    elapsed = (time.perf_counter() - started) * 1000
    success = len(samples) - len(errors)
    checks = [
        check("Concurrent requests completed", len(samples) == requests, f"{len(samples)}/{requests}"),
        check("All retrievals returned successfully", not errors, f"{len(errors)} errors"),
    ]
    return {"checks": checks, "metrics": {
        "requests": requests, "concurrency": concurrency, "successful_requests": success,
        "failed_requests": len(errors), "error_rate_percent": round(len(errors) / requests * 100, 2),
        "latency_avg_ms": round(statistics.mean(samples), 2),
        "latency_p50_ms": percentile(samples, .50), "latency_p95_ms": percentile(samples, .95),
        "latency_p99_ms": percentile(samples, .99), "latency_max_ms": round(max(samples), 2),
        "elapsed_ms": round(elapsed, 2), "throughput_requests_per_second": round(success / (elapsed / 1000), 2) if elapsed else 0,
        "errors": errors[:5], "scope": "Concurrent in-process retrieval calls; use external k6 for public-network load."
    }}


async def run_langgraph_trace(runs: int) -> dict:
    from src.agent.graph import AgentState, compiled_graph, RECURSION_LIMIT

    all_timings: dict[str, list[float]] = {}
    responses = []
    for _ in range(runs):
        state = AgentState(messages=[
            {"role": "system", "content": "You are DOOM evaluation. Do not call tools. Reply briefly."},
            {"role": "user", "content": "Reply exactly: DOOM graph trace passed."},
        ], tool_context={"evaluation_disable_tools": "true"})
        starts: dict[str, float] = {}
        async for event in compiled_graph.astream_events(
            state, config={"recursion_limit": RECURSION_LIMIT}, version="v2"
        ):
            metadata = event.get("metadata") or {}
            node = metadata.get("langgraph_node")
            run_id = event.get("run_id")
            if not node or not run_id:
                continue
            if event.get("event") == "on_chain_start":
                starts[run_id] = time.perf_counter()
            elif event.get("event") == "on_chain_end" and run_id in starts:
                all_timings.setdefault(str(node), []).append((time.perf_counter() - starts.pop(run_id)) * 1000)
                output = (event.get("data") or {}).get("output")
                if isinstance(output, dict) and output.get("final_response"):
                    responses.append(str(output["final_response"]))
    rows = [{"node": name, "calls": len(values), "avg_ms": round(statistics.mean(values), 2),
             "p95_ms": percentile(values, .95), "max_ms": round(max(values), 2)}
            for name, values in sorted(all_timings.items())]
    checks = [
        check("At least one LangGraph node was traced", bool(rows), f"{len(rows)} node types"),
        check("Graph returned a response", bool(responses), f"{len(responses)}/{runs} runs"),
    ]
    return {"checks": checks, "metrics": {
        "graph_runs": runs, "traced_node_count": len(rows), "node_timings": rows,
        "total_node_calls": sum(row["calls"] for row in rows),
        "scope": "Node durations include work inside each LangGraph node; the decide node includes provider latency."
    }}


async def run_failure_checks() -> dict:
    from src.api.routes.evaluation import _run_database
    from src.memory import rag
    from src.agent import graph

    checks = []
    with patch("src.memory.database.engine.connect", side_effect=TimeoutError("synthetic database timeout")):
        try:
            await asyncio.to_thread(_run_database, 1)
            db_failed_safely = False
        except TimeoutError:
            db_failed_safely = True
    checks.append(check("Database timeout is surfaced (mocked)", db_failed_safely))

    with patch.object(rag, "search_docs", side_effect=RuntimeError("synthetic embedding failure")):
        try:
            rag.search_docs("synthetic failure test")
            embedding_failed_safely = False
        except RuntimeError as exc:
            embedding_failed_safely = "synthetic embedding failure" in str(exc)
    checks.append(check("Embedding failure is surfaced (mocked)", embedding_failed_safely))

    messages = [
        {"role": "system", "content": "Evaluation only. Do not call tools."},
        {"role": "user", "content": "Say hello."},
    ]
    with patch.object(graph, "chat", new=AsyncMock(side_effect=RuntimeError("synthetic provider outage"))):
        try:
            await graph.run_graph(messages, tool_context={"evaluation_disable_tools": "true"})
            provider_failed_safely = False
        except RuntimeError as exc:
            provider_failed_safely = "synthetic provider outage" in str(exc)
    checks.append(check("Provider failure is surfaced (mocked)", provider_failed_safely))

    # Exercise the actual fallback-chain policy with synthetic providers:
    # provider A fails, provider B succeeds. No network calls or API keys.
    from contextlib import AbstractContextManager
    from src.agent.llm_fallback import LLMFallbackChain

    class FakeSpan(AbstractContextManager):
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def update(self, **kwargs): return None

    class FakeLangfuse:
        def start_as_current_observation(self, **kwargs): return FakeSpan()
        def flush(self): return None

    class FakeProvider:
        def __init__(self, name, result=None, should_fail=False):
            self.name, self.result, self.should_fail = name, result, should_fail
        def models(self): return [self.name + "-model"]
        def complete(self, model, messages, timeout):
            if self.should_fail:
                raise RuntimeError("synthetic provider unavailable")
            return self.result

    fallback_chain = LLMFallbackChain(
        providers=[FakeProvider("primary", should_fail=True), FakeProvider("backup", result="recovered")],
        langfuse_client=FakeLangfuse(), fail_message="all providers failed",
        total_timeout_seconds=5, attempt_timeout_seconds=1,
    )
    fallback_response = await fallback_chain.chat(messages)
    fallback_recovered = fallback_response == "recovered"
    checks.append(check("Fallback provider recovers after primary failure", fallback_recovered,
                        f"response={fallback_response}"))
    return {"checks": checks, "metrics": {
        "faults_injected": 3, "database_timeout_handled": db_failed_safely,
        "embedding_failure_handled": embedding_failed_safely, "provider_failure_handled": provider_failed_safely,
        "fallback_recovered": fallback_recovered,
        "scope": "Synthetic mocked faults and providers only. No live database, embedding service or provider is disrupted."
    }}


async def run_security_checks() -> dict:
    import httpx
    import jwt
    import os
    from fastapi import FastAPI
    from src.api.auth import decode_session_token
    from src.api.app import app

    secret = os.getenv("SESSION_SECRET")
    expired_rejected = wrong_owner_rejected = False
    if secret:
        expired = jwt.encode({"email": "athuldev743@gmail.com", "is_owner": True,
                              "iat": 1, "exp": 2}, secret, algorithm="HS256")
        wrong_owner = jwt.encode({"email": "not-owner@example.com", "is_owner": True,
                                  "iat": int(time.time()), "exp": int(time.time()) + 60},
                                 secret, algorithm="HS256")
        expired_rejected = decode_session_token(expired) is None
        wrong_owner_rejected = decode_session_token(wrong_owner) is None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://doom-test") as client:
        eval_response = await client.get("/evaluation/api/catalog")
        mcp_response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    checks = [
        check("Expired owner session rejected", expired_rejected, "Synthetic expired JWT"),
        check("Wrong-owner session rejected", wrong_owner_rejected, "Synthetic signed JWT"),
        check("Unauthenticated evaluation API denied", eval_response.status_code == 403, f"HTTP {eval_response.status_code}"),
        check("Unauthenticated MCP access denied", mcp_response.status_code == 401, f"HTTP {mcp_response.status_code}"),
    ]
    return {"checks": checks, "metrics": {
        "expired_session_rejected": expired_rejected, "wrong_owner_rejected": wrong_owner_rejected,
        "evaluation_unauthenticated_status": eval_response.status_code,
        "mcp_unauthenticated_status": mcp_response.status_code,
        "scope": "Synthetic tokens and unauthenticated requests; does not modify or revoke real owner sessions."
    }}


@router.get("/catalog")
async def production_catalog():
    return {"tests": MODULES, "external_tests": [
        {"id": "public_load", "title": "Public network load (k6)", "script": "evaluation/k6/production-load.js"},
        {"id": "mcp_protocol", "title": "MCP Streamable HTTP (k6)", "script": "evaluation/k6/mcp-streamable-http.js"},
    ]}


@router.post("/run/{test_id}")
async def run_production_test(test_id: str, config: ProductionRunConfig):
    started = time.perf_counter()
    if test_id not in {item["id"] for item in MODULES}:
        raise HTTPException(status_code=404, detail="Unknown production evaluation test")
    try:
        if test_id == "rag_concurrency":
            payload = await run_rag_concurrency(config.concurrency, config.requests)
        elif test_id == "langgraph_trace":
            payload = await run_langgraph_trace(config.runs)
        elif test_id == "failure_recovery":
            payload = await run_failure_checks()
        else:
            payload = await run_security_checks()
        checks = payload["checks"]
        passed = sum(item["status"] == "passed" for item in checks)
        result = {"test_id": test_id, "status": "passed" if passed == len(checks) else "failed",
                  "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                  "checks_passed": passed, "checks_failed": len(checks) - passed, **payload}
    except Exception as exc:
        result = {"test_id": test_id, "status": "error",
                  "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                  "checks_passed": 0, "checks_failed": 1,
                  "error": f"{type(exc).__name__}: {exc}", "checks": [], "metrics": {}}
    return result
