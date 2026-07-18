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
from apps.backend.app.debug.camera_preview import (
    CameraPreviewApplication,
    run_camera_preview,
)
from apps.backend.app.emotion.video.face_quality import (
    FaceQualityConfig,
    FaceQualityEvaluator,
    OpenCVFaceDetector,
)
from apps.backend.app.infrastructure.config import ConfigError, load_app_config
from apps.backend.app.infrastructure.environment import load_project_environment

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT / "configs" / "app.local.yaml",
    )
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


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
        application = CameraPreviewApplication(
            camera,
            FaceQualityEvaluator(
                OpenCVFaceDetector(),
                FaceQualityConfig(
                    sufficient_quality=config.video_emotion.minimum_quality
                ),
            ),
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
