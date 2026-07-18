"""Provider-independent deterministic fusion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .emotion import SCHEMA_VERSION, EmotionLabel, Modality, ModalityEmotion


class ConflictType(StrEnum):
    CONSISTENT_POSITIVE = "consistent_positive"
    CONSISTENT_NEUTRAL = "consistent_neutral"
    CONSISTENT_NEGATIVE = "consistent_negative"
    VERBAL_POSITIVE_BEHAVIOR_NEGATIVE = "verbal_positive_behavior_negative"
    VERBAL_NEGATIVE_BEHAVIOR_POSITIVE = "verbal_negative_behavior_positive"
    AUDIO_VISUAL_DISAGREEMENT = "audio_visual_disagreement"
    UNCERTAIN = "uncertain"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CompanionStrategy(StrEnum):
    POSITIVE_ENGAGEMENT = "positive_engagement"
    EMOTIONAL_VALIDATION = "emotional_validation"
    GENTLE_CHECK_IN = "gentle_check_in"
    CALM_LISTENING = "calm_listening"
    NEUTRAL_CLARIFICATION = "neutral_clarification"
    NORMAL_CONVERSATION = "normal_conversation"


@dataclass(frozen=True, slots=True)
class ConflictResult:
    fused_label: EmotionLabel
    weighted_score: float
    conflict: bool
    conflict_type: ConflictType
    conflict_score: float
    reliable_modalities: tuple[Modality, ...]
    strategy: CompanionStrategy
    explanation: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ConflictResult version: {self.schema_version}"
            )
        if not -1.0 <= self.weighted_score <= 1.0:
            raise ValueError("weighted_score must be between -1 and 1")
        if not 0.0 <= self.conflict_score <= 1.0:
            raise ValueError("conflict_score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EmotionTurnAnalysis:
    observations: tuple[ModalityEmotion, ...]
    fusion: ConflictResult
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported EmotionTurnAnalysis version: {self.schema_version}"
            )
