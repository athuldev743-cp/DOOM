import time

from fastapi import APIRouter, Depends, HTTPException

from src.agent.core import Agent
from src.api.deps import Identity, get_current_identity

router = APIRouter(prefix="/test", tags=["Testing"])


@router.get("/latency")
async def test_latency(identity: Identity = Depends(get_current_identity)):
    # This endpoint triggers real LLM requests, so it must never be public.
    if not identity.is_owner:
        raise HTTPException(status_code=403, detail="Owner authentication required")

    agent = Agent(session_id="latency-test", is_owner=True)

    start = time.perf_counter()
    response = await agent.chat("what time is it")
    elapsed = time.perf_counter() - start

    return {
        "status": "success",
        "latency_seconds": round(elapsed, 3),
        "response": response,
        "note": "Includes LLM provider selection and tool execution; not a pure API-server benchmark.",
    }
