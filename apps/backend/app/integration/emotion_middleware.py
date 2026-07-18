"""Parallel independent modality analysis followed by deterministic fusion."""

from __future__ import annotations

import asyncio

from apps.backend.app.emotion.text.service import TextEmotionService
from apps.backend.app.fusion.service import EmotionFusionService
from packages.schemas import EmotionTurnAnalysis, TurnRecord

from .video_emotion_middleware import VideoEmotionMiddleware


class EmotionMiddleware:
    def __init__(
        self,
        text_service: TextEmotionService,
        video_middleware: VideoEmotionMiddleware,
        fusion_service: EmotionFusionService,
    ) -> None:
        self._text_service = text_service
        self._video_middleware = video_middleware
        self._fusion_service = fusion_service

    async def analyze_turn(self, turn: TurnRecord) -> EmotionTurnAnalysis:
        text_result, video_result = await asyncio.gather(
            self._text_service.analyze(
                turn_id=turn.turn_id,
                transcript=turn.transcript,
            ),
            self._video_middleware.analyze_turn(turn),
        )
        observations = (text_result, video_result)
        return EmotionTurnAnalysis(
            observations=observations,
            fusion=self._fusion_service.fuse(observations),
        )
