"""Canonical, secret-free application configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CameraCaptureConfig:
    enabled: bool = False
    device_index: int = 0
    width: int = 640
    height: int = 480
    target_fps: float = 10.0
    buffer_seconds: float = 30.0
    sample_fps: float = 2.0
    max_sampled_frames: int = 12
    retain_media: bool = False

    def __post_init__(self) -> None:
        if self.device_index < 0:
            raise ValueError("camera device_index must be non-negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera dimensions must be positive")
        if self.target_fps <= 0 or self.buffer_seconds <= 0:
            raise ValueError("camera rate and buffer duration must be positive")
        if self.sample_fps <= 0 or self.max_sampled_frames <= 0:
            raise ValueError("camera sampling limits must be positive")


@dataclass(frozen=True, slots=True)
class VideoAnalysisConfig:
    enabled: bool = False
    provider: str = "mimo"
    model: str = "mimo-v2.5"
    base_url: str = ""
    api_key_secret_name: str = "MIMO_API_KEY"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    prompt_path: Path = Path("configs/prompts/video_emotion_v1.txt")
    prompt_version: str = "video_emotion_v1"
    minimum_quality: float = 0.45

    def __post_init__(self) -> None:
        if self.provider != "mimo":
            raise ValueError("only the configured MVP provider 'mimo' is supported")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid video provider timeout or retry configuration")
        if not 0.0 <= self.minimum_quality <= 1.0:
            raise ValueError("minimum_quality must be between 0 and 1")
        if not self.prompt_version or not self.api_key_secret_name:
            raise ValueError("prompt version and secret name must be non-empty")


@dataclass(frozen=True, slots=True)
class AppConfig:
    camera: CameraCaptureConfig = CameraCaptureConfig()
    video_emotion: VideoAnalysisConfig = VideoAnalysisConfig()
