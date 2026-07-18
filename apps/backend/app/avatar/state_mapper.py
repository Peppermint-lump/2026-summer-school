"""Map independently observed modality emotions to a safe Live2D state."""

from __future__ import annotations

from packages.schemas import (
    ActionType,
    AvatarEmotion,
    AvatarExpression,
    AvatarMotion,
    AvatarState,
    ConflictType,
    EmotionLabel,
    EmotionStatus,
    EmotionTurnAnalysis,
    FusionConfig,
    Modality,
    ModalityEmotion,
    ModalityExpression,
)


class AvatarStateMapper:
    def __init__(self, fusion_config: FusionConfig | None = None) -> None:
        self._fusion_config = fusion_config or FusionConfig()

    def map(self, analysis: EmotionTurnAnalysis) -> AvatarState:
        suggestions = tuple(
            self._suggestion(observation) for observation in analysis.observations
        )
        emotion, expression = self._final_expression(analysis)
        motion = (
            AvatarMotion.GREETING
            if _has_reliable_wave(analysis.observations)
            else AvatarMotion.IDLE
        )
        return AvatarState(
            emotion=emotion,
            expression=expression,
            motion=motion,
            source_label=analysis.fusion.fused_label,
            weighted_score=analysis.fusion.weighted_score,
            modality_expressions=suggestions,
            reason=analysis.fusion.explanation,
        )

    def _suggestion(self, observation: ModalityEmotion) -> ModalityExpression:
        contributes = (
            observation.status is EmotionStatus.OK
            and observation.label is not EmotionLabel.UNCERTAIN
            and observation.reliability >= self._fusion_config.reliable_threshold
        )
        emotion, expression = _expression_for_observation(observation)
        return ModalityExpression(
            modality=observation.modality,
            source_label=observation.label,
            avatar_emotion=emotion,
            expression=expression,
            reliability=observation.reliability,
            contributes_to_fusion=contributes,
        )

    def _final_expression(
        self, analysis: EmotionTurnAnalysis
    ) -> tuple[AvatarEmotion, AvatarExpression]:
        if analysis.fusion.fused_label is EmotionLabel.POSITIVE:
            return AvatarEmotion.AFFECTION, AvatarExpression.HEART
        if analysis.fusion.fused_label is EmotionLabel.NEGATIVE:
            if any(_explicit_strong_crying(item) for item in analysis.observations):
                return AvatarEmotion.SADNESS, AvatarExpression.CRY
            return AvatarEmotion.SADNESS, AvatarExpression.NEUTRAL
        if analysis.fusion.conflict_type is ConflictType.INSUFFICIENT_EVIDENCE:
            reliable = tuple(
                item
                for item in analysis.observations
                if item.status is EmotionStatus.OK
                and item.label is not EmotionLabel.UNCERTAIN
                and item.reliability >= self._fusion_config.reliable_threshold
            )
            if len(reliable) == 1:
                return _expression_for_observation(reliable[0])
        return AvatarEmotion.NEUTRAL, AvatarExpression.NEUTRAL


def _expression_for_observation(
    observation: ModalityEmotion,
) -> tuple[AvatarEmotion, AvatarExpression]:
    if observation.status is not EmotionStatus.OK:
        return AvatarEmotion.NEUTRAL, AvatarExpression.NEUTRAL
    if observation.label is EmotionLabel.POSITIVE:
        return AvatarEmotion.AFFECTION, AvatarExpression.HEART
    if observation.label is EmotionLabel.NEGATIVE:
        if _explicit_strong_crying(observation):
            return AvatarEmotion.SADNESS, AvatarExpression.CRY
        return AvatarEmotion.SADNESS, AvatarExpression.NEUTRAL
    return AvatarEmotion.NEUTRAL, AvatarExpression.NEUTRAL


def _explicit_strong_crying(observation: ModalityEmotion) -> bool:
    if observation.reliability < 0.8:
        return False
    evidence = " ".join((observation.fine_emotion or "", *observation.evidence)).lower()
    return any(cue in evidence for cue in ("crying", "tears", "哭泣", "流泪"))


def _has_reliable_wave(observations: tuple[ModalityEmotion, ...]) -> bool:
    for observation in observations:
        if observation.modality is not Modality.VIDEO:
            continue
        if any(
            action.action is ActionType.WAVE and action.confidence >= 0.60
            for action in observation.observed_actions
        ):
            return True
    return False
