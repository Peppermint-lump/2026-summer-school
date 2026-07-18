"""Canonical output of one independently analyzed multimodal turn."""

from __future__ import annotations

from dataclasses import dataclass

from .avatar import AvatarState
from .emotion import SCHEMA_VERSION
from .fusion import EmotionTurnAnalysis


@dataclass(frozen=True, slots=True)
class EmotionTurnResult:
    analysis: EmotionTurnAnalysis
    avatar_state: AvatarState
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported EmotionTurnResult version")
