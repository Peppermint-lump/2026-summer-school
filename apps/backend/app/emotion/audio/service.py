"""Fail-open application service for independent raw-audio emotion."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from apps.backend.app.emotion.providers.base import (
    AudioEmotionProvider,
    AudioEmotionRequest,
    ProviderError,
    ProviderInvalidOutputError,
    ProviderRateLimitError,
)
from packages.schemas import EmotionLabel, EmotionStatus, ModalityEmotion

from .quality import AudioQualityEvaluator


@dataclass(frozen=True, slots=True)
class AudioEmotionServiceConfig:
    enabled: bool = False
    provider_timeout_seconds: float = 20.0
    prompt_version: str = "audio_emotion_v1"
    minimum_quality: float = 0.35

    def __post_init__(self) -> None:
        if self.provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be positive")
        if not 0.0 <= self.minimum_quality <= 1.0:
            raise ValueError("minimum_quality must be between 0 and 1")


class AudioEmotionService:
    def __init__(
        self,
        provider: AudioEmotionProvider,
        quality_evaluator: AudioQualityEvaluator,
        config: AudioEmotionServiceConfig | None = None,
    ) -> None:
        self._provider = provider
        self._quality_evaluator = quality_evaluator
        self.config = config or AudioEmotionServiceConfig()

    async def analyze(
        self, *, turn_id: str, audio_path: Path | None
    ) -> ModalityEmotion:
        if not self.config.enabled:
            return _fallback_result(EmotionStatus.DISABLED, quality=0.0)
        if audio_path is None:
            return _fallback_result(
                EmotionStatus.INSUFFICIENT_EVIDENCE,
                quality=0.0,
                evidence=("audio_missing",),
            )
        quality_report = self._quality_evaluator.evaluate(audio_path)
        if quality_report.quality < self.config.minimum_quality:
            return _fallback_result(
                EmotionStatus.INSUFFICIENT_EVIDENCE,
                quality=quality_report.quality,
                evidence=quality_report.reasons or ("low_audio_quality",),
            )
        request = AudioEmotionRequest(
            turn_id=turn_id,
            audio_path=audio_path,
            quality=quality_report.quality,
            prompt_version=self.config.prompt_version,
        )
        try:
            async with asyncio.timeout(self.config.provider_timeout_seconds):
                return await self._provider.analyze_audio(request)
        except TimeoutError:
            return _fallback_result(
                EmotionStatus.TIMEOUT,
                quality=quality_report.quality,
                evidence=("provider_timeout",),
            )
        except ProviderRateLimitError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=quality_report.quality,
                evidence=("provider_rate_limited",),
            )
        except ProviderInvalidOutputError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=quality_report.quality,
                evidence=("provider_invalid_output",),
            )
        except ProviderError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=quality_report.quality,
                evidence=("provider_request_failed",),
            )


def _fallback_result(
    status: EmotionStatus,
    *,
    quality: float,
    evidence: tuple[str, ...] = (),
) -> ModalityEmotion:
    return ModalityEmotion.audio_result(
        label=EmotionLabel.UNCERTAIN,
        confidence=0.0,
        quality=quality,
        status=status,
        evidence=evidence,
    )
