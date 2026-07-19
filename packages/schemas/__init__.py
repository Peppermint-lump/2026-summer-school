"""Versioned canonical domain schemas."""

from .avatar import (
    AvatarEmotion,
    AvatarExpression,
    AvatarMotion,
    AvatarState,
    ModalityExpression,
)
from .config import (
    AppConfig,
    AudioAnalysisConfig,
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
from .result import EmotionTurnResult

__all__ = [
    "AppConfig",
    "ActionType",
    "AudioAnalysisConfig",
    "AvatarEmotion",
    "AvatarExpression",
    "AvatarMotion",
    "AvatarState",
    "CameraCaptureConfig",
    "CompanionStrategy",
    "ConflictResult",
    "ConflictType",
    "EmotionLabel",
    "EmotionStatus",
    "EmotionTurnAnalysis",
    "EmotionTurnResult",
    "FusionConfig",
    "Modality",
    "ModalityEmotion",
    "ModalityExpression",
    "ObservedAction",
    "TextAnalysisConfig",
    "TurnRecord",
    "VideoArtifactStatus",
    "VideoAnalysisConfig",
    "VideoTurnArtifact",
]
