"""Fail-open application service for independent visual emotion observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from apps.backend.app.emotion.providers.base import (
    ProviderError,
    VideoEmotionProvider,
    VideoEmotionRequest,
)
from packages.schemas import (
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    VideoArtifactStatus,
    VideoTurnArtifact,
)


@dataclass(frozen=True, slots=True)
class VideoEmotionServiceConfig:
    enabled: bool = False
    provider_timeout_seconds: float = 20.0
    prompt_version: str = "video_emotion_v1"

    def __post_init__(self) -> None:
        if self.provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be positive")


class VideoEmotionService:
    def __init__(
        self,
        provider: VideoEmotionProvider,
        config: VideoEmotionServiceConfig | None = None,
    ) -> None:
        self._provider = provider
        self.config = config or VideoEmotionServiceConfig()

    async def analyze(self, artifact: VideoTurnArtifact) -> ModalityEmotion:
        if not self.config.enabled or artifact.status is VideoArtifactStatus.DISABLED:
            return _fallback_result(EmotionStatus.DISABLED, quality=0.0)
        if (
            artifact.status is not VideoArtifactStatus.OK
            or not artifact.frame_paths
            or artifact.quality <= 0.0
        ):
            return _fallback_result(
                EmotionStatus.INSUFFICIENT_EVIDENCE,
                quality=artifact.quality,
                evidence=artifact.quality_reasons,
            )

        request = VideoEmotionRequest(
            turn_id=artifact.turn_id,
            frame_paths=artifact.frame_paths,
            quality=artifact.quality,
            prompt_version=self.config.prompt_version,
        )
        try:
            async with asyncio.timeout(self.config.provider_timeout_seconds):
                return await self._provider.analyze_video(request)
        except TimeoutError:
            return _fallback_result(EmotionStatus.TIMEOUT, quality=artifact.quality)
        except ProviderError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=artifact.quality,
            )


def _fallback_result(
    status: EmotionStatus,
    *,
    quality: float,
    evidence: tuple[str, ...] = (),
) -> ModalityEmotion:
    return ModalityEmotion.video_result(
        label=EmotionLabel.UNCERTAIN,
        confidence=0.0,
        quality=quality,
        status=status,
        evidence=evidence,
    )
