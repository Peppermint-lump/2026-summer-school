"""Fail-open application service for independent text emotion observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from apps.backend.app.emotion.providers.base import (
    ProviderError,
    ProviderInvalidOutputError,
    ProviderRateLimitError,
    TextEmotionProvider,
    TextEmotionRequest,
)
from packages.schemas import EmotionLabel, EmotionStatus, ModalityEmotion

from .quality import estimate_text_quality


@dataclass(frozen=True, slots=True)
class TextEmotionServiceConfig:
    enabled: bool = False
    provider_timeout_seconds: float = 12.0
    prompt_version: str = "text_emotion_v1"

    def __post_init__(self) -> None:
        if self.provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be positive")


class TextEmotionService:
    def __init__(
        self,
        provider: TextEmotionProvider,
        config: TextEmotionServiceConfig | None = None,
    ) -> None:
        self._provider = provider
        self.config = config or TextEmotionServiceConfig()

    async def analyze(self, *, turn_id: str, transcript: str | None) -> ModalityEmotion:
        if not self.config.enabled:
            return _fallback_result(EmotionStatus.DISABLED, quality=0.0)
        if transcript is None or not transcript.strip():
            return _fallback_result(EmotionStatus.INSUFFICIENT_EVIDENCE, quality=0.0)
        quality = estimate_text_quality(transcript)
        request = TextEmotionRequest(
            turn_id=turn_id,
            transcript=transcript,
            quality=quality,
            prompt_version=self.config.prompt_version,
        )
        try:
            async with asyncio.timeout(self.config.provider_timeout_seconds):
                return await self._provider.analyze_text(request)
        except TimeoutError:
            return _fallback_result(
                EmotionStatus.TIMEOUT,
                quality=quality,
                evidence=("provider_timeout",),
            )
        except ProviderRateLimitError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=quality,
                evidence=("provider_rate_limited",),
            )
        except ProviderInvalidOutputError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=quality,
                evidence=("provider_invalid_output",),
            )
        except ProviderError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=quality,
                evidence=("provider_request_failed",),
            )


def _fallback_result(
    status: EmotionStatus,
    *,
    quality: float,
    evidence: tuple[str, ...] = (),
) -> ModalityEmotion:
    return ModalityEmotion.text_result(
        label=EmotionLabel.UNCERTAIN,
        confidence=0.0,
        quality=quality,
        status=status,
        evidence=evidence,
    )
