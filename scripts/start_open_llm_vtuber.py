"""Configure and start Open-LLM-VTuber from the repository-root .env file."""

from __future__ import annotations

import argparse
import os
import runpy
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any, cast

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ROOT = REPOSITORY_ROOT / "third_party" / "Open-LLM-VTuber"
_environment_module = runpy.run_path(
    str(
        REPOSITORY_ROOT
        / "apps"
        / "backend"
        / "app"
        / "infrastructure"
        / "environment.py"
    )
)
DotEnvError = cast(type[ValueError], _environment_module["DotEnvError"])
load_project_environment = cast(
    Callable[..., bool], _environment_module["load_project_environment"]
)


class VtuberConfigurationError(ValueError):
    """Raised when the safe VTuber environment contract is incomplete."""


def prepare_emotion_config(repository_root: Path) -> Path:
    """Create the ignored local emotion config once from the safe example."""
    config_directory = repository_root / "configs"
    local_path = config_directory / "app.local.yaml"
    if local_path.exists():
        return local_path

    example_path = config_directory / "app.example.yaml"
    if not example_path.is_file():
        raise VtuberConfigurationError(
            "emotion configuration template is missing: configs/app.example.yaml"
        )
    try:
        shutil.copyfile(example_path, local_path)
    except OSError as exc:
        raise VtuberConfigurationError(
            "emotion configuration could not be initialized"
        ) from exc
    return local_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate .env and prepare conf.yaml without starting the server",
    )
    parser.add_argument("--emotion-port", type=int, default=18765)
    return parser.parse_args()


def prepare_vtuber_config(
    upstream_root: Path,
    environment: MutableMapping[str, str],
) -> Path:
    """Prepare the ignored upstream config from env or an existing local config."""
    required = (
        "GLM_API_KEY",
        "GLM_BASE_URL",
        "GLM_COMPANION_MODEL",
        "VTUBER_LLM_PROVIDER",
        "LIVE2D_DEFAULT_MODEL",
    )
    use_environment_config = any(
        environment.get(name, "").strip() for name in required
    )
    if use_environment_config:
        missing = [
            name for name in required if not environment.get(name, "").strip()
        ]
        if missing:
            raise VtuberConfigurationError(
                "fill the following variables in .env: " + ", ".join(missing)
            )
        if environment["VTUBER_LLM_PROVIDER"] != "zhipu_llm":
            raise VtuberConfigurationError(
                "VTUBER_LLM_PROVIDER must remain zhipu_llm for the SSOT GLM binding"
            )

    config_path = upstream_root / "conf.yaml"
    if not config_path.exists():
        template_path = upstream_root / "config_templates" / "conf.default.yaml"
        try:
            shutil.copyfile(template_path, config_path)
        except OSError as exc:
            raise VtuberConfigurationError(
                "Open-LLM-VTuber configuration could not be created"
            ) from exc
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise VtuberConfigurationError(
            "Open-LLM-VTuber configuration could not be read"
        ) from exc
    if not isinstance(loaded, dict):
        raise VtuberConfigurationError("Open-LLM-VTuber config root must be a mapping")
    config = cast(dict[str, Any], loaded)

    system = _mapping(config, "system_config")
    system["host"] = "127.0.0.1"
    character = _mapping(config, "character_config")
    agent = _mapping(character, "agent_config")
    settings = _mapping(_mapping(agent, "agent_settings"), "basic_memory_agent")
    llm_configs = _mapping(agent, "llm_configs")
    zhipu = _mapping(llm_configs, "zhipu_llm")
    if use_environment_config:
        character["live2d_model_name"] = "${LIVE2D_DEFAULT_MODEL}"
        settings["llm_provider"] = "${VTUBER_LLM_PROVIDER}"
        zhipu.update(
            {
                "base_url": "${GLM_BASE_URL}",
                "llm_api_key": "${GLM_API_KEY}",
                "model": "${GLM_COMPANION_MODEL}",
            }
        )
    else:
        _validate_existing_vtuber_config(character, settings, zhipu)

    try:
        config_path.write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise VtuberConfigurationError(
            "Open-LLM-VTuber configuration could not be updated"
        ) from exc
    return config_path


def _validate_existing_vtuber_config(
    character: dict[str, Any],
    settings: dict[str, Any],
    zhipu: dict[str, Any],
) -> None:
    """Validate legacy ignored conf.yaml values without exposing credentials."""
    provider = settings.get("llm_provider")
    if provider != "zhipu_llm":
        raise VtuberConfigurationError(
            "conf.yaml basic_memory_agent.llm_provider must remain zhipu_llm"
        )

    required_fields = {
        "character_config.live2d_model_name": character.get("live2d_model_name"),
        "zhipu_llm.llm_api_key": zhipu.get("llm_api_key"),
        "zhipu_llm.model": zhipu.get("model"),
    }
    missing = [
        name
        for name, value in required_fields.items()
        if not isinstance(value, str)
        or not value.strip()
        or value.strip().startswith("${")
    ]
    if missing:
        raise VtuberConfigurationError(
            "configure these values in conf.yaml or provide the complete .env "
            "contract: "
            + ", ".join(missing)
        )


def _mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise VtuberConfigurationError(f"Open-LLM-VTuber config '{key}' is invalid")
    return cast(dict[str, Any], value)


def _root_python() -> Path:
    candidates = (
        REPOSITORY_ROOT / ".venv" / "bin" / "python",
        REPOSITORY_ROOT / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise VtuberConfigurationError(
        "root .venv Python is missing; create the project environment first"
    )


def start_emotion_backend(port: int) -> subprocess.Popen[bytes]:
    """Start the Python 3.11+ canonical middleware before the upstream server."""
    token = secrets.token_urlsafe(32)
    os.environ["EMOTION_BACKEND_TOKEN"] = token
    os.environ["EMOTION_BACKEND_URL"] = f"http://127.0.0.1:{port}"
    config_path = prepare_emotion_config(REPOSITORY_ROOT)
    process = subprocess.Popen(
        [
            str(_root_python()),
            str(REPOSITORY_ROOT / "scripts" / "start_emotion_backend.py"),
            "--config",
            str(config_path),
            "--port",
            str(port),
        ],
        cwd=REPOSITORY_ROOT,
        env=os.environ.copy(),
    )
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise VtuberConfigurationError(
                f"emotion backend exited with code {process.returncode}"
            )
        try:
            with urllib.request.urlopen(request, timeout=0.5) as response:
                if response.status == 200:
                    return process
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    process.terminate()
    process.wait(timeout=5)
    raise VtuberConfigurationError("emotion backend startup timed out")


def stop_emotion_backend(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    args = parse_args()
    emotion_backend: subprocess.Popen[bytes] | None = None
    try:
        load_project_environment(REPOSITORY_ROOT)
        prepare_vtuber_config(UPSTREAM_ROOT, os.environ)
        prepare_emotion_config(REPOSITORY_ROOT)
    except (DotEnvError, VtuberConfigurationError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    if args.check_only:
        print("Open-LLM-VTuber environment configuration is valid")
        return 0

    try:
        emotion_backend = start_emotion_backend(args.emotion_port)
        os.chdir(UPSTREAM_ROOT)
        sys.path.insert(0, str(UPSTREAM_ROOT))
        sys.argv = [str(UPSTREAM_ROOT / "run_server.py")]
        if args.verbose:
            sys.argv.append("--verbose")
        runpy.run_path(str(UPSTREAM_ROOT / "run_server.py"), run_name="__main__")
        return 0
    except VtuberConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    finally:
        stop_emotion_backend(emotion_backend)


if __name__ == "__main__":
    raise SystemExit(main())
