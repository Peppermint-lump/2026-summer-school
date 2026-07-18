"""Composition root for the canonical per-turn emotion runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apps.backend.app.avatar.state_mapper import AvatarStateMapper
from apps.backend.app.capture.camera_buffer import (
    CameraBuffer,
    CameraBufferConfig,
    CameraState,
)
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.capture.video_export import FrameExportConfig, FrameExporter
from apps.backend.app.emotion.audio.quality import AudioQualityEvaluator
from apps.backend.app.emotion.audio.service import (
    AudioEmotionService,
    AudioEmotionServiceConfig,
)
from apps.backend.app.emotion.providers.base import (
    AudioEmotionRequest,
    TextEmotionRequest,
    VideoEmotionRequest,
)
from apps.backend.app.emotion.providers.glm import (
    GlmTextConfig,
    GlmTextEmotionProvider,
)
from apps.backend.app.emotion.providers.mimo import (
    MiMoAudioConfig,
    MiMoAudioEmotionProvider,
    MiMoVideoConfig,
    MiMoVideoEmotionProvider,
)
from apps.backend.app.emotion.text.service import (
    TextEmotionService,
    TextEmotionServiceConfig,
)
from apps.backend.app.emotion.video.action_emotion import ActionEmotionConfig
from apps.backend.app.emotion.video.face_quality import (
    FaceQualityConfig,
    FaceQualityEvaluator,
    OpenCVFaceDetector,
)
from apps.backend.app.emotion.video.preprocess import VideoTurnPreprocessor
from apps.backend.app.emotion.video.service import (
    VideoEmotionService,
    VideoEmotionServiceConfig,
)
from apps.backend.app.fusion.service import EmotionFusionService
from apps.backend.app.infrastructure.config import EnvironmentSecretStore
from apps.backend.app.infrastructure.http_client import HttpxJsonClient
from packages.schemas import AppConfig, ModalityEmotion

from .emotion_middleware import EmotionMiddleware
from .video_emotion_middleware import VideoEmotionMiddleware


@dataclass(slots=True)
class EmotionRuntime:
    middleware: EmotionMiddleware
    camera: CameraBuffer
    camera_enabled: bool

    def start(self) -> None:
        if self.camera_enabled and self.camera.state is CameraState.STOPPED:
            self.camera.start()

    def stop(self) -> None:
        self.camera.stop()


def build_emotion_runtime(
    config: AppConfig,
    *,
    repository_root: Path,
    secret_store: EnvironmentSecretStore | None = None,
) -> EmotionRuntime:
    """Build providers at the edge while keeping all modality inputs isolated."""
    secrets = secret_store or EnvironmentSecretStore()
    http_client = HttpxJsonClient()
    runtime_root = repository_root / "runtime"
    cleaner = TurnMediaCleaner(
        runtime_root,
        retain_media=config.camera.retain_media,
    )
    camera = CameraBuffer(
        CameraBufferConfig(
            device_index=config.camera.device_index,
            width=config.camera.width,
            height=config.camera.height,
            target_fps=config.camera.target_fps,
            buffer_seconds=config.camera.buffer_seconds,
        )
    )

    text = config.text_emotion
    text_provider = (
        GlmTextEmotionProvider(
            GlmTextConfig(
                base_url=text.base_url,
                api_key=secrets.get_required(text.api_key_secret_name),
                model=text.model,
                timeout_seconds=text.timeout_seconds,
                max_retries=text.max_retries,
            ),
            http_client,
            prompt=text.prompt_path.read_text(encoding="utf-8"),
        )
        if text.enabled
        else _DisabledTextProvider()
    )
    text_service = TextEmotionService(
        text_provider,
        TextEmotionServiceConfig(
            enabled=text.enabled,
            provider_timeout_seconds=text.timeout_seconds,
            prompt_version=text.prompt_version,
        ),
    )

    audio = config.audio_emotion
    audio_provider = (
        MiMoAudioEmotionProvider(
            MiMoAudioConfig(
                base_url=audio.base_url,
                api_key=secrets.get_required(audio.api_key_secret_name),
                model=audio.model,
                timeout_seconds=audio.timeout_seconds,
                max_retries=audio.max_retries,
                max_media_bytes=audio.max_media_bytes,
            ),
            http_client,
            prompt=audio.prompt_path.read_text(encoding="utf-8"),
        )
        if audio.enabled
        else _DisabledAudioProvider()
    )
    audio_service = AudioEmotionService(
        audio_provider,
        AudioQualityEvaluator(),
        AudioEmotionServiceConfig(
            enabled=audio.enabled,
            provider_timeout_seconds=audio.timeout_seconds,
            prompt_version=audio.prompt_version,
            minimum_quality=audio.minimum_quality,
        ),
    )

    video = config.video_emotion
    video_provider = (
        MiMoVideoEmotionProvider(
            MiMoVideoConfig(
                base_url=video.base_url,
                api_key=secrets.get_required(video.api_key_secret_name),
                model=video.model,
                timeout_seconds=video.timeout_seconds,
                max_retries=video.max_retries,
                max_frames=config.camera.max_sampled_frames,
            ),
            http_client,
            prompt=video.prompt_path.read_text(encoding="utf-8"),
        )
        if video.enabled
        else _DisabledVideoProvider()
    )
    evaluator = FaceQualityEvaluator(
        OpenCVFaceDetector(),
        FaceQualityConfig(sufficient_quality=video.minimum_quality),
    )
    video_service = VideoEmotionService(
        video_provider,
        VideoEmotionServiceConfig(
            enabled=video.enabled,
            provider_timeout_seconds=video.timeout_seconds,
            prompt_version=video.prompt_version,
            action_emotion=ActionEmotionConfig(
                minimum_action_confidence=video.action_minimum_confidence,
                maximum_action_weight=video.action_emotion_weight,
            ),
        ),
    )
    video_middleware = VideoEmotionMiddleware(
        VideoTurnPreprocessor(
            camera,
            evaluator,
            FrameExporter(
                runtime_root,
                FrameExportConfig(
                    sample_fps=config.camera.sample_fps,
                    max_frames=config.camera.max_sampled_frames,
                ),
            ),
        ),
        video_service,
        cleaner,
        camera_enabled=config.camera.enabled and video.enabled,
        cleanup_after_analysis=False,
    )
    middleware = EmotionMiddleware(
        text_service,
        audio_service,
        video_middleware,
        EmotionFusionService(config.fusion),
        AvatarStateMapper(config.fusion),
        media_cleaner=cleaner,
    )
    return EmotionRuntime(
        middleware=middleware,
        camera=camera,
        camera_enabled=config.camera.enabled and video.enabled,
    )


class _DisabledTextProvider:
    async def analyze_text(self, request: TextEmotionRequest) -> ModalityEmotion:
        raise RuntimeError("disabled text provider was called")


class _DisabledAudioProvider:
    async def analyze_audio(self, request: AudioEmotionRequest) -> ModalityEmotion:
        raise RuntimeError("disabled audio provider was called")


class _DisabledVideoProvider:
    async def analyze_video(self, request: VideoEmotionRequest) -> ModalityEmotion:
        raise RuntimeError("disabled video provider was called")
