"""Parallel independent modality analysis followed by deterministic fusion."""

from __future__ import annotations

import asyncio
import logging

from apps.backend.app.avatar.state_mapper import AvatarStateMapper
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.emotion.audio.service import AudioEmotionService
from apps.backend.app.emotion.text.service import TextEmotionService
from apps.backend.app.fusion.service import EmotionFusionService
from packages.schemas import EmotionTurnAnalysis, EmotionTurnResult, TurnRecord

from .video_emotion_middleware import VideoEmotionMiddleware

logger = logging.getLogger(__name__)


class EmotionMiddleware:
    def __init__(
        self,
        text_service: TextEmotionService,
        audio_service: AudioEmotionService,
        video_middleware: VideoEmotionMiddleware,
        fusion_service: EmotionFusionService,
        avatar_mapper: AvatarStateMapper,
        media_cleaner: TurnMediaCleaner | None = None,
    ) -> None:
        self._text_service = text_service
        self._audio_service = audio_service
        self._video_middleware = video_middleware
        self._fusion_service = fusion_service
        self._avatar_mapper = avatar_mapper
        self._media_cleaner = media_cleaner

    async def analyze_turn(self, turn: TurnRecord) -> EmotionTurnResult:
        try:
            text_result, audio_result, video_result = await asyncio.gather(
                self._text_service.analyze(
                    turn_id=turn.turn_id,
                    transcript=turn.transcript,
                ),
                self._audio_service.analyze(
                    turn_id=turn.turn_id,
                    audio_path=turn.audio_path,
                ),
                self._video_middleware.analyze_turn(turn),
            )
            observations = (text_result, audio_result, video_result)
            analysis = EmotionTurnAnalysis(
                observations=observations,
                fusion=self._fusion_service.fuse(observations),
            )
            return EmotionTurnResult(
                analysis=analysis,
                avatar_state=self._avatar_mapper.map(analysis),
            )
        finally:
            if self._media_cleaner is not None:
                try:
                    self._media_cleaner.cleanup_turn(turn.turn_id)
                except OSError:
                    logger.warning(
                        "Temporary turn media cleanup failed",
                        extra={
                            "session_id": turn.session_id,
                            "turn_id": turn.turn_id,
                            "request_id": None,
                            "provider": "local",
                            "stage": "media_cleanup",
                            "latency_ms": 0,
                            "status": "error",
                        },
                    )
