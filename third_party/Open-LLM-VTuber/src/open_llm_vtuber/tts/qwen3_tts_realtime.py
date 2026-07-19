from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets
from loguru import logger

from .piper_tts import TTSEngine as PiperTTSEngine
from .tts_interface import TTSInterface


class TTSEngine(TTSInterface):
    """Qwen3 realtime TTS client with a local Piper fallback."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "qwen3-tts-flash-realtime",
        voice: str = "Cherry",
        url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        language_type: str = "Auto",
        sample_rate: int = 24000,
        timeout_seconds: int = 30,
        fallback_model_path: str | None = "models/piper/zh_CN-huayan-medium.onnx",
        fallback_timeout_seconds: int = 60,
    ) -> None:
        configured_key = api_key.strip()
        if configured_key.startswith("${") and configured_key.endswith("}"):
            configured_key = ""

        self.api_key = configured_key or os.getenv("DASHSCOPE_API_KEY", "").strip()
        self.model = model
        self.voice = voice
        self.url = self._url_with_model(url, model)
        self.language_type = language_type
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds
        self.fallback_engine = PiperTTSEngine(
            model_path=(fallback_model_path or "models/piper/zh_CN-huayan-medium.onnx"),
            timeout_seconds=fallback_timeout_seconds,
        )

    @staticmethod
    def _url_with_model(url: str, model: str) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["model"] = model
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    @staticmethod
    def _event(event_type: str, **payload: Any) -> str:
        event = {
            "event_id": f"event_{time.time_ns()}",
            "type": event_type,
            **payload,
        }
        return json.dumps(event, ensure_ascii=False)

    async def _synthesize_qwen(self, text: str) -> bytes:
        chunks: list[bytes] = []
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with websockets.connect(
            self.url,
            additional_headers=headers,
            open_timeout=self.timeout_seconds,
            close_timeout=5,
        ) as websocket:
            await websocket.send(
                self._event(
                    "session.update",
                    session={
                        "mode": "commit",
                        "voice": self.voice,
                        "language_type": self.language_type,
                        "response_format": "wav",
                        "sample_rate": self.sample_rate,
                    },
                )
            )
            await websocket.send(self._event("input_text_buffer.append", text=text))
            await websocket.send(self._event("input_text_buffer.commit"))

            response_done = False
            while not response_done:
                raw_message = await websocket.recv()
                event = json.loads(raw_message)
                event_type = event.get("type")
                if event_type == "response.audio.delta":
                    chunks.append(base64.b64decode(event.get("delta", "")))
                elif event_type == "response.done":
                    response_done = True
                elif event_type == "error":
                    error = event.get("error")
                    if isinstance(error, dict):
                        code = error.get("code", "unknown_error")
                        message = error.get("message", "Qwen TTS request failed")
                    else:
                        code = "unknown_error"
                        message = str(error or "Qwen TTS request failed")
                    raise RuntimeError(f"{code}: {message}")

            await websocket.send(self._event("session.finish"))

        audio = b"".join(chunks)
        if not audio:
            raise RuntimeError("Qwen TTS returned no audio data")
        return audio

    async def _generate_qwen_audio(
        self, text: str, file_name_no_ext: str | None
    ) -> str:
        audio = await asyncio.wait_for(
            self._synthesize_qwen(text), timeout=self.timeout_seconds
        )
        output_path = Path(self.generate_cache_file_name(file_name_no_ext, "wav"))
        output_path.write_bytes(audio)
        logger.info(
            "Qwen3 TTS generated audio with model={} voice={}",
            self.model,
            self.voice,
        )
        return str(output_path)

    async def async_generate_audio(
        self, text: str, file_name_no_ext: str | None = None
    ) -> str:
        if not self.api_key:
            logger.warning(
                "DASHSCOPE_API_KEY is not configured; using local Piper TTS fallback."
            )
            return await self.fallback_engine.async_generate_audio(
                text, file_name_no_ext
            )

        try:
            return await self._generate_qwen_audio(text, file_name_no_ext)
        except (
            asyncio.TimeoutError,
            OSError,
            RuntimeError,
            ValueError,
            websockets.WebSocketException,
        ) as exc:
            logger.warning(
                "Qwen3 realtime TTS failed ({}); using local Piper fallback.",
                exc,
            )
            return await self.fallback_engine.async_generate_audio(
                text, file_name_no_ext
            )

    def generate_audio(self, text: str, file_name_no_ext: str | None = None) -> str:
        return asyncio.run(self.async_generate_audio(text, file_name_no_ext))
