"""Authenticated loopback HTTP boundary for per-turn emotion analysis."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import threading
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from apps.backend.app.debug.trace_store import DebugTraceStore
from packages.schemas import EmotionTurnResult, Modality, TurnRecord

from .runtime_factory import EmotionRuntime

_MAX_REQUEST_BYTES = 36 * 1024 * 1024
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


class LoopbackEmotionServer:
    """Own one local server and one canonical runtime composition root."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        token: str,
        runtime: EmotionRuntime,
        runtime_root: Path,
        debug_output_root: Path,
        continuous_visual_enabled: bool = False,
        continuous_visual_window_seconds: float = 3.0,
        continuous_visual_interval_seconds: float = 2.0,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("emotion server must bind to loopback")
        if not token:
            raise ValueError("emotion server token must be non-empty")
        self._runtime = runtime
        self._runtime_root = runtime_root.resolve()
        self._trace_store = DebugTraceStore(debug_output_root.resolve())
        self._continuous_visual_enabled = (
            continuous_visual_enabled and runtime.camera_enabled
        )
        self._continuous_visual_window_seconds = continuous_visual_window_seconds
        self._continuous_visual_interval_seconds = continuous_visual_interval_seconds
        self._analysis_lock = threading.Lock()
        self._visual_lock = threading.Lock()
        self._visual_stop = threading.Event()
        self._visual_thread: threading.Thread | None = None
        self._visual_sequence = 0
        self._latest_visual: dict[str, Any] | None = None
        handler = _handler_factory(
            token=token,
            analyze=self._analyze_payload,
            health=self._health_payload,
            latest_visual=self._latest_visual_payload,
        )
        self._server = ThreadingHTTPServer((host, port), handler)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def serve_forever(self) -> None:
        self._runtime.start()
        self._start_continuous_visual()
        try:
            self._server.serve_forever(poll_interval=0.25)
        finally:
            self._stop_continuous_visual()
            self._server.server_close()
            self._runtime.stop()

    def _health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "camera_enabled": self._runtime.camera_enabled,
            "camera_state": self._runtime.camera.state.value,
            "continuous_visual_enabled": self._continuous_visual_enabled,
            "continuous_visual_sequence": self._visual_sequence,
            "raw_media_retained": False,
        }

    def _start_continuous_visual(self) -> None:
        if not self._continuous_visual_enabled:
            return
        self._visual_stop.clear()
        self._visual_thread = threading.Thread(
            target=self._continuous_visual_loop,
            name="continuous-visual-analysis",
            daemon=True,
        )
        self._visual_thread.start()

    def _stop_continuous_visual(self) -> None:
        self._visual_stop.set()
        if self._visual_thread is not None:
            self._visual_thread.join(timeout=2.0)
            self._visual_thread = None

    def _continuous_visual_loop(self) -> None:
        if self._visual_stop.wait(self._continuous_visual_window_seconds):
            return
        while not self._visual_stop.is_set():
            end_ms = time.time_ns() // 1_000_000
            window_ms = round(self._continuous_visual_window_seconds * 1000)
            turn_id = f"visual_{end_ms}"
            try:
                response = self._analyze_payload(
                    {
                        "session_id": "continuous_visual",
                        "turn_id": turn_id,
                        "speech_start_ms": end_ms,
                        "speech_end_ms": end_ms,
                        "visual_start_ms": max(0, end_ms - window_ms),
                        "visual_end_ms": end_ms,
                        "transcript": None,
                        "audio_wav_base64": None,
                    }
                )
            except (OSError, RuntimeError, ValueError) as exc:
                print(
                    "continuous visual analysis failed "
                    f"turn_id={turn_id} error={type(exc).__name__}",
                    flush=True,
                )
            else:
                with self._visual_lock:
                    self._visual_sequence += 1
                    self._latest_visual = response
                video: dict[str, Any] = next(
                    (
                        observation
                        for observation in response["analysis"]["observations"]
                        if observation["modality"] == "video"
                    ),
                    {},
                )
                actions = [
                    item.get("action") for item in video.get("observed_actions", [])
                ]
                print(
                    "continuous visual analysis complete "
                    f"turn_id={turn_id} label={video.get('label', 'unknown')} "
                    f"actions={actions} reliability={video.get('reliability', 0)}",
                    flush=True,
                )
            if self._visual_stop.wait(self._continuous_visual_interval_seconds):
                return

    def _latest_visual_payload(self) -> dict[str, Any]:
        with self._visual_lock:
            return {
                "available": self._latest_visual is not None,
                "sequence": self._visual_sequence,
                "result": self._latest_visual,
            }

    def _analyze_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = _required_identifier(payload, "session_id")
        turn_id = _required_identifier(payload, "turn_id")
        speech_start_ms = _required_nonnegative_int(payload, "speech_start_ms")
        speech_end_ms = _required_nonnegative_int(payload, "speech_end_ms")
        if speech_end_ms < speech_start_ms:
            raise ValueError("speech_end_ms must be greater than speech_start_ms")
        visual_start_ms = _optional_nonnegative_int(payload, "visual_start_ms")
        visual_end_ms = _optional_nonnegative_int(payload, "visual_end_ms")
        if (visual_start_ms is None) is not (visual_end_ms is None):
            raise ValueError("visual time range must provide both bounds")
        if (
            visual_start_ms is not None
            and visual_end_ms is not None
            and visual_end_ms < visual_start_ms
        ):
            raise ValueError("visual_end_ms must be greater than visual_start_ms")
        transcript_value = payload.get("transcript")
        if transcript_value is not None and not isinstance(transcript_value, str):
            raise ValueError("transcript must be a string or null")
        transcript = transcript_value.strip() if transcript_value else None
        audio_path = self._write_audio(turn_id, payload.get("audio_wav_base64"))
        turn = TurnRecord(
            session_id=session_id,
            turn_id=turn_id,
            speech_start_ms=speech_start_ms,
            speech_end_ms=speech_end_ms,
            visual_start_ms=visual_start_ms,
            visual_end_ms=visual_end_ms,
            audio_path=audio_path,
            transcript=transcript,
        )
        started = time.monotonic()
        self._trace_store.write_stage(
            turn_id,
            "00_request.json",
            {
                "schema_version": "1.0",
                "session_id": session_id,
                "turn_id": turn_id,
                "transcript_provided": transcript is not None,
                "transcript_character_count": len(transcript or ""),
                "audio_provided": audio_path is not None,
                "camera_enabled": self._runtime.camera_enabled,
                "visual_window_provided": visual_start_ms is not None,
                "visual_window_duration_ms": (
                    visual_end_ms - visual_start_ms
                    if visual_start_ms is not None and visual_end_ms is not None
                    else speech_end_ms - speech_start_ms
                ),
                "raw_media_logged": False,
            },
        )
        with self._analysis_lock:
            result = asyncio.run(self._runtime.middleware.analyze_turn(turn))
        response = _result_payload(result)
        response["turn_id"] = turn_id
        response["latency_ms"] = round((time.monotonic() - started) * 1000)
        response["companion_context"] = _companion_context(result)
        response["trace_directory"] = str(self._trace_store.turn_directory(turn_id))
        observations = {
            item.modality.value: _jsonable(item)
            for item in result.analysis.observations
        }
        for filename, modality in (
            ("01_text_observation.json", "text"),
            ("02_audio_observation.json", "audio"),
            ("03_video_observation.json", "video"),
        ):
            self._trace_store.write_stage(
                turn_id,
                filename,
                cast(dict[str, Any], observations[modality]),
            )
        self._trace_store.write_stage(
            turn_id,
            "04_fusion.json",
            cast(dict[str, Any], _jsonable(result.analysis.fusion)),
        )
        self._trace_store.write_stage(
            turn_id,
            "05_avatar_state.json",
            cast(dict[str, Any], _jsonable(result.avatar_state)),
        )
        temporary_media_remains = (self._runtime_root / "turns" / turn_id).exists()
        self._trace_store.write_stage(
            turn_id,
            "06_cleanup.json",
            {
                "schema_version": "1.0",
                "turn_id": turn_id,
                "temporary_media_removed": not temporary_media_remains,
                "raw_media_may_remain": temporary_media_remains,
            },
        )
        self._trace_store.write_stage(turn_id, "summary.json", response)
        return response

    def _write_audio(self, turn_id: str, encoded: Any) -> Path | None:
        if encoded is None:
            return None
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("audio_wav_base64 must be a non-empty string or null")
        try:
            media = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("audio_wav_base64 is invalid") from exc
        if not media.startswith(b"RIFF") or media[8:12] != b"WAVE":
            raise ValueError("audio payload must be a WAV file")
        turns_root = self._runtime_root / "turns"
        turn_directory = (turns_root / turn_id).resolve()
        turn_directory.relative_to(turns_root.resolve())
        turn_directory.mkdir(parents=True, exist_ok=True)
        audio_path = turn_directory / "audio.wav"
        audio_path.write_bytes(media)
        return audio_path


def _handler_factory(
    *,
    token: str,
    analyze: Any,
    health: Any,
    latest_visual: Any,
) -> type[BaseHTTPRequestHandler]:
    class EmotionRequestHandler(BaseHTTPRequestHandler):
        server_version = "EmotionLoopback/1.0"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._authorized():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            if self.path == "/health":
                self._send_json(HTTPStatus.OK, cast(dict[str, Any], health()))
                return
            if self.path == "/v1/visual/latest":
                self._send_json(
                    HTTPStatus.OK,
                    cast(dict[str, Any], latest_visual()),
                )
                return
            if self.path != "/health":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._authorized():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            if self.path != "/v1/turns/analyze":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if not 0 < content_length <= _MAX_REQUEST_BYTES:
                    raise ValueError("request body size is invalid")
                decoded = json.loads(self.rfile.read(content_length))
                if not isinstance(decoded, dict):
                    raise ValueError("request body must be a JSON object")
                result = analyze(cast(dict[str, Any], decoded))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
                OSError,
            ) as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_request", "message": str(exc)},
                )
                return
            self._send_json(HTTPStatus.OK, cast(dict[str, Any], result))

        def log_message(self, format: str, *args: object) -> None:
            return

        def _authorized(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {token}"

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                return

    return EmotionRequestHandler


def _required_identifier(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{key} must be a safe non-empty identifier")
    return value


def _required_nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _optional_nonnegative_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer or null")
    return cast(int, value)


def _result_payload(result: EmotionTurnResult) -> dict[str, Any]:
    return cast(dict[str, Any], _jsonable(result))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _companion_context(result: EmotionTurnResult) -> str:
    observations: list[str] = []
    visible_details: list[str] = []
    for observation in result.analysis.observations:
        fine_emotion = (
            f",fine={_context_fragment(observation.fine_emotion)}"
            if observation.fine_emotion
            else ""
        )
        observations.append(
            f"{observation.modality.value}={observation.label.value}"
            f"(reliability={observation.reliability:.2f},"
            f"status={observation.status.value}{fine_emotion})"
        )
        if observation.modality is Modality.VIDEO:
            visible_details.extend(
                f"{action.action.value}(confidence={action.confidence:.2f},"
                f"evidence={_context_fragment(action.evidence) or 'none'})"
                for action in observation.observed_actions
            )
    visible = "; ".join(visible_details) if visible_details else "none"
    fusion = result.analysis.fusion
    return (
        "[System context: Independent emotion observers produced uncertain signals, "
        "not facts about the user's internal state. "
        f"Observations: {'; '.join(observations)}. "
        f"Visible actions: {visible}. "
        f"Deterministic fusion: label={fusion.fused_label.value}, "
        f"weighted_score={fusion.weighted_score:.2f}, "
        f"conflict={fusion.conflict_type.value}. "
        f"Authoritative strategy: {fusion.strategy.value}. "
        "Use nonjudgmental language, do not diagnose or claim certainty.]"
    )


def _context_fragment(value: str | None) -> str:
    if not value:
        return ""
    normalized = " ".join(value.split())
    return normalized.replace("[", "(").replace("]", ")")[:160]
