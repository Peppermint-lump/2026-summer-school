"""Provider-independent ports for video-only emotion observation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from packages.schemas import ModalityEmotion


class ProviderError(RuntimeError):
    """Typed external-provider failure safe for application-level mapping."""


class ProviderRateLimitError(ProviderError):
    """Provider rejected the request because of rate limiting."""


class ProviderInvalidOutputError(ProviderError):
    """Provider returned malformed or schema-invalid output."""


@dataclass(frozen=True, slots=True)
class VideoEmotionRequest:
    turn_id: str
    frame_paths: tuple[Path, ...]
    quality: float
    prompt_version: str

    def __post_init__(self) -> None:
        if not self.turn_id or not self.frame_paths:
            raise ValueError("video emotion requests require a turn and frames")
        if not 0.0 <= self.quality <= 1.0:
            raise ValueError("quality must be between 0 and 1")
        if not self.prompt_version:
            raise ValueError("prompt_version must be non-empty")


class VideoEmotionProvider(Protocol):
    async def analyze_video(self, request: VideoEmotionRequest) -> ModalityEmotion: ...
