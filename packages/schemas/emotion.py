"""Canonical, provider-independent data contracts for emotion processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


class Modality(StrEnum):
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"


class EmotionLabel(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNCERTAIN = "uncertain"


class EmotionStatus(StrEnum):
    OK = "ok"
    UNCERTAIN = "uncertain"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    DISABLED = "disabled"


class ActionType(StrEnum):
    WAVE = "wave"
    THUMBS_UP = "thumbs_up"
    CLAP = "clap"
    NOD = "nod"
    HEAD_SHAKE = "head_shake"
    HANDS_UP = "hands_up"
    POINT = "point"
    STILL = "still"
    OTHER = "other"


class VideoArtifactStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DISABLED = "disabled"
    CAPTURE_ERROR = "capture_error"


def _validate_unit_interval(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ObservedAction:
    action: ActionType
    confidence: float
    evidence: str = ""

    def __post_init__(self) -> None:
        _validate_unit_interval("action confidence", self.confidence)
        if len(self.evidence) > 200:
            raise ValueError("action evidence must not exceed 200 characters")


@dataclass(frozen=True, slots=True)
class TurnRecord:
    session_id: str
    turn_id: str
    speech_start_ms: int
    speech_end_ms: int
    audio_path: Path | None = None
    video_path: Path | None = None
    frame_paths: tuple[Path, ...] = ()
    transcript: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported TurnRecord version: {self.schema_version}")
        if not self.session_id or not self.turn_id:
            raise ValueError("session_id and turn_id must be non-empty")
        if self.speech_start_ms < 0 or self.speech_end_ms < self.speech_start_ms:
            raise ValueError("invalid speech time range")


@dataclass(frozen=True, slots=True)
class VideoTurnArtifact:
    turn_id: str
    status: VideoArtifactStatus
    frame_paths: tuple[Path, ...] = ()
    video_path: Path | None = None
    captured_frame_count: int = 0
    sampled_frame_count: int = 0
    quality: float = 0.0
    quality_reasons: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported VideoTurnArtifact version: {self.schema_version}"
            )
        if not self.turn_id:
            raise ValueError("turn_id must be non-empty")
        if self.captured_frame_count < 0 or self.sampled_frame_count < 0:
            raise ValueError("frame counts must be non-negative")
        _validate_unit_interval("quality", self.quality)


@dataclass(frozen=True, slots=True)
class ModalityEmotion:
    modality: Modality
    label: EmotionLabel
    confidence: float
    quality: float
    reliability: float
    status: EmotionStatus
    fine_emotion: str | None = None
    evidence: tuple[str, ...] = ()
    observed_actions: tuple[ObservedAction, ...] = ()
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported ModalityEmotion version: {self.schema_version}"
            )
        _validate_unit_interval("confidence", self.confidence)
        _validate_unit_interval("quality", self.quality)
        _validate_unit_interval("reliability", self.reliability)
        expected = round(self.confidence * self.quality, 10)
        if abs(self.reliability - expected) > 1e-9:
            raise ValueError("reliability must equal confidence * quality")
        forbidden_metadata = {"frames", "base64", "api_key", "authorization"}
        if forbidden_metadata.intersection(self.raw_metadata):
            raise ValueError("raw_metadata contains sensitive media or credentials")
        if self.modality is not Modality.VIDEO and self.observed_actions:
            raise ValueError("observed actions belong only to the video modality")

    @classmethod
    def video_result(
        cls,
        *,
        label: EmotionLabel,
        confidence: float,
        quality: float,
        status: EmotionStatus,
        fine_emotion: str | None = None,
        evidence: tuple[str, ...] = (),
        observed_actions: tuple[ObservedAction, ...] = (),
        raw_metadata: dict[str, Any] | None = None,
    ) -> ModalityEmotion:
        return cls(
            modality=Modality.VIDEO,
            label=label,
            confidence=confidence,
            quality=quality,
            reliability=round(confidence * quality, 10),
            status=status,
            fine_emotion=fine_emotion,
            evidence=evidence,
            observed_actions=observed_actions,
            raw_metadata=raw_metadata or {},
        )

    @classmethod
    def text_result(
        cls,
        *,
        label: EmotionLabel,
        confidence: float,
        quality: float,
        status: EmotionStatus,
        fine_emotion: str | None = None,
        evidence: tuple[str, ...] = (),
        raw_metadata: dict[str, Any] | None = None,
    ) -> ModalityEmotion:
        return cls(
            modality=Modality.TEXT,
            label=label,
            confidence=confidence,
            quality=quality,
            reliability=round(confidence * quality, 10),
            status=status,
            fine_emotion=fine_emotion,
            evidence=evidence,
            raw_metadata=raw_metadata or {},
        )

    @classmethod
    def audio_result(
        cls,
        *,
        label: EmotionLabel,
        confidence: float,
        quality: float,
        status: EmotionStatus,
        fine_emotion: str | None = None,
        evidence: tuple[str, ...] = (),
        raw_metadata: dict[str, Any] | None = None,
    ) -> ModalityEmotion:
        return cls(
            modality=Modality.AUDIO,
            label=label,
            confidence=confidence,
            quality=quality,
            reliability=round(confidence * quality, 10),
            status=status,
            fine_emotion=fine_emotion,
            evidence=evidence,
            raw_metadata=raw_metadata or {},
        )
