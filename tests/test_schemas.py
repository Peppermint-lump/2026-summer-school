from __future__ import annotations

import unittest

from packages.schemas import (
    ActionType,
    EmotionLabel,
    EmotionStatus,
    Modality,
    ModalityEmotion,
    ObservedAction,
    TurnRecord,
)


class SchemaTests(unittest.TestCase):
    def test_turn_record_rejects_inverted_time_range(self) -> None:
        with self.assertRaises(ValueError):
            TurnRecord(
                session_id="session_1",
                turn_id="turn_1",
                speech_start_ms=200,
                speech_end_ms=100,
            )

    def test_video_result_computes_deterministic_reliability(self) -> None:
        result = ModalityEmotion.video_result(
            label=EmotionLabel.NEGATIVE,
            confidence=0.75,
            quality=0.8,
            status=EmotionStatus.OK,
        )
        self.assertEqual(result.reliability, 0.6)

    def test_modality_emotion_rejects_sensitive_metadata(self) -> None:
        with self.assertRaises(ValueError):
            ModalityEmotion.video_result(
                label=EmotionLabel.NEUTRAL,
                confidence=0.5,
                quality=0.5,
                status=EmotionStatus.OK,
                raw_metadata={"base64": "sensitive"},
            )

    def test_actions_cannot_leak_into_text_modality(self) -> None:
        with self.assertRaises(ValueError):
            ModalityEmotion(
                modality=Modality.TEXT,
                label=EmotionLabel.POSITIVE,
                confidence=0.8,
                quality=0.8,
                reliability=0.64,
                status=EmotionStatus.OK,
                observed_actions=(ObservedAction(ActionType.WAVE, 0.8),),
            )


if __name__ == "__main__":
    unittest.main()
