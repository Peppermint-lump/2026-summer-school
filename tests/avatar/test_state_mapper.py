from __future__ import annotations

import unittest

from apps.backend.app.avatar.state_mapper import AvatarStateMapper
from apps.backend.app.fusion.service import EmotionFusionService
from packages.schemas import (
    ActionType,
    AvatarExpression,
    AvatarMotion,
    ConflictType,
    EmotionLabel,
    EmotionStatus,
    EmotionTurnAnalysis,
    Modality,
    ModalityEmotion,
    ObservedAction,
)


def observation(
    modality: Modality,
    label: EmotionLabel,
    *,
    confidence: float = 0.9,
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


class AvatarStateMapperTests(unittest.TestCase):
    def test_each_modality_keeps_its_own_expression_suggestion(self) -> None:
        observations = (
            observation(Modality.TEXT, EmotionLabel.POSITIVE),
            observation(Modality.AUDIO, EmotionLabel.NEUTRAL),
            observation(Modality.VIDEO, EmotionLabel.NEGATIVE),
        )
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        state = AvatarStateMapper().map(analysis)

        by_modality = {
            suggestion.modality: suggestion for suggestion in state.modality_expressions
        }
        self.assertEqual(by_modality[Modality.TEXT].expression, AvatarExpression.HEART)
        self.assertEqual(
            by_modality[Modality.AUDIO].expression, AvatarExpression.NEUTRAL
        )
        self.assertEqual(
            by_modality[Modality.VIDEO].source_label, EmotionLabel.NEGATIVE
        )

    def test_weighted_positive_result_maps_to_final_heart(self) -> None:
        observations = (
            observation(Modality.TEXT, EmotionLabel.POSITIVE),
            observation(Modality.AUDIO, EmotionLabel.POSITIVE),
            observation(Modality.VIDEO, EmotionLabel.NEUTRAL),
        )
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        state = AvatarStateMapper().map(analysis)

        self.assertEqual(state.expression, AvatarExpression.HEART)
        self.assertEqual(state.source_label, EmotionLabel.POSITIVE)

    def test_wave_selects_greeting_without_becoming_fourth_modality(self) -> None:
        video = ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.8,
            quality=0.9,
            status=EmotionStatus.OK,
            observed_actions=(
                ObservedAction(ActionType.WAVE, 0.9, "side-to-side hand motion"),
            ),
        )
        observations = (observation(Modality.TEXT, EmotionLabel.NEUTRAL), video)
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        state = AvatarStateMapper().map(analysis)

        self.assertEqual(state.motion, AvatarMotion.GREETING)
        self.assertEqual(len(state.modality_expressions), 2)

    def test_non_wave_active_actions_select_neutral_observe_motion(self) -> None:
        fallback_actions = (
            ActionType.THUMBS_UP,
            ActionType.CLAP,
            ActionType.NOD,
            ActionType.HEAD_SHAKE,
            ActionType.HANDS_UP,
            ActionType.POINT,
            ActionType.OTHER,
        )
        for action_type in fallback_actions:
            with self.subTest(action_type=action_type):
                video = ModalityEmotion.video_result(
                    label=EmotionLabel.NEUTRAL,
                    confidence=0.8,
                    quality=0.9,
                    status=EmotionStatus.OK,
                    observed_actions=(
                        ObservedAction(
                            action_type,
                            0.75,
                            "visible body movement",
                        ),
                    ),
                )
                observations = (video,)
                analysis = EmotionTurnAnalysis(
                    observations=observations,
                    fusion=EmotionFusionService().fuse(observations),
                )

                self.assertEqual(
                    AvatarStateMapper().map(analysis).motion,
                    AvatarMotion.OBSERVE,
                )

    def test_low_confidence_other_action_does_not_move_avatar(self) -> None:
        video = ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.8,
            quality=0.9,
            status=EmotionStatus.OK,
            observed_actions=(ObservedAction(ActionType.OTHER, 0.59),),
        )
        observations = (video,)
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        self.assertEqual(AvatarStateMapper().map(analysis).motion, AvatarMotion.IDLE)

    def test_still_never_uses_observe_fallback(self) -> None:
        video = ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
            observed_actions=(ObservedAction(ActionType.STILL, 0.99),),
        )
        observations = (video,)
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        self.assertEqual(AvatarStateMapper().map(analysis).motion, AvatarMotion.IDLE)

    def test_wave_has_priority_over_other_fallback(self) -> None:
        video = ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.8,
            quality=0.9,
            status=EmotionStatus.OK,
            observed_actions=(
                ObservedAction(ActionType.OTHER, 0.95),
                ObservedAction(ActionType.WAVE, 0.75),
            ),
        )
        observations = (video,)
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        self.assertEqual(
            AvatarStateMapper().map(analysis).motion,
            AvatarMotion.GREETING,
        )

    def test_generic_negative_does_not_force_cry_expression(self) -> None:
        observations = (
            observation(Modality.TEXT, EmotionLabel.NEGATIVE),
            observation(Modality.AUDIO, EmotionLabel.NEGATIVE),
        )
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        state = AvatarStateMapper().map(analysis)

        self.assertEqual(state.source_label, EmotionLabel.NEGATIVE)
        self.assertEqual(state.expression, AvatarExpression.NEUTRAL)

    def test_single_reliable_input_keeps_its_expression_without_strong_fusion(
        self,
    ) -> None:
        text = observation(Modality.TEXT, EmotionLabel.POSITIVE)
        audio = ModalityEmotion.audio_result(
            label=EmotionLabel.UNCERTAIN,
            confidence=0.0,
            quality=0.0,
            status=EmotionStatus.INSUFFICIENT_EVIDENCE,
        )
        video = ModalityEmotion.video_result(
            label=EmotionLabel.UNCERTAIN,
            confidence=0.0,
            quality=0.0,
            status=EmotionStatus.DISABLED,
        )
        observations = (text, audio, video)
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )

        state = AvatarStateMapper().map(analysis)

        self.assertEqual(
            analysis.fusion.conflict_type,
            ConflictType.INSUFFICIENT_EVIDENCE,
        )
        self.assertEqual(state.source_label, EmotionLabel.UNCERTAIN)
        self.assertEqual(state.expression, AvatarExpression.HEART)


if __name__ == "__main__":
    unittest.main()
