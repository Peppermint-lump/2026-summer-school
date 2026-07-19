from __future__ import annotations

import unittest

from apps.backend.app.emotion.video.action_emotion import apply_action_emotion
from packages.schemas import (
    ActionType,
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    ObservedAction,
)


class ActionEmotionTests(unittest.TestCase):
    def test_action_stays_inside_video_modality_and_is_bounded(self) -> None:
        visual = ModalityEmotion.video_result(
            label=EmotionLabel.UNCERTAIN,
            confidence=0.0,
            quality=0.9,
            status=EmotionStatus.UNCERTAIN,
            observed_actions=(
                ObservedAction(ActionType.WAVE, 0.95, "repeated side-to-side hand"),
            ),
        )

        result = apply_action_emotion(visual)

        self.assertEqual(result.label, EmotionLabel.POSITIVE)
        self.assertLess(result.reliability, 0.55)
        self.assertEqual(result.observed_actions[0].action, ActionType.WAVE)
        self.assertEqual(result.raw_metadata["action_emotion_weight"], 0.25)

    def test_low_confidence_action_does_not_change_visual_emotion(self) -> None:
        visual = ModalityEmotion.video_result(
            label=EmotionLabel.NEGATIVE,
            confidence=0.8,
            quality=0.9,
            status=EmotionStatus.OK,
            observed_actions=(ObservedAction(ActionType.THUMBS_UP, 0.4),),
        )

        self.assertIs(apply_action_emotion(visual), visual)

    def test_head_shake_is_not_forced_to_negative_emotion(self) -> None:
        visual = ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.8,
            quality=0.9,
            status=EmotionStatus.OK,
            observed_actions=(ObservedAction(ActionType.HEAD_SHAKE, 0.9),),
        )

        self.assertEqual(apply_action_emotion(visual).label, EmotionLabel.NEUTRAL)


if __name__ == "__main__":
    unittest.main()
