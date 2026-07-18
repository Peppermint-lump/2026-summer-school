"""Privacy-safe camera and opt-in provider smoke tests for the video pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from apps.backend.app.capture.camera_buffer import (
    CameraBuffer,
    CameraBufferConfig,
    CameraUnavailableError,
)
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.capture.video_export import FrameExportConfig, FrameExporter
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
from apps.backend.app.integration.video_emotion_middleware import (
    VideoEmotionMiddleware,
)
from packages.schemas import AppConfig, TurnRecord

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "configs" / "app.local.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("camera", "provider"),
        default="camera",
        help="camera keeps all frames in memory; provider performs one paid API call",
    )
    parser.add_argument(
        "--transcript",
        help=(
            "optional current-turn ASR text; provider mode then performs a second "
            "GLM call and prints deterministic text/video fusion"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="capture duration in seconds (1-15)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    return parser.parse_args()


def build_camera(config: AppConfig) -> CameraBuffer:
    camera = config.camera
    return CameraBuffer(
        CameraBufferConfig(
            device_index=camera.device_index,
            width=camera.width,
            height=camera.height,
            target_fps=camera.target_fps,
            buffer_seconds=camera.buffer_seconds,
        )
    )


def capture_turn(camera: CameraBuffer, duration: float) -> tuple[int, int]:
    if not 1.0 <= duration <= 15.0:
        raise ConfigError("duration must be between 1 and 15 seconds")
    camera.start()
    start_ms = time.time_ns() // 1_000_000
    try:
        time.sleep(duration)
        return start_ms, time.time_ns() // 1_000_000
    finally:
        camera.stop()


def run_camera_smoke(config: AppConfig, duration: float) -> int:
    if not config.camera.enabled:
        raise ConfigError("camera is disabled in the local configuration")
    camera = build_camera(config)
    start_ms, end_ms = capture_turn(camera, duration)
    frames = camera.frames_between(start_ms, end_ms)
    report = FaceQualityEvaluator(
        OpenCVFaceDetector(),
        FaceQualityConfig(sufficient_quality=config.video_emotion.minimum_quality),
    ).evaluate(frames)
    summary = asdict(report)
    summary["camera_state_after_test"] = camera.state.value
    summary["retained_media"] = False
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if frames else 2


async def run_provider_smoke(
    config: AppConfig, duration: float, transcript: str | None
) -> int:
    if not config.camera.enabled:
        raise ConfigError("camera is disabled in the local configuration")
    video = config.video_emotion
    if not video.enabled:
        raise ConfigError("video emotion is disabled in the local configuration")
    if "<" in video.base_url or not video.base_url.startswith("https://"):
        raise ConfigError("set the HTTPS MiMo base_url in configs/app.local.yaml")
    api_key = EnvironmentSecretStore().get_required(video.api_key_secret_name)
    camera = build_camera(config)
    start_ms, end_ms = capture_turn(camera, duration)
    runtime_root = REPOSITORY_ROOT / "runtime"
    preprocessor = VideoTurnPreprocessor(
        camera,
        FaceQualityEvaluator(
            OpenCVFaceDetector(),
            FaceQualityConfig(sufficient_quality=video.minimum_quality),
        ),
        FrameExporter(
            runtime_root,
            FrameExportConfig(
                sample_fps=config.camera.sample_fps,
                max_frames=config.camera.max_sampled_frames,
            ),
        ),
    )
    provider = MiMoVideoEmotionProvider(
        MiMoVideoConfig(
            base_url=video.base_url,
            api_key=api_key,
            model=video.model,
            timeout_seconds=video.timeout_seconds,
            max_retries=video.max_retries,
            max_frames=config.camera.max_sampled_frames,
        ),
        HttpxJsonClient(),
        prompt=video.prompt_path.read_text(encoding="utf-8"),
    )
    middleware = VideoEmotionMiddleware(
        preprocessor,
        VideoEmotionService(
            provider,
            VideoEmotionServiceConfig(
                enabled=True,
                provider_timeout_seconds=video.timeout_seconds,
                prompt_version=video.prompt_version,
                action_emotion=ActionEmotionConfig(
                    minimum_action_confidence=video.action_minimum_confidence,
                    maximum_action_weight=video.action_emotion_weight,
                ),
            ),
        ),
        TurnMediaCleaner(runtime_root, retain_media=config.camera.retain_media),
        camera_enabled=True,
    )
    result = await middleware.analyze_turn(
        TurnRecord(
            session_id="debug_session",
            turn_id=f"debug_{start_ms}",
            speech_start_ms=start_ms,
            speech_end_ms=end_ms,
        )
    )
    output: dict[str, object] = {
        "video": {
            "modality": result.modality.value,
            "label": result.label.value,
            "fine_emotion": result.fine_emotion,
            "confidence": result.confidence,
            "quality": result.quality,
            "reliability": result.reliability,
            "status": result.status.value,
            "evidence": result.evidence,
            "observed_actions": [
                {
                    "type": action.action.value,
                    "confidence": action.confidence,
                    "evidence": action.evidence,
                }
                for action in result.observed_actions
            ],
        },
        "retained_media": config.camera.retain_media,
    }
    if transcript is not None:
        text = config.text_emotion
        if not text.enabled:
            raise ConfigError("text emotion is disabled in the local configuration")
        text_api_key = EnvironmentSecretStore().get_required(text.api_key_secret_name)
        text_result = await TextEmotionService(
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
                enabled=True,
                provider_timeout_seconds=text.timeout_seconds,
                prompt_version=text.prompt_version,
            ),
        ).analyze(turn_id=f"debug_{start_ms}", transcript=transcript)
        fusion = EmotionFusionService(config.fusion).fuse((text_result, result))
        output["text"] = {
            "label": text_result.label.value,
            "confidence": text_result.confidence,
            "quality": text_result.quality,
            "reliability": text_result.reliability,
            "status": text_result.status.value,
            "evidence": text_result.evidence,
        }
        output["fusion"] = {
            "final_emotion": fusion.fused_label.value,
            "weighted_score": fusion.weighted_score,
            "conflict_type": fusion.conflict_type.value,
            "conflict_score": fusion.conflict_score,
            "reliable_modalities": [
                modality.value for modality in fusion.reliable_modalities
            ],
            "strategy": fusion.strategy.value,
            "explanation": fusion.explanation,
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result.status.value in {"ok", "uncertain"} else 2


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        load_project_environment(REPOSITORY_ROOT)
        config = load_app_config(args.config.resolve(), repository_root=REPOSITORY_ROOT)
        if args.mode == "camera":
            return run_camera_smoke(config, args.duration)
        return asyncio.run(run_provider_smoke(config, args.duration, args.transcript))
    except (ConfigError, CameraUnavailableError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
