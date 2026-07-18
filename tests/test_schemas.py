from __future__ import annotations

import unittest

from packages.schemas import (
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
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


if __name__ == "__main__":
    unittest.main()
