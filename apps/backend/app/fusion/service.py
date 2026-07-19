"""Pure deterministic reliability-weighted emotion fusion."""

from __future__ import annotations

from packages.schemas import (
    CompanionStrategy,
    ConflictResult,
    ConflictType,
    EmotionLabel,
    EmotionStatus,
    FusionConfig,
    Modality,
    ModalityEmotion,
)

_LABEL_SCORES = {
    EmotionLabel.POSITIVE: 1.0,
    EmotionLabel.NEUTRAL: 0.0,
    EmotionLabel.NEGATIVE: -1.0,
}

_MODALITY_ORDER = (Modality.TEXT, Modality.AUDIO, Modality.VIDEO)


class EmotionFusionService:
    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()

    def fuse(self, observations: tuple[ModalityEmotion, ...]) -> ConflictResult:
        by_modality = _index_observations(observations)
        reliable = tuple(
            by_modality[modality]
            for modality in _MODALITY_ORDER
            if modality in by_modality
            and _is_reliable(by_modality[modality], self.config)
        )
        if len(reliable) < 2:
            return ConflictResult(
                fused_label=EmotionLabel.UNCERTAIN,
                weighted_score=0.0,
                conflict=False,
                conflict_type=ConflictType.INSUFFICIENT_EVIDENCE,
                conflict_score=0.0,
                reliable_modalities=tuple(item.modality for item in reliable),
                strategy=CompanionStrategy.NORMAL_CONVERSATION,
                explanation="少于两个模态达到可靠阈值，保留为不确定观察。",
            )

        weighted_score = _weighted_score(reliable, self.config)
        fused_label = _label_from_score(weighted_score, self.config)
        conflict_type = _classify_conflict(reliable)
        conflict = conflict_type in {
            ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE,
            ConflictType.VERBAL_NEGATIVE_BEHAVIOR_POSITIVE,
            ConflictType.AUDIO_VISUAL_DISAGREEMENT,
        }
        conflict_score = _conflict_score(reliable) if conflict else 0.0
        return ConflictResult(
            fused_label=fused_label,
            weighted_score=round(weighted_score, 4),
            conflict=conflict,
            conflict_type=conflict_type,
            conflict_score=round(conflict_score, 4),
            reliable_modalities=tuple(item.modality for item in reliable),
            strategy=_strategy_for(conflict_type, fused_label),
            explanation=_explanation_for(conflict_type),
        )


def _index_observations(
    observations: tuple[ModalityEmotion, ...],
) -> dict[Modality, ModalityEmotion]:
    indexed: dict[Modality, ModalityEmotion] = {}
    for observation in observations:
        if observation.modality in indexed:
            raise ValueError(f"duplicate modality result: {observation.modality}")
        indexed[observation.modality] = observation
    return indexed


def _is_reliable(observation: ModalityEmotion, config: FusionConfig) -> bool:
    return (
        observation.status is EmotionStatus.OK
        and observation.label in _LABEL_SCORES
        and observation.reliability >= config.reliable_threshold
    )


def _weighted_score(
    observations: tuple[ModalityEmotion, ...], config: FusionConfig
) -> float:
    configured_weights = {
        Modality.TEXT: config.text_weight,
        Modality.AUDIO: config.audio_weight,
        Modality.VIDEO: config.video_weight,
    }
    contributions = [
        (
            _LABEL_SCORES[observation.label],
            configured_weights[observation.modality] * observation.reliability,
        )
        for observation in observations
    ]
    total_weight = sum(weight for _, weight in contributions)
    return sum(score * weight for score, weight in contributions) / total_weight


def _label_from_score(score: float, config: FusionConfig) -> EmotionLabel:
    if score >= config.positive_threshold:
        return EmotionLabel.POSITIVE
    if score <= config.negative_threshold:
        return EmotionLabel.NEGATIVE
    return EmotionLabel.NEUTRAL


def _classify_conflict(
    observations: tuple[ModalityEmotion, ...],
) -> ConflictType:
    labels = {item.modality: item.label for item in observations}
    unique_labels = set(labels.values())
    if len(unique_labels) == 1:
        label = next(iter(unique_labels))
        return {
            EmotionLabel.POSITIVE: ConflictType.CONSISTENT_POSITIVE,
            EmotionLabel.NEUTRAL: ConflictType.CONSISTENT_NEUTRAL,
            EmotionLabel.NEGATIVE: ConflictType.CONSISTENT_NEGATIVE,
        }[label]
    text_label = labels.get(Modality.TEXT)
    behavior_labels = {
        label
        for modality, label in labels.items()
        if modality in {Modality.AUDIO, Modality.VIDEO}
    }
    if text_label is EmotionLabel.POSITIVE and EmotionLabel.NEGATIVE in behavior_labels:
        return ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE
    if text_label is EmotionLabel.NEGATIVE and EmotionLabel.POSITIVE in behavior_labels:
        return ConflictType.VERBAL_NEGATIVE_BEHAVIOR_POSITIVE
    if (
        Modality.AUDIO in labels
        and Modality.VIDEO in labels
        and labels[Modality.AUDIO] is not labels[Modality.VIDEO]
    ):
        return ConflictType.AUDIO_VISUAL_DISAGREEMENT
    return ConflictType.UNCERTAIN


def _conflict_score(observations: tuple[ModalityEmotion, ...]) -> float:
    scores = [_LABEL_SCORES[item.label] for item in observations]
    disagreement = (max(scores) - min(scores)) / 2.0
    reliability = sum(item.reliability for item in observations) / len(observations)
    return min(1.0, disagreement * reliability)


def _strategy_for(
    conflict_type: ConflictType, fused_label: EmotionLabel
) -> CompanionStrategy:
    explicit = {
        ConflictType.CONSISTENT_POSITIVE: CompanionStrategy.POSITIVE_ENGAGEMENT,
        ConflictType.CONSISTENT_NEGATIVE: CompanionStrategy.EMOTIONAL_VALIDATION,
        ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE: (
            CompanionStrategy.GENTLE_CHECK_IN
        ),
        ConflictType.VERBAL_NEGATIVE_BEHAVIOR_POSITIVE: (
            CompanionStrategy.NEUTRAL_CLARIFICATION
        ),
        ConflictType.AUDIO_VISUAL_DISAGREEMENT: CompanionStrategy.NEUTRAL_CLARIFICATION,
        ConflictType.UNCERTAIN: CompanionStrategy.NORMAL_CONVERSATION,
        ConflictType.INSUFFICIENT_EVIDENCE: CompanionStrategy.NORMAL_CONVERSATION,
    }
    if conflict_type in explicit:
        return explicit[conflict_type]
    if fused_label is EmotionLabel.NEUTRAL:
        return CompanionStrategy.CALM_LISTENING
    return CompanionStrategy.NORMAL_CONVERSATION


def _explanation_for(conflict_type: ConflictType) -> str:
    return {
        ConflictType.CONSISTENT_POSITIVE: "可靠的模态观察整体偏积极。",
        ConflictType.CONSISTENT_NEUTRAL: "可靠的模态观察整体偏中性。",
        ConflictType.CONSISTENT_NEGATIVE: "可靠的模态观察整体偏消极。",
        ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE: (
            "文字表达偏积极，可靠的非语言观察偏消极。"
        ),
        ConflictType.VERBAL_NEGATIVE_BEHAVIOR_POSITIVE: (
            "文字表达偏消极，可靠的非语言观察偏积极。"
        ),
        ConflictType.AUDIO_VISUAL_DISAGREEMENT: "可靠的语音与视觉观察不一致。",
        ConflictType.UNCERTAIN: "可靠观察方向不完全一致，采用保守融合结果。",
        ConflictType.INSUFFICIENT_EVIDENCE: "可靠证据不足。",
    }[conflict_type]
