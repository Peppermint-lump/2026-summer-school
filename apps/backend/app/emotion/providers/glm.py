"""GLM text-only emotion adapter using an OpenAI-compatible endpoint."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from apps.backend.app.infrastructure.http_client import (
    AsyncJsonClient,
    HttpClientInvalidResponseError,
    HttpResponse,
)
from packages.schemas import EmotionLabel, EmotionStatus, ModalityEmotion

from .base import (
    ProviderError,
    ProviderInvalidOutputError,
    ProviderRateLimitError,
    TextEmotionRequest,
)


@dataclass(frozen=True, slots=True)
class GlmTextConfig:
    base_url: str
    api_key: str
    model: str = "glm-4.7-flash"
    timeout_seconds: float = 12.0
    max_retries: int = 2
    retry_base_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("GLM base_url must use HTTPS")
        if not self.api_key:
            raise ValueError("GLM API key must be supplied by secure configuration")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid GLM timeout or retry configuration")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class GlmTextEmotionProvider:
    def __init__(
        self,
        config: GlmTextConfig,
        http_client: AsyncJsonClient,
        *,
        prompt: str,
    ) -> None:
        if not prompt.strip():
            raise ValueError("text prompt must be loaded from configuration")
        self._config = config
        self._http_client = http_client
        self._prompt = prompt

    async def analyze_text(self, request: TextEmotionRequest) -> ModalityEmotion:
        response: HttpResponse | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._http_client.post_json(
                    url=self._config.chat_completions_url,
                    headers={
                        "Authorization": f"Bearer {self._config.api_key}",
                        "Content-Type": "application/json",
                    },
                    payload={
                        "model": self._config.model,
                        "messages": [
                            {"role": "system", "content": self._prompt},
                            {"role": "user", "content": request.transcript},
                        ],
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    },
                    timeout_seconds=self._config.timeout_seconds,
                )
            except (OSError, TimeoutError) as exc:
                if attempt >= self._config.max_retries:
                    raise ProviderError(
                        "GLM request failed after bounded retries"
                    ) from exc
                await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))
                continue
            except HttpClientInvalidResponseError as exc:
                raise ProviderInvalidOutputError(
                    "GLM returned an invalid HTTP response"
                ) from exc
            if response.status_code == 429:
                if attempt >= self._config.max_retries:
                    raise ProviderRateLimitError("GLM rate limit exceeded")
                await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))
                continue
            if response.status_code >= 500:
                if attempt >= self._config.max_retries:
                    raise ProviderError("GLM server failed after bounded retries")
                await asyncio.sleep(self._config.retry_base_seconds * (2**attempt))
                continue
            if response.status_code >= 400:
                raise ProviderError(
                    f"GLM rejected request with status {response.status_code}"
                )
            break
        if response is None:
            raise ProviderError("GLM request produced no response")
        return _canonical_text_result(
            _extract_json(response.data),
            quality=request.quality,
            model=self._config.model,
            prompt_version=request.prompt_version,
            request_id=response.request_id,
        )


def _extract_json(response: dict[str, Any]) -> dict[str, Any]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderInvalidOutputError(
            "GLM response is missing message content"
        ) from exc
    if not isinstance(content, str):
        raise ProviderInvalidOutputError("GLM content must be text JSON")
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProviderInvalidOutputError("GLM content is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderInvalidOutputError("GLM emotion output must be an object")
    return parsed


def _canonical_text_result(
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
        raise ProviderInvalidOutputError("GLM confidence must be numeric")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ProviderInvalidOutputError("GLM confidence is outside [0, 1]")
    fine_emotion = parsed.get("fine_emotion")
    if fine_emotion is not None and not isinstance(fine_emotion, str):
        raise ProviderInvalidOutputError("GLM fine_emotion must be text or null")
    evidence_value = parsed.get("evidence", [])
    if not isinstance(evidence_value, list) or not all(
        isinstance(item, str) for item in evidence_value
    ):
        raise ProviderInvalidOutputError("GLM evidence must be a list of strings")
    metadata: dict[str, Any] = {
        "provider": "glm",
        "model": model,
        "prompt_version": prompt_version,
    }
    if request_id:
        metadata["request_id"] = request_id
    status = (
        EmotionStatus.UNCERTAIN if label is EmotionLabel.UNCERTAIN else EmotionStatus.OK
    )
    return ModalityEmotion.text_result(
        label=label,
        confidence=confidence,
        quality=quality,
        status=status,
        fine_emotion=fine_emotion,
        evidence=tuple(item[:200] for item in evidence_value[:6]),
        raw_metadata=metadata,
    )


def _normalize_label(value: Any) -> EmotionLabel:
    if not isinstance(value, str):
        raise ProviderInvalidOutputError("GLM label must be text")
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
        return aliases[value.strip().lower()]
    except KeyError as exc:
        raise ProviderInvalidOutputError(f"unsupported GLM label: {value}") from exc
