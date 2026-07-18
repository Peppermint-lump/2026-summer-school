"""Canonical deterministic avatar expression contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .emotion import SCHEMA_VERSION, EmotionLabel, Modality


class AvatarEmotion(StrEnum):
    NEUTRAL = "neutral"
    JOY = "joy"
    AFFECTION = "affection"
    SADNESS = "sadness"
    ANGER = "anger"
    SLEEPY = "sleepy"
    BLUSH = "blush"


class AvatarExpression(StrEnum):
    NEUTRAL = "neutral"
    HEART = "heart"
    STAR = "star"
    CRY = "cry"
    SLEEPY = "sleepy"
    BLUSH = "blush"
    BUTTERFLY = "butterfly"


class AvatarMotion(StrEnum):
    IDLE = "idle"
    GREETING = "greeting"


@dataclass(frozen=True, slots=True)
class ModalityExpression:
    modality: Modality
    source_label: EmotionLabel
    avatar_emotion: AvatarEmotion
    expression: AvatarExpression
    reliability: float
    contributes_to_fusion: bool
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported ModalityExpression version")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("expression reliability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class AvatarState:
    emotion: AvatarEmotion
    expression: AvatarExpression
    motion: AvatarMotion
    source_label: EmotionLabel
    weighted_score: float
    modality_expressions: tuple[ModalityExpression, ...]
    reason: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported AvatarState version")
        if not -1.0 <= self.weighted_score <= 1.0:
            raise ValueError("avatar weighted_score must be between -1 and 1")
