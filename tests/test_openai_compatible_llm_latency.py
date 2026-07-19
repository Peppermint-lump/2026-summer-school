from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "Open-LLM-VTuber" / "src"))

from open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import (  # noqa: E402
    AsyncLLM,
)


class FakeStream:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self._chunks = iter(chunks)
        self.closed = False

    def __aiter__(self) -> "FakeStream":
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def close(self) -> None:
        self.closed = True


class HangingStream(FakeStream):
    def __init__(self) -> None:
        super().__init__([])

    async def __anext__(self) -> SimpleNamespace:
        await asyncio.sleep(60)
        raise StopAsyncIteration


class FakeCompletions:
    def __init__(self, stream: FakeStream) -> None:
        self.stream = stream
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.stream


class FakeClient:
    def __init__(self, stream: FakeStream) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(stream))


def chunk(content: str | None = None, reasoning: str | None = None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


class OpenAICompatibleLatencyTests(unittest.IsolatedAsyncioTestCase):
    def make_llm(self, stream: FakeStream, timeout: float = 1.0) -> AsyncLLM:
        llm = AsyncLLM(
            model="test-model",
            base_url="https://example.invalid/v1",
            llm_api_key="test-key",
            first_response_timeout_seconds=timeout,
            thinking_mode="disabled",
        )
        llm.client = FakeClient(stream)
        return llm

    async def test_thinking_is_disabled_and_reasoning_is_not_displayed(self) -> None:
        stream = FakeStream([chunk(reasoning="hidden"), chunk(content="你好")])
        llm = self.make_llm(stream)

        output = [
            item
            async for item in llm.chat_completion([{"role": "user", "content": "hi"}])
        ]

        self.assertEqual(output, ["你好"])
        self.assertEqual(
            llm.client.chat.completions.kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        self.assertTrue(stream.closed)

    async def test_empty_chunks_do_not_break_the_stream(self) -> None:
        stream = FakeStream([SimpleNamespace(choices=[]), chunk(content="ready")])
        llm = self.make_llm(stream)

        output = [item async for item in llm.chat_completion([])]

        self.assertEqual(output, ["ready"])

    async def test_stream_ending_without_text_yields_fallback(self) -> None:
        llm = self.make_llm(FakeStream([]))

        output = [item async for item in llm.chat_completion([])]

        self.assertEqual(
            output,
            ["抱歉，我刚才没有及时收到回复。我们可以再试一次。"],
        )

    async def test_first_visible_response_timeout_yields_fallback(self) -> None:
        stream = HangingStream()
        llm = self.make_llm(stream, timeout=0.01)

        output = [item async for item in llm.chat_completion([])]

        self.assertEqual(
            output,
            ["抱歉，我刚才没有及时收到回复。我们可以再试一次。"],
        )
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()
