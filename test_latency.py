import asyncio
import time

from src.agent.core import Agent


async def main():
    agent = Agent()

    print("\n=== CALL 1 (cold) ===")
    response1 = await agent.chat("what time is it")
    print(response1)

    print("\n=== CALL 2 (warm — same process) ===")
    response2 = await agent.chat("what time is it")
    print(response2)

asyncio.run(main())
