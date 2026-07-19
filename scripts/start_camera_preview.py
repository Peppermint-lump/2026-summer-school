"""Start the local visual validation screen with explicit camera opt-in."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.backend.app.capture.camera_buffer import (
    CameraBuffer,
    CameraBufferConfig,
    CameraUnavailableError,
)
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.capture.video_export import FrameExportConfig, FrameExporter
from apps.backend.app.debug.camera_preview import (
    CameraPreviewApplication,
    run_camera_preview,
)
from apps.backend.app.debug.emotion_pipeline import EmotionDebugPipeline
from apps.backend.app.debug.trace_store import DebugTraceStore
from apps.backend.app.emotion.providers.glm import (
    GlmTextConfig,
    GlmTextEmotionProvider,
)
from apps.backend.app.emotion.providers.mimo import (
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
from apps.backend.app.infrastructure.config import (
    ConfigError,
    EnvironmentSecretStore,
    load_app_config,
)
from apps.backend.app.infrastructure.environment import load_project_environment
from apps.backend.app.infrastructure.http_client import HttpxJsonClient
from packages.schemas import AppConfig

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT / "configs" / "app.local.yaml",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--debug-output",
        type=Path,
        default=REPOSITORY_ROOT / "runtime" / "debug" / "emotion_pipeline",
        help="metadata-only per-turn JSON output directory",
    )
    return parser.parse_args()


def build_analyzer(
    config: AppConfig,
    *,
    camera: CameraBuffer,
    evaluator: FaceQualityEvaluator,
    debug_output: Path,
) -> EmotionDebugPipeline:
    video = config.video_emotion
    if not video.enabled:
        raise ConfigError("set VIDEO_EMOTION_ENABLED=true in .env")
    video_api_key = EnvironmentSecretStore().get_required(video.api_key_secret_name)
    runtime_root = REPOSITORY_ROOT / "runtime"
    preprocessor = VideoTurnPreprocessor(
        camera,
        evaluator,
        FrameExporter(
            runtime_root,
            FrameExportConfig(
                sample_fps=config.camera.sample_fps,
                max_frames=config.camera.max_sampled_frames,
            ),
        ),
    )
    video_service = VideoEmotionService(
        MiMoVideoEmotionProvider(
            MiMoVideoConfig(
                base_url=video.base_url,
                api_key=video_api_key,
                model=video.model,
                timeout_seconds=video.timeout_seconds,
                max_retries=video.max_retries,
                max_frames=config.camera.max_sampled_frames,
            ),
            HttpxJsonClient(),
            prompt=video.prompt_path.read_text(encoding="utf-8"),
        ),
        VideoEmotionServiceConfig(
            enabled=True,
            provider_timeout_seconds=video.timeout_seconds,
            prompt_version=video.prompt_version,
            action_emotion=ActionEmotionConfig(
                minimum_action_confidence=video.action_minimum_confidence,
                maximum_action_weight=video.action_emotion_weight,
            ),
        ),
    )
    text = config.text_emotion
    text_api_key = (
        EnvironmentSecretStore().get_required(text.api_key_secret_name)
        if text.enabled
        else "disabled"
    )
    text_service = TextEmotionService(
        GlmTextEmotionProvider(
            GlmTextConfig(
                base_url=text.base_url,
                api_key=text_api_key,
                model=text.model,
                timeout_seconds=text.timeout_seconds,
                max_retries=text.max_retries,
            ),
            HttpxJsonClient(),
            prompt=text.prompt_path.read_text(encoding="utf-8"),
        ),
        TextEmotionServiceConfig(
            enabled=text.enabled,
            provider_timeout_seconds=text.timeout_seconds,
            prompt_version=text.prompt_version,
        ),
    )
    return EmotionDebugPipeline(
        camera=camera,
        quality_evaluator=evaluator,
        video_preprocessor=preprocessor,
        video_service=video_service,
        text_service=text_service,
        fusion_service=EmotionFusionService(config.fusion),
        media_cleaner=TurnMediaCleaner(runtime_root, retain_media=False),
        trace_store=DebugTraceStore(debug_output),
    )


def main() -> int:
    args = parse_args()
    try:
        load_project_environment(REPOSITORY_ROOT)
        config = load_app_config(args.config.resolve(), repository_root=REPOSITORY_ROOT)
        if not config.camera.enabled:
            raise ConfigError("camera is disabled in the local configuration")
        camera = CameraBuffer(
            CameraBufferConfig(
                device_index=config.camera.device_index,
                width=config.camera.width,
                height=config.camera.height,
                target_fps=config.camera.target_fps,
                buffer_seconds=config.camera.buffer_seconds,
            )
        )
        evaluator = FaceQualityEvaluator(
            OpenCVFaceDetector(),
            FaceQualityConfig(sufficient_quality=config.video_emotion.minimum_quality),
        )
        analyzer = None
        unavailable_reason = None
        try:
            analyzer = build_analyzer(
                config,
                camera=camera,
                evaluator=evaluator,
                debug_output=args.debug_output.resolve(),
            )
        except ConfigError as exc:
            unavailable_reason = str(exc)
        application = CameraPreviewApplication(
            camera,
            evaluator,
            analyzer=analyzer,
            analysis_unavailable_reason=unavailable_reason,
        )
        print(
            json.dumps(
                {
                    "debug_output_root": str(args.debug_output.resolve()),
                    "video_provider_enabled": config.video_emotion.enabled,
                    "text_provider_enabled": config.text_emotion.enabled,
                    "audio_included": False,
                    "raw_media_retained": False,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        camera.start()
        try:
            run_camera_preview(application, port=args.port)
        finally:
            camera.stop()
        return 0
    except (ConfigError, CameraUnavailableError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
