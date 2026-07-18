"""Deterministically convert recognized actions into bounded video evidence."""

from __future__ import annotations

from dataclasses import dataclass

from packages.schemas import (
    ActionType,
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    ObservedAction,
)


@dataclass(frozen=True, slots=True)
class ActionEmotionConfig:
    minimum_action_confidence: float = 0.60
    maximum_action_weight: float = 0.25
    positive_threshold: float = 0.25
    negative_threshold: float = -0.25

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_action_confidence <= 1.0:
            raise ValueError("minimum_action_confidence must be between 0 and 1")
        if not 0.0 <= self.maximum_action_weight <= 0.5:
            raise ValueError("maximum_action_weight must be between 0 and 0.5")


_ACTION_PRIORS: dict[ActionType, tuple[float, float]] = {
    ActionType.WAVE: (1.0, 0.45),
    ActionType.THUMBS_UP: (1.0, 0.80),
    ActionType.CLAP: (1.0, 0.70),
    ActionType.NOD: (0.0, 0.35),
    ActionType.HEAD_SHAKE: (0.0, 0.35),
}

_LABEL_SCORES = {
    EmotionLabel.POSITIVE: 1.0,
    EmotionLabel.NEUTRAL: 0.0,
    EmotionLabel.NEGATIVE: -1.0,
}


def apply_action_emotion(
    visual: ModalityEmotion,
    config: ActionEmotionConfig | None = None,
) -> ModalityEmotion:
    """Blend action priors into one video result without creating a new modality."""
    effective_config = config or ActionEmotionConfig()
    mapped = _mapped_actions(visual.observed_actions, effective_config)
    if not mapped:
        return visual

    action_support = sum(support for _, support in mapped)
    action_score = sum(score * support for score, support in mapped) / action_support
    action_support = min(1.0, action_support / len(mapped))
    action_weight = effective_config.maximum_action_weight

    visual_score = _LABEL_SCORES.get(visual.label)
    visual_support = (
        visual.confidence * (1.0 - action_weight) if visual_score is not None else 0.0
    )
    bounded_action_support = action_support * action_weight
    total_support = visual_support + bounded_action_support
    if total_support <= 0.0:
        return visual
    weighted_score = (
        (visual_score or 0.0) * visual_support + action_score * bounded_action_support
    ) / total_support
    label = _label_from_score(weighted_score, effective_config)
    confidence = min(1.0, total_support)
    status = (
        EmotionStatus.UNCERTAIN
        if visual.status is not EmotionStatus.OK or confidence < 0.5
        else EmotionStatus.OK
    )
    if label is EmotionLabel.UNCERTAIN:
        status = EmotionStatus.UNCERTAIN
    metadata = dict(visual.raw_metadata)
    metadata["action_emotion_weight"] = action_weight
    return ModalityEmotion.video_result(
        label=label,
        confidence=confidence,
        quality=visual.quality,
        status=status,
        fine_emotion=visual.fine_emotion,
        evidence=visual.evidence,
        observed_actions=visual.observed_actions,
        raw_metadata=metadata,
    )


def _mapped_actions(
    actions: tuple[ObservedAction, ...], config: ActionEmotionConfig
) -> list[tuple[float, float]]:
    mapped: list[tuple[float, float]] = []
    for action in actions:
        prior = _ACTION_PRIORS.get(action.action)
        if prior is None or action.confidence < config.minimum_action_confidence:
            continue
        score, prior_strength = prior
        mapped.append((score, action.confidence * prior_strength))
    return mapped


def _label_from_score(score: float, config: ActionEmotionConfig) -> EmotionLabel:
    if score >= config.positive_threshold:
        return EmotionLabel.POSITIVE
    if score <= config.negative_threshold:
        return EmotionLabel.NEGATIVE
    return EmotionLabel.NEUTRAL
