from __future__ import annotations

import asyncio
import base64
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "Open-LLM-VTuber" / "src"))

from open_llm_vtuber.tts.qwen3_tts_realtime import TTSEngine  # noqa: E402
from open_llm_vtuber.conversations.tts_manager import TTSTaskManager  # noqa: E402


class FakeFallbackEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def async_generate_audio(
        self, text: str, file_name_no_ext: str | None = None
    ) -> str:
        self.calls.append((text, file_name_no_ext))
        return "fallback.wav"


class FakeWebSocket:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = [json.dumps(response) for response in responses]
        self.sent: list[dict] = []

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        return self.responses.pop(0)


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class Qwen3RealtimeTTSTests(unittest.IsolatedAsyncioTestCase):
    async def test_realtime_events_are_assembled_into_wav_bytes(self) -> None:
        websocket = FakeWebSocket(
            [
                {
                    "type": "response.audio.delta",
                    "delta": base64.b64encode(b"RIFF").decode("ascii"),
                },
                {
                    "type": "response.audio.delta",
                    "delta": base64.b64encode(b"audio").decode("ascii"),
                },
                {"type": "response.done"},
            ]
        )
        engine = TTSEngine(api_key="test-key")

        with patch(
            "open_llm_vtuber.tts.qwen3_tts_realtime.websockets.connect",
            return_value=FakeConnection(websocket),
        ) as connect:
            audio = await engine._synthesize_qwen("你好")

        self.assertEqual(audio, b"RIFFaudio")
        self.assertIn("model=qwen3-tts-flash-realtime", connect.call_args.args[0])
        self.assertEqual(
            connect.call_args.kwargs["additional_headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(
            [event["type"] for event in websocket.sent],
            [
                "session.update",
                "input_text_buffer.append",
                "input_text_buffer.commit",
                "session.finish",
            ],
        )
        self.assertEqual(websocket.sent[0]["session"]["sample_rate"], 24000)
        self.assertEqual(websocket.sent[1]["text"], "你好")

    async def test_missing_api_key_uses_piper_fallback(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            engine = TTSEngine(api_key="")
        fallback = FakeFallbackEngine()
        engine.fallback_engine = fallback

        result = await engine.async_generate_audio("你好", "missing-key")

        self.assertEqual(result, "fallback.wav")
        self.assertEqual(fallback.calls, [("你好", "missing-key")])

    async def test_provider_failure_uses_piper_fallback(self) -> None:
        engine = TTSEngine(api_key="test-key")
        fallback = FakeFallbackEngine()
        engine.fallback_engine = fallback
        engine._generate_qwen_audio = AsyncMock(
            side_effect=RuntimeError("provider unavailable")
        )

        result = await engine.async_generate_audio("你好", "provider-error")

        self.assertEqual(result, "fallback.wav")
        self.assertEqual(fallback.calls, [("你好", "provider-error")])

    async def test_turn_uses_piper_for_all_segments_after_qwen_failure(self) -> None:
        engine = TTSEngine(api_key="test-key")
        fallback = FakeFallbackEngine()
        engine.fallback_engine = fallback
        engine._generate_qwen_audio = AsyncMock(
            side_effect=RuntimeError("provider unavailable")
        )
        turn_engine = engine.create_turn_engine()

        first = await turn_engine.async_generate_audio("first sentence", "first")
        second = await turn_engine.async_generate_audio("second sentence", "second")

        self.assertEqual((first, second), ("fallback.wav", "fallback.wav"))
        engine._generate_qwen_audio.assert_awaited_once_with(
            "first sentence", "first"
        )
        self.assertEqual(
            fallback.calls,
            [("first sentence", "first"), ("second sentence", "second")],
        )

    async def test_new_turn_retries_qwen_after_previous_turn_fell_back(self) -> None:
        engine = TTSEngine(api_key="test-key")
        fallback = FakeFallbackEngine()
        engine.fallback_engine = fallback
        engine._generate_qwen_audio = AsyncMock(
            side_effect=[RuntimeError("temporary failure"), "qwen.wav"]
        )

        first_turn = engine.create_turn_engine()
        second_turn = engine.create_turn_engine()
        first = await first_turn.async_generate_audio("first turn", "first-turn")
        second = await second_turn.async_generate_audio("second turn", "second-turn")

        self.assertEqual(first, "fallback.wav")
        self.assertEqual(second, "qwen.wav")
        self.assertEqual(engine._generate_qwen_audio.await_count, 2)

    async def test_tts_manager_reuses_one_engine_context_per_reply(self) -> None:
        manager = TTSTaskManager()
        turn_engine = object()
        engine = SimpleNamespace(
            create_turn_engine=unittest.mock.Mock(return_value=turn_engine)
        )
        manager._process_tts = AsyncMock()

        async def send(_: str) -> None:
            return None

        display_text = SimpleNamespace(name="assistant")
        await manager.speak("first", display_text, None, None, engine, send)
        await manager.speak("second", display_text, None, None, engine, send)
        await asyncio.gather(*manager.task_list)

        engine.create_turn_engine.assert_called_once_with()
        used_engines = [
            call.kwargs["tts_engine"] for call in manager._process_tts.await_args_list
        ]
        self.assertEqual(used_engines, [turn_engine, turn_engine])
        manager.clear()


if __name__ == "__main__":
    unittest.main()
