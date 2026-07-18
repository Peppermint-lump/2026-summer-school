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
    action_minimum_confidence: float = 0.60
    action_emotion_weight: float = 0.25

    def __post_init__(self) -> None:
        if self.provider != "mimo":
            raise ValueError("only the configured MVP provider 'mimo' is supported")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid video provider timeout or retry configuration")
        if not 0.0 <= self.minimum_quality <= 1.0:
            raise ValueError("minimum_quality must be between 0 and 1")
        if not 0.0 <= self.action_minimum_confidence <= 1.0:
            raise ValueError("action_minimum_confidence must be between 0 and 1")
        if not 0.0 <= self.action_emotion_weight <= 0.5:
            raise ValueError("action_emotion_weight must be between 0 and 0.5")
        if not self.prompt_version or not self.api_key_secret_name:
            raise ValueError("prompt version and secret name must be non-empty")


@dataclass(frozen=True, slots=True)
class AudioAnalysisConfig:
    enabled: bool = False
    provider: str = "mimo"
    model: str = "mimo-v2.5"
    base_url: str = "https://api.xiaomimimo.com/v1"
    api_key_secret_name: str = "MIMO_API_KEY"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    prompt_path: Path = Path("configs/prompts/audio_emotion_v1.txt")
    prompt_version: str = "audio_emotion_v1"
    minimum_quality: float = 0.35
    max_media_bytes: int = 24 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.provider != "mimo":
            raise ValueError(
                "only the configured MVP audio provider 'mimo' is supported"
            )
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid audio provider timeout or retry configuration")
        if not 0.0 <= self.minimum_quality <= 1.0:
            raise ValueError("audio minimum_quality must be between 0 and 1")
        if self.max_media_bytes <= 0:
            raise ValueError("audio max_media_bytes must be positive")
        if not self.prompt_version or not self.api_key_secret_name:
            raise ValueError("prompt version and secret name must be non-empty")


@dataclass(frozen=True, slots=True)
class TextAnalysisConfig:
    enabled: bool = False
    provider: str = "glm"
    model: str = "glm-4.7-flash"
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    api_key_secret_name: str = "GLM_API_KEY"
    timeout_seconds: float = 12.0
    max_retries: int = 2
    prompt_path: Path = Path("configs/prompts/text_emotion_v1.txt")
    prompt_version: str = "text_emotion_v1"

    def __post_init__(self) -> None:
        if self.provider != "glm":
            raise ValueError("only the configured MVP text provider 'glm' is supported")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("invalid text provider timeout or retry configuration")
        if not self.prompt_version or not self.api_key_secret_name:
            raise ValueError("prompt version and secret name must be non-empty")


@dataclass(frozen=True, slots=True)
class FusionConfig:
    reliable_threshold: float = 0.55
    positive_threshold: float = 0.25
    negative_threshold: float = -0.25
    text_weight: float = 0.45
    audio_weight: float = 0.25
    video_weight: float = 0.30

    def __post_init__(self) -> None:
        if not 0.0 <= self.reliable_threshold <= 1.0:
            raise ValueError("fusion reliable_threshold must be between 0 and 1")
        if not 0.0 < self.positive_threshold <= 1.0:
            raise ValueError("fusion positive_threshold must be in (0, 1]")
        if not -1.0 <= self.negative_threshold < 0.0:
            raise ValueError("fusion negative_threshold must be in [-1, 0)")
        if self.negative_threshold >= self.positive_threshold:
            raise ValueError("fusion label thresholds overlap")
        weights = (self.text_weight, self.audio_weight, self.video_weight)
        if any(weight <= 0.0 for weight in weights):
            raise ValueError("fusion modality weights must be positive")


@dataclass(frozen=True, slots=True)
class AppConfig:
    camera: CameraCaptureConfig = CameraCaptureConfig()
    video_emotion: VideoAnalysisConfig = VideoAnalysisConfig()
    audio_emotion: AudioAnalysisConfig = AudioAnalysisConfig()
    text_emotion: TextAnalysisConfig = TextAnalysisConfig()
    fusion: FusionConfig = FusionConfig()
