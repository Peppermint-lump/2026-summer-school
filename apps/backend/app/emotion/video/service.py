"""Fail-open application service for independent visual emotion observation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

from apps.backend.app.emotion.providers.base import (
    ProviderError,
    ProviderInvalidOutputError,
    ProviderRateLimitError,
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

from .action_emotion import ActionEmotionConfig, apply_action_emotion


@dataclass(frozen=True, slots=True)
class VideoEmotionServiceConfig:
    enabled: bool = False
    provider_timeout_seconds: float = 20.0
    prompt_version: str = "video_emotion_v1"
    action_emotion: ActionEmotionConfig = ActionEmotionConfig()

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
                observation = await self._provider.analyze_video(request)
                observation = replace(
                    observation,
                    raw_metadata={
                        **observation.raw_metadata,
                        "captured_frame_count": artifact.captured_frame_count,
                        "sampled_frame_count": artifact.sampled_frame_count,
                        "quality_reasons": artifact.quality_reasons,
                    },
                )
                return apply_action_emotion(observation, self.config.action_emotion)
        except TimeoutError:
            return _fallback_result(
                EmotionStatus.TIMEOUT,
                quality=artifact.quality,
                evidence=("provider_timeout",),
            )
        except ProviderRateLimitError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=artifact.quality,
                evidence=("provider_rate_limited",),
            )
        except ProviderInvalidOutputError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=artifact.quality,
                evidence=("provider_invalid_output",),
            )
        except ProviderError:
            return _fallback_result(
                EmotionStatus.PROVIDER_ERROR,
                quality=artifact.quality,
                evidence=("provider_request_failed",),
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
