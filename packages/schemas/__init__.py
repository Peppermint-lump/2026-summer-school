"""Versioned canonical domain schemas."""

from .config import (
    AppConfig,
    CameraCaptureConfig,
    FusionConfig,
    TextAnalysisConfig,
    VideoAnalysisConfig,
)
from .emotion import (
    ActionType,
    EmotionLabel,
    EmotionStatus,
    Modality,
    ModalityEmotion,
    ObservedAction,
    TurnRecord,
    VideoArtifactStatus,
    VideoTurnArtifact,
)
from .fusion import (
    CompanionStrategy,
    ConflictResult,
    ConflictType,
    EmotionTurnAnalysis,
)

__all__ = [
    "AppConfig",
    "ActionType",
    "CameraCaptureConfig",
    "CompanionStrategy",
    "ConflictResult",
    "ConflictType",
    "EmotionLabel",
    "EmotionStatus",
    "EmotionTurnAnalysis",
    "FusionConfig",
    "Modality",
    "ModalityEmotion",
    "ObservedAction",
    "TextAnalysisConfig",
    "TurnRecord",
    "VideoArtifactStatus",
    "VideoAnalysisConfig",
    "VideoTurnArtifact",
]
