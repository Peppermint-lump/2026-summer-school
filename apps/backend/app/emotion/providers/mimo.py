"""Independent MiMo audio-only and video-only provider adapters."""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.backend.app.infrastructure.http_client import (
    AsyncJsonClient,
    HttpClientInvalidResponseError,
    HttpResponse,
)
from packages.schemas import (
    ActionType,
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    ObservedAction,
)

from .base import (
    AudioEmotionRequest,
    ProviderError,
    ProviderInvalidOutputError,
    ProviderRateLimitError,
    VideoEmotionRequest,
)


@dataclass(frozen=True, slots=True)
class MiMoAudioConfig:
    base_url: str
    api_key: str
    model: str = "mimo-v2.5"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    retry_base_seconds: float = 0.25
    max_media_bytes: int = 24 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("MiMo base_url must use HTTPS")
        if not self.api_key:
            raise ValueError("MiMo API key must be supplied by secure configuration")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid MiMo timeout or retry configuration")
        if self.max_media_bytes <= 0:
            raise ValueError("MiMo audio media limit must be positive")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class MiMoAudioEmotionProvider:
    """Translate raw audio evidence into the canonical audio schema."""

    def __init__(
        self,
        config: MiMoAudioConfig,
        http_client: AsyncJsonClient,
        *,
        prompt: str,
    ) -> None:
        if not prompt.strip():
            raise ValueError("audio prompt must be loaded from configuration")
        self._config = config
        self._http_client = http_client
        self._prompt = prompt

    async def analyze_audio(self, request: AudioEmotionRequest) -> ModalityEmotion:
        payload = self._build_payload(request.audio_path)
        response = await _post_mimo_payload(
            url=self._config.chat_completions_url,
            api_key=self._config.api_key,
            payload=payload,
            http_client=self._http_client,
            timeout_seconds=self._config.timeout_seconds,
            max_retries=self._config.max_retries,
            retry_base_seconds=self._config.retry_base_seconds,
        )
        parsed = _extract_emotion_json(response.data)
        return _canonical_audio_result(
            parsed,
            quality=request.quality,
            model=self._config.model,
            prompt_version=request.prompt_version,
            request_id=response.request_id,
        )

    def _build_payload(self, audio_path: Path) -> dict[str, Any]:
        try:
            media = audio_path.read_bytes()
        except OSError as exc:
            raise ProviderError("audio file could not be read") from exc
        if not media:
            raise ProviderError("audio file is empty")
        if len(media) > self._config.max_media_bytes:
            raise ProviderError("audio request exceeds the media-size limit")
        mime_type = _detect_audio_mime(media, audio_path)
        encoded = base64.b64encode(media).decode("ascii")
        return {
            "model": self._config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:{mime_type};base64,{encoded}"
                            },
                        },
                        {"type": "text", "text": self._prompt},
                    ],
                }
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 512,
        }


@dataclass(frozen=True, slots=True)
class MiMoVideoConfig:
    base_url: str
    api_key: str
    model: str = "mimo-v2.5"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    retry_base_seconds: float = 0.25
    max_frames: int = 12
    max_total_media_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("MiMo base_url must use HTTPS")
        if not self.api_key:
            raise ValueError("MiMo API key must be supplied by secure configuration")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid MiMo timeout or retry configuration")
        if self.max_frames <= 0 or self.max_total_media_bytes <= 0:
            raise ValueError("MiMo media limits must be positive")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


async def _post_mimo_payload(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    http_client: AsyncJsonClient,
    timeout_seconds: float,
    max_retries: int,
    retry_base_seconds: float,
) -> HttpResponse:
    response: HttpResponse | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await http_client.post_json(
                url=url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
        except (OSError, TimeoutError) as exc:
            if attempt >= max_retries:
                raise ProviderError(
                    "MiMo request failed after bounded retries"
                ) from exc
            await asyncio.sleep(retry_base_seconds * (2**attempt))
            continue
        except HttpClientInvalidResponseError as exc:
            raise ProviderInvalidOutputError(
                "MiMo returned an invalid HTTP response"
            ) from exc

        if response.status_code == 429:
            if attempt >= max_retries:
                raise ProviderRateLimitError("MiMo rate limit exceeded")
            await asyncio.sleep(retry_base_seconds * (2**attempt))
            continue
        if response.status_code >= 500:
            if attempt >= max_retries:
                raise ProviderError("MiMo server failed after bounded retries")
            await asyncio.sleep(retry_base_seconds * (2**attempt))
            continue
        if response.status_code >= 400:
            raise ProviderError(
                f"MiMo rejected request with status {response.status_code}"
            )
        return response

    raise ProviderError("MiMo request produced no response")


class MiMoVideoEmotionProvider:
    """Translate sampled visual evidence into the canonical video schema."""

    def __init__(
        self,
        config: MiMoVideoConfig,
        http_client: AsyncJsonClient,
        *,
        prompt: str,
    ) -> None:
        if not prompt.strip():
            raise ValueError("video prompt must be loaded from configuration")
        self._config = config
        self._http_client = http_client
        self._prompt = prompt

    async def analyze_video(self, request: VideoEmotionRequest) -> ModalityEmotion:
        payload = self._build_payload(request.frame_paths)
        response: HttpResponse | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._http_client.post_json(
                    url=self._config.chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "Content-Type": "application/json",
                    },
                    payload=payload,
                    timeout_seconds=self._config.timeout_seconds,
                )
            except (OSError, TimeoutError) as exc:
                if attempt >= self._config.max_retries:
                    raise ProviderError(
                        "MiMo request failed after bounded retries"
                    ) from exc
                await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))
                continue
            except HttpClientInvalidResponseError as exc:
                raise ProviderInvalidOutputError(
                    "MiMo returned an invalid HTTP response"
                ) from exc

            if response.status_code == 429:
                if attempt >= self._config.max_retries:
                    raise ProviderRateLimitError("MiMo rate limit exceeded")
                await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))
                continue
            if response.status_code >= 500:
                if attempt >= self._config.max_retries:
                    raise ProviderError("MiMo server failed after bounded retries")
                await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))
                continue
            if response.status_code >= 400:
                raise ProviderError(
                    f"MiMo rejected request with status {response.status_code}"
                )
            break

        if response is None:
            raise ProviderError("MiMo request produced no response")
        parsed = _extract_emotion_json(response.data)
        return _canonical_video_result(
            parsed,
            quality=request.quality,
            model=self._config.model,
            prompt_version=request.prompt_version,
            request_id=response.request_id,
        )

    def _build_payload(self, frame_paths: tuple[Path, ...]) -> dict[str, Any]:
        if len(frame_paths) > self._config.max_frames:
            raise ProviderError("video request exceeds the configured frame limit")
        content: list[dict[str, Any]] = [{"type": "text", "text": self._prompt}]
        total_bytes = 0
        for path in frame_paths:
            try:
                media = path.read_bytes()
            except OSError as exc:
                raise ProviderError("video frame could not be read") from exc
            total_bytes += len(media)
            if total_bytes > self._config.max_total_media_bytes:
                raise ProviderError("video request exceeds the media-size limit")
            mime_type = _detect_image_mime(media)
            encoded = base64.b64encode(media).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )
        return {
            "model": self._config.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }


def _detect_image_mime(media: bytes) -> str:
    if media.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if media.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    raise ProviderError("video frame is not a supported JPEG or PNG image")


def _detect_audio_mime(media: bytes, path: Path) -> str:
    suffix = path.suffix.lower()
    if media.startswith(b"RIFF") and media[8:12] == b"WAVE":
        return "audio/wav"
    if media.startswith(b"fLaC"):
        return "audio/flac"
    if media.startswith(b"OggS"):
        return "audio/ogg"
    if media.startswith(b"ID3") or (
        len(media) >= 2 and media[0] == 0xFF and media[1] & 0xE0 == 0xE0
    ):
        return "audio/mpeg"
    if len(media) >= 12 and media[4:8] == b"ftyp" and suffix == ".m4a":
        return "audio/mp4"
    raise ProviderError("audio must be WAV, MP3, FLAC, M4A, or OGG")


def _extract_emotion_json(response: dict[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderInvalidOutputError(
            "MiMo response is missing message content"
        ) from exc
    if not isinstance(message, dict):
        raise ProviderInvalidOutputError("MiMo response message must be an object")
    content = message.get("content") or message.get("reasoning_content")
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    if not isinstance(content, str):
        raise ProviderInvalidOutputError("MiMo content must be text JSON")
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProviderInvalidOutputError("MiMo content is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderInvalidOutputError("MiMo emotion output must be an object")
    return parsed


def _canonical_audio_result(
    parsed: dict[str, Any],
    *,
    quality: float,
    model: str,
    prompt_version: str,
    request_id: str | None,
) -> ModalityEmotion:
    label = _normalize_label(parsed.get("label"))
    confidence = _validated_confidence(parsed.get("confidence"))
    fine_emotion = _validated_fine_emotion(parsed.get("fine_emotion"))
    evidence = _validated_evidence(parsed.get("evidence", []))
    metadata: dict[str, Any] = {
        "provider": "mimo",
        "model": model,
        "prompt_version": prompt_version,
    }
    if request_id:
        metadata["request_id"] = request_id
    status = (
        EmotionStatus.UNCERTAIN if label is EmotionLabel.UNCERTAIN else EmotionStatus.OK
    )
    return ModalityEmotion.audio_result(
        label=label,
        confidence=confidence,
        quality=quality,
        status=status,
        fine_emotion=fine_emotion,
        evidence=evidence,
        raw_metadata=metadata,
    )


def _validated_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderInvalidOutputError("MiMo confidence must be numeric")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise ProviderInvalidOutputError("MiMo confidence is outside [0, 1]")
    return confidence


def _validated_fine_emotion(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ProviderInvalidOutputError("MiMo fine_emotion must be text or null")
    return value


def _validated_evidence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProviderInvalidOutputError("MiMo evidence must be a list of strings")
    return tuple(item[:200] for item in value[:6])


def _canonical_video_result(
    parsed: dict[str, Any],
    *,
    quality: float,
    model: str,
    prompt_version: str,
    request_id: str | None,
) -> ModalityEmotion:
    label = _normalize_label(parsed.get("label"))
    confidence = parsed.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ProviderInvalidOutputError("MiMo confidence must be numeric")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ProviderInvalidOutputError("MiMo confidence is outside [0, 1]")
    fine_emotion = parsed.get("fine_emotion")
    if fine_emotion is not None and not isinstance(fine_emotion, str):
        raise ProviderInvalidOutputError("MiMo fine_emotion must be text or null")
    evidence_value = parsed.get("evidence", [])
    if not isinstance(evidence_value, list) or not all(
        isinstance(item, str) for item in evidence_value
    ):
        raise ProviderInvalidOutputError("MiMo evidence must be a list of strings")
    evidence = tuple(item[:200] for item in evidence_value[:6])
    observed_actions = _normalize_actions(parsed.get("actions", []))
    metadata: dict[str, Any] = {
        "provider": "mimo",
        "model": model,
        "prompt_version": prompt_version,
    }
    if request_id:
        metadata["request_id"] = request_id
    status = (
        EmotionStatus.UNCERTAIN if label is EmotionLabel.UNCERTAIN else EmotionStatus.OK
    )
    return ModalityEmotion.video_result(
        label=label,
        confidence=confidence,
        quality=quality,
        status=status,
        fine_emotion=fine_emotion,
        evidence=evidence,
        observed_actions=observed_actions,
        raw_metadata=metadata,
    )


def _normalize_actions(value: Any) -> tuple[ObservedAction, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderInvalidOutputError("MiMo actions must be a list")
    actions: list[ObservedAction] = []
    aliases = {
        "wave": ActionType.WAVE,
        "waving": ActionType.WAVE,
        "thumbs_up": ActionType.THUMBS_UP,
        "thumbs-up": ActionType.THUMBS_UP,
        "clap": ActionType.CLAP,
        "clapping": ActionType.CLAP,
        "nod": ActionType.NOD,
        "nodding": ActionType.NOD,
        "head_shake": ActionType.HEAD_SHAKE,
        "head-shake": ActionType.HEAD_SHAKE,
        "hands_up": ActionType.HANDS_UP,
        "hands-up": ActionType.HANDS_UP,
        "point": ActionType.POINT,
        "pointing": ActionType.POINT,
        "still": ActionType.STILL,
        "other": ActionType.OTHER,
    }
    for item in value[:6]:
        if not isinstance(item, dict):
            raise ProviderInvalidOutputError("MiMo action entries must be objects")
        raw_type = item.get("type")
        confidence = item.get("confidence")
        evidence = item.get("evidence", "")
        if not isinstance(raw_type, str) or raw_type.strip().lower() not in aliases:
            raise ProviderInvalidOutputError("MiMo returned an unsupported action")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ProviderInvalidOutputError("MiMo action confidence must be numeric")
        if not 0.0 <= float(confidence) <= 1.0:
            raise ProviderInvalidOutputError("MiMo action confidence is outside [0, 1]")
        if not isinstance(evidence, str):
            raise ProviderInvalidOutputError("MiMo action evidence must be text")
        actions.append(
            ObservedAction(
                action=aliases[raw_type.strip().lower()],
                confidence=float(confidence),
                evidence=evidence[:200],
            )
        )
    return tuple(actions)


def _normalize_label(value: Any) -> EmotionLabel:
    if not isinstance(value, str):
        raise ProviderInvalidOutputError("MiMo label must be text")
    normalized = value.strip().lower()
    aliases = {
        "positive": EmotionLabel.POSITIVE,
        "积极": EmotionLabel.POSITIVE,
        "neutral": EmotionLabel.NEUTRAL,
        "中性": EmotionLabel.NEUTRAL,
        "negative": EmotionLabel.NEGATIVE,
        "消极": EmotionLabel.NEGATIVE,
        "uncertain": EmotionLabel.UNCERTAIN,
        "不确定": EmotionLabel.UNCERTAIN,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ProviderInvalidOutputError(f"unsupported MiMo label: {value}") from exc
