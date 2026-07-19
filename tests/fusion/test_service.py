from __future__ import annotations

import unittest

from apps.backend.app.fusion.service import EmotionFusionService
from packages.schemas import (
    CompanionStrategy,
    ConflictType,
    EmotionLabel,
    EmotionStatus,
    FusionConfig,
    Modality,
    ModalityEmotion,
)


def observation(
    modality: Modality,
    label: EmotionLabel,
    *,
    confidence: float = 0.8,
    quality: float = 0.9,
) -> ModalityEmotion:
    return ModalityEmotion(
        modality=modality,
        label=label,
        confidence=confidence,
        quality=quality,
        reliability=round(confidence * quality, 10),
        status=EmotionStatus.OK,
    )


class EmotionFusionServiceTests(unittest.TestCase):
    def test_consistent_positive_uses_reliability_weighted_sum(self) -> None:
        result = EmotionFusionService().fuse(
            (
                observation(Modality.TEXT, EmotionLabel.POSITIVE),
                observation(Modality.VIDEO, EmotionLabel.POSITIVE),
            )
        )

        self.assertEqual(result.fused_label, EmotionLabel.POSITIVE)
        self.assertEqual(result.weighted_score, 1.0)
        self.assertEqual(result.conflict_type, ConflictType.CONSISTENT_POSITIVE)
        self.assertEqual(result.strategy, CompanionStrategy.POSITIVE_ENGAGEMENT)

    def test_verbal_positive_behavior_negative_is_deterministic_conflict(self) -> None:
        result = EmotionFusionService().fuse(
            (
                observation(
                    Modality.TEXT,
                    EmotionLabel.POSITIVE,
                    confidence=0.9,
                    quality=1.0,
                ),
                observation(
                    Modality.VIDEO,
                    EmotionLabel.NEGATIVE,
                    confidence=0.8,
                    quality=1.0,
                ),
            )
        )

        self.assertTrue(result.conflict)
        self.assertEqual(
            result.conflict_type,
            ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE,
        )
        self.assertEqual(result.strategy, CompanionStrategy.GENTLE_CHECK_IN)
        self.assertAlmostEqual(result.weighted_score, 0.2558, places=4)

    def test_fewer_than_two_reliable_modalities_is_insufficient(self) -> None:
        result = EmotionFusionService().fuse(
            (
                observation(Modality.TEXT, EmotionLabel.POSITIVE),
                observation(
                    Modality.VIDEO,
                    EmotionLabel.NEGATIVE,
                    confidence=0.4,
                    quality=0.5,
                ),
            )
        )

        self.assertEqual(result.fused_label, EmotionLabel.UNCERTAIN)
        self.assertEqual(result.conflict_type, ConflictType.INSUFFICIENT_EVIDENCE)
        self.assertFalse(result.conflict)

    def test_configured_weights_can_change_final_label_without_changing_conflict(
        self,
    ) -> None:
        service = EmotionFusionService(
            FusionConfig(text_weight=0.2, audio_weight=0.2, video_weight=0.6)
        )
        result = service.fuse(
            (
                observation(Modality.TEXT, EmotionLabel.POSITIVE),
                observation(Modality.VIDEO, EmotionLabel.NEGATIVE),
            )
        )

        self.assertEqual(result.fused_label, EmotionLabel.NEGATIVE)
        self.assertEqual(
            result.conflict_type,
            ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE,
        )


if __name__ == "__main__":
    unittest.main()
