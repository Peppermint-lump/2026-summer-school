"""Narrow Python 3.10 adapter to the canonical loopback emotion backend."""

from __future__ import annotations

import base64
import io
import os
import time
import uuid
import wave
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
import numpy as np
from loguru import logger

_EXPRESSIONS = {"neutral", "heart", "star", "cry", "sleepy", "blush", "butterfly"}
_MOTIONS = {"idle", "greeting"}


@dataclass(frozen=True)
class EmotionMiddlewareResult:
    turn_id: str
    companion_context: str
    expression: str
    motion: str
    trace_directory: Optional[str]
    payload: Dict[str, Any]


class EmotionMiddlewareClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 35.0,
        sample_rate: int = 16000,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._sample_rate = sample_rate

    @classmethod
    def from_environment(cls) -> Optional["EmotionMiddlewareClient"]:
        base_url = os.environ.get("EMOTION_BACKEND_URL", "").strip()
        token = os.environ.get("EMOTION_BACKEND_TOKEN", "").strip()
        if not base_url or not token:
            return None
        timeout = float(os.environ.get("EMOTION_BACKEND_TIMEOUT_SECONDS", "35"))
        sample_rate = int(os.environ.get("EMOTION_AUDIO_SAMPLE_RATE", "16000"))
        return cls(
            base_url=base_url,
            token=token,
            timeout_seconds=timeout,
            sample_rate=sample_rate,
        )

    async def analyze(
        self,
        *,
        session_id: str,
        transcript: str,
        raw_audio: Optional[np.ndarray],
    ) -> Optional[EmotionMiddlewareResult]:
        turn_id = f"turn_{uuid.uuid4().hex}"
        audio_wav = _encode_audio_wav(raw_audio, self._sample_rate)
        end_ms = time.time_ns() // 1_000_000
        duration_ms = _audio_duration_ms(raw_audio, self._sample_rate)
        payload = {
            "session_id": _safe_session_id(session_id),
            "turn_id": turn_id,
            "speech_start_ms": max(0, end_ms - duration_ms),
            "speech_end_ms": end_ms,
            "transcript": transcript,
            "audio_wav_base64": (
                base64.b64encode(audio_wav).decode("ascii") if audio_wav else None
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/v1/turns/analyze",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=payload,
                )
            response.raise_for_status()
            decoded = response.json()
            return _parse_result(decoded)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning(
                "Canonical emotion middleware failed open: {}",
                type(exc).__name__,
            )
            return None

    async def latest_visual(
        self, *, after_sequence: int
    ) -> Optional[tuple[int, EmotionMiddlewareResult]]:
        """Return a new canonical video-only observation without media payloads."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    f"{self._base_url}/v1/visual/latest",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
            response.raise_for_status()
            return _parse_visual_update(response.json(), after_sequence)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning(
                "Continuous visual middleware poll failed open: {}",
                type(exc).__name__,
            )
            return None


def _encode_audio_wav(
    raw_audio: Optional[np.ndarray], sample_rate: int
) -> Optional[bytes]:
    if raw_audio is None or raw_audio.size == 0:
        return None
    samples = np.asarray(raw_audio, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(samples)))
    if peak <= 1.5:
        pcm = np.clip(samples, -1.0, 1.0) * 32767.0
    else:
        pcm = np.clip(samples, -32768.0, 32767.0)
    pcm16 = pcm.astype("<i2", copy=False)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def _audio_duration_ms(raw_audio: Optional[np.ndarray], sample_rate: int) -> int:
    if raw_audio is None or raw_audio.size == 0:
        return 0
    return round(raw_audio.size / sample_rate * 1000)


def _safe_session_id(value: str) -> str:
    normalized = "".join(char for char in value if char.isalnum() or char in "_-")
    return normalized[:96] or "vtuber_session"


def _parse_result(payload: Any) -> EmotionMiddlewareResult:
    if not isinstance(payload, dict):
        raise ValueError("emotion middleware response must be an object")
    avatar = payload.get("avatar_state")
    if not isinstance(avatar, dict):
        raise ValueError("emotion middleware response has no avatar_state")
    expression = avatar.get("expression")
    motion = avatar.get("motion")
    context = payload.get("companion_context")
    turn_id = payload.get("turn_id")
    if expression not in _EXPRESSIONS or motion not in _MOTIONS:
        raise ValueError("emotion middleware returned an unsupported avatar state")
    if not isinstance(context, str) or not isinstance(turn_id, str):
        raise ValueError("emotion middleware response is incomplete")
    trace_directory = payload.get("trace_directory")
    if trace_directory is not None and not isinstance(trace_directory, str):
        trace_directory = None
    return EmotionMiddlewareResult(
        turn_id=turn_id,
        companion_context=context[:4000],
        expression=expression,
        motion=motion,
        trace_directory=trace_directory,
        payload=payload,
    )


def _parse_visual_update(
    payload: Any, after_sequence: int
) -> Optional[tuple[int, EmotionMiddlewareResult]]:
    if not isinstance(payload, dict):
        raise ValueError("visual update response must be an object")
    sequence = payload.get("sequence")
    if not isinstance(sequence, int):
        raise ValueError("visual update sequence must be an integer")
    if not payload.get("available") or sequence <= after_sequence:
        return None
    return sequence, _parse_result(payload.get("result"))


def apply_emotion_context(
    input_text: str,
    metadata: Optional[Dict[str, Any]],
) -> str:
    """Append only the canonical observation summary to the companion input."""
    if not metadata:
        return input_text
    context = metadata.get("emotion_companion_context")
    if not isinstance(context, str) or not context:
        return input_text
    return f"{input_text}\n\n{context}"
