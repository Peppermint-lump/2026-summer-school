"""Load validated application configuration and resolve secrets at the edge."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from packages.schemas import AppConfig, CameraCaptureConfig, VideoAnalysisConfig


class ConfigError(ValueError):
    """Raised when local application configuration is missing or invalid."""


class EnvironmentSecretStore:
    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = os.environ if environment is None else environment

    def get_required(self, name: str) -> str:
        value = self._environment.get(name)
        if not value:
            raise ConfigError(
                f"required secret environment variable is missing: {name}"
            )
        return value


def load_app_config(
    path: Path,
    *,
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
) -> AppConfig:
    effective_environment = os.environ if environment is None else environment
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"configuration file cannot be read: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError("configuration file is not valid YAML") from exc
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be a mapping")

    root = cast(dict[str, Any], raw)
    capture = _mapping(root, "capture")
    camera = _mapping(capture, "camera")
    emotion = _mapping(root, "emotion")
    video = _mapping(emotion, "video")
    prompt_path = (repository_root / _string(video, "prompt_path")).resolve()
    try:
        prompt_path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ConfigError("video prompt_path escapes the repository") from exc
    if not prompt_path.is_file():
        raise ConfigError("configured video prompt does not exist")

    try:
        return AppConfig(
            camera=CameraCaptureConfig(
                enabled=_boolean(camera, "enabled"),
                device_index=_integer(camera, "device_index"),
                width=_integer(camera, "width"),
                height=_integer(camera, "height"),
                target_fps=_number(camera, "target_fps"),
                buffer_seconds=_number(camera, "buffer_seconds"),
                sample_fps=_number(camera, "sample_fps"),
                max_sampled_frames=_integer(camera, "max_sampled_frames"),
                retain_media=_boolean(camera, "retain_media"),
            ),
            video_emotion=VideoAnalysisConfig(
                enabled=_environment_boolean(
                    effective_environment,
                    "VIDEO_EMOTION_ENABLED",
                    default=_boolean(video, "enabled"),
                ),
                provider=_environment_string(
                    effective_environment,
                    "VIDEO_EMOTION_PROVIDER",
                    default=_string(video, "provider"),
                ),
                model=_environment_string(
                    effective_environment,
                    "MIMO_MODEL",
                    default=_string(video, "model"),
                ),
                base_url=_environment_string(
                    effective_environment,
                    "MIMO_BASE_URL",
                    default=_string(video, "base_url"),
                ),
                api_key_secret_name=_string(video, "api_key_secret_name"),
                timeout_seconds=_number(video, "timeout_seconds"),
                max_retries=_integer(video, "max_retries"),
                prompt_path=prompt_path,
                prompt_version=_string(video, "prompt_version"),
                minimum_quality=_number(video, "minimum_quality"),
            ),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _mapping(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise ConfigError(f"configuration '{key}' must be a mapping")
    return cast(dict[str, Any], child)


def _string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ConfigError(f"configuration '{key}' must be a non-empty string")
    return result


def _boolean(value: Mapping[str, Any], key: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise ConfigError(f"configuration '{key}' must be a boolean")
    return result


def _integer(value: Mapping[str, Any], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ConfigError(f"configuration '{key}' must be an integer")
    return result


def _number(value: Mapping[str, Any], key: str) -> float:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ConfigError(f"configuration '{key}' must be a number")
    return float(result)


def _environment_string(
    environment: Mapping[str, str], key: str, *, default: str
) -> str:
    result = environment.get(key, default).strip()
    if not result:
        raise ConfigError(f"environment variable '{key}' must be non-empty")
    return result


def _environment_boolean(
    environment: Mapping[str, str], key: str, *, default: bool
) -> bool:
    raw_value = environment.get(key)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"environment variable '{key}' must be a boolean")
