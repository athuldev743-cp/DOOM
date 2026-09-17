import time

from fastapi import APIRouter
from src.agent.core import Agent

router = APIRouter(prefix="/test", tags=["Testing"])


@router.get("/latency")
async def test_latency():
    agent = Agent()

    # CALL 1 — cold
    start = time.perf_counter()
    response1 = await agent.chat("what time is it")
    cold_time = time.perf_counter() - start

    # CALL 2 — warm, same Agent/process
    start = time.perf_counter()
    response2 = await agent.chat("what time is it")
    warm_time = time.perf_counter() - start

    return {
        "status": "success",
        "cold": {
            "latency_seconds": round(cold_time, 3),
            "response": response1,
        },
        "warm": {
            "latency_seconds": round(warm_time, 3),
            "response": response2,
        },
    }