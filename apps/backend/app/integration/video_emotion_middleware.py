"""Turn-scoped video middleware with mandatory fail-open media cleanup."""

from __future__ import annotations

import logging

from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.capture.video_export import FrameEncodingError
from apps.backend.app.emotion.video.preprocess import VideoTurnPreprocessor
from apps.backend.app.emotion.video.service import VideoEmotionService
from packages.schemas import (
    ModalityEmotion,
    TurnRecord,
    VideoArtifactStatus,
    VideoTurnArtifact,
)

logger = logging.getLogger(__name__)


class VideoEmotionMiddleware:
    """Provide one video result without owning the authoritative turn orchestrator."""

    def __init__(
        self,
        preprocessor: VideoTurnPreprocessor,
        emotion_service: VideoEmotionService,
        media_cleaner: TurnMediaCleaner,
        *,
        camera_enabled: bool,
        cleanup_after_analysis: bool = True,
    ) -> None:
        self._preprocessor = preprocessor
        self._emotion_service = emotion_service
        self._media_cleaner = media_cleaner
        self._camera_enabled = camera_enabled
        self._cleanup_after_analysis = cleanup_after_analysis

    async def analyze_turn(self, turn: TurnRecord) -> ModalityEmotion:
        if not self._camera_enabled:
            return await self._emotion_service.analyze(
                VideoTurnArtifact(
                    turn_id=turn.turn_id,
                    status=VideoArtifactStatus.DISABLED,
                )
            )

        try:
            try:
                start_ms = (
                    turn.visual_start_ms
                    if turn.visual_start_ms is not None
                    else turn.speech_start_ms
                )
                end_ms = (
                    turn.visual_end_ms
                    if turn.visual_end_ms is not None
                    else turn.speech_end_ms
                )
                artifact = self._preprocessor.prepare(
                    turn.turn_id,
                    start_ms,
                    end_ms,
                )
            except (FrameEncodingError, OSError):
                logger.warning(
                    "Video capture preprocessing failed",
                    extra=_log_context(turn, stage="video_preprocess", status="error"),
                )
                artifact = VideoTurnArtifact(
                    turn_id=turn.turn_id,
                    status=VideoArtifactStatus.CAPTURE_ERROR,
                    quality_reasons=("video_capture_error",),
                )
            return await self._emotion_service.analyze(artifact)
        finally:
            if self._cleanup_after_analysis:
                try:
                    self._media_cleaner.cleanup_turn(turn.turn_id)
                except OSError:
                    logger.warning(
                        "Temporary turn media cleanup failed",
                        extra=_log_context(turn, stage="media_cleanup", status="error"),
                    )


def _log_context(turn: TurnRecord, *, stage: str, status: str) -> dict[str, object]:
    return {
        "session_id": turn.session_id,
        "turn_id": turn.turn_id,
        "request_id": None,
        "provider": "local",
        "stage": stage,
        "latency_ms": 0,
        "status": status,
    }
