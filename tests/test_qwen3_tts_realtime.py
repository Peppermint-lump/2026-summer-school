from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "Open-LLM-VTuber" / "src"))

from open_llm_vtuber.tts.qwen3_tts_realtime import TTSEngine  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
