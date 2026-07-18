from __future__ import annotations

import unittest

from apps.backend.app.fusion.service import EmotionFusionService
from apps.backend.app.integration.emotion_middleware import EmotionMiddleware
from packages.schemas import (
    ConflictType,
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    TurnRecord,
)


class FakeTextService:
    async def analyze(self, *, turn_id: str, transcript: str | None) -> ModalityEmotion:
        assert turn_id == "turn_1"
        assert transcript == "我很好"
        return ModalityEmotion.text_result(
            label=EmotionLabel.POSITIVE,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
        )


class FakeVideoMiddleware:
    async def analyze_turn(self, turn: TurnRecord) -> ModalityEmotion:
        assert turn.turn_id == "turn_1"
        return ModalityEmotion.video_result(
            label=EmotionLabel.NEGATIVE,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
        )


class EmotionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_results_are_fused_after_both_complete(self) -> None:
        middleware = EmotionMiddleware(  # type: ignore[arg-type]
            FakeTextService(),
            FakeVideoMiddleware(),
            EmotionFusionService(),
        )
        result = await middleware.analyze_turn(
            TurnRecord(
                session_id="session_1",
                turn_id="turn_1",
                speech_start_ms=1,
                speech_end_ms=2,
                transcript="我很好",
            )
        )

        self.assertEqual(len(result.observations), 2)
        self.assertEqual(
            result.fusion.conflict_type,
            ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE,
        )


if __name__ == "__main__":
    unittest.main()
