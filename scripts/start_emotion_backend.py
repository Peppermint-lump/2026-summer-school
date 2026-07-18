"""Start the authenticated canonical emotion middleware on loopback."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from apps.backend.app.infrastructure.config import ConfigError, load_app_config
from apps.backend.app.infrastructure.environment import load_project_environment
from apps.backend.app.integration.loopback_server import LoopbackEmotionServer
from apps.backend.app.integration.runtime_factory import build_emotion_runtime

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=REPOSITORY_ROOT / "configs" / "app.local.yaml",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument(
        "--token-env",
        default="EMOTION_BACKEND_TOKEN",
        help="environment variable containing the ephemeral loopback token",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_project_environment(REPOSITORY_ROOT)
        token = os.environ.get(args.token_env, "")
        if not token:
            raise ConfigError(f"missing ephemeral token in {args.token_env}")
        config = load_app_config(
            args.config.resolve(),
            repository_root=REPOSITORY_ROOT,
        )
        runtime = build_emotion_runtime(config, repository_root=REPOSITORY_ROOT)
        server = LoopbackEmotionServer(
            host=args.host,
            port=args.port,
            token=token,
            runtime=runtime,
            runtime_root=REPOSITORY_ROOT / "runtime",
            debug_output_root=(REPOSITORY_ROOT / "runtime" / "debug" / "emotion_turns"),
            continuous_visual_enabled=config.video_emotion.continuous_enabled,
            continuous_visual_window_seconds=(
                config.video_emotion.continuous_window_seconds
            ),
            continuous_visual_interval_seconds=(
                config.video_emotion.continuous_interval_seconds
            ),
        )
        print(
            "emotion backend ready "
            f"host={args.host} port={server.port} "
            f"camera_enabled={runtime.camera_enabled} "
            f"continuous_visual={config.video_emotion.continuous_enabled}",
            flush=True,
        )
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except (ConfigError, OSError, ValueError) as exc:
        print(f"emotion backend configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
