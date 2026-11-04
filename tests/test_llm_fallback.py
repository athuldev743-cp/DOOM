import asyncio
from contextlib import contextmanager

from src.agent.llm_fallback import LLMFallbackChain


class FakeSpan:
    def __init__(self):
        self.updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)


class FakeLangfuse:
    def __init__(self):
        self.spans = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        span = FakeSpan()
        self.spans.append(span)
        yield span

    def flush(self):
        pass


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.received_timeout = None

    def models(self):
        return ["model-a"]

    def complete(self, model, messages, timeout):
        self.received_timeout = timeout
        return "hello"


def test_fallback_passes_bounded_timeout_and_returns_response():
    provider = FakeProvider()
    langfuse = FakeLangfuse()
    chain = LLMFallbackChain(
        [provider], langfuse, "unavailable",
        total_timeout_seconds=3, attempt_timeout_seconds=2,
    )

    result = asyncio.run(chain.chat([{"role": "user", "content": "hi"}]))

    assert result == "hello"
    assert provider.received_timeout == 2
    assert langfuse.spans[0].updates[0]["metadata"]["attempted_models"] == 1


def test_provider_call_does_not_block_event_loop():
    class SlowProvider(FakeProvider):
        def complete(self, model, messages, timeout):
            import time
            time.sleep(0.05)
            return "ready"

    chain = LLMFallbackChain(
        [SlowProvider()], FakeLangfuse(), "unavailable",
        total_timeout_seconds=3, attempt_timeout_seconds=2,
    )

    async def scenario():
        ticked = False

        async def heartbeat():
            nonlocal ticked
            await asyncio.sleep(0.005)
            ticked = True

        result, _ = await asyncio.gather(
            chain.chat([{"role": "user", "content": "hi"}]),
            heartbeat(),
        )
        return result, ticked

    result, ticked = asyncio.run(scenario())
    assert result == "ready"
    assert ticked is True
