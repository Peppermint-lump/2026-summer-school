"""Load local environment files without evaluating shell expressions."""

from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path


class DotEnvError(ValueError):
    """Raised when a local environment file is malformed."""


_ENVIRONMENT_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")


def load_project_environment(
    repository_root: Path,
    *,
    environment: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> bool:
    """Load the ignored repository-root ``.env`` file when it exists."""
    return load_dotenv_file(
        repository_root / ".env",
        environment=environment,
        override=override,
        required=False,
    )


def load_dotenv_file(
    path: Path,
    *,
    environment: MutableMapping[str, str] | None = None,
    override: bool = False,
    required: bool = True,
) -> bool:
    """Load simple KEY=VALUE pairs while preserving existing process values."""
    target = os.environ if environment is None else environment
    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        if required:
            raise DotEnvError(f"environment file does not exist: {path}") from None
        return False
    except OSError as exc:
        raise DotEnvError(f"environment file cannot be read: {path}") from exc

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not _ENVIRONMENT_NAME.fullmatch(key):
            raise DotEnvError(f"invalid environment entry at {path}:{line_number}")
        value = _parse_value(raw_value.strip(), path=path, line_number=line_number)
        if override or key not in target:
            target[key] = value
    return True


def _parse_value(raw_value: str, *, path: Path, line_number: int) -> str:
    if not raw_value:
        return ""
    quote = raw_value[0]
    if quote not in {"'", '"'}:
        return raw_value.split(" #", maxsplit=1)[0].rstrip()
    if len(raw_value) < 2 or raw_value[-1] != quote:
        raise DotEnvError(f"unterminated quoted value at {path}:{line_number}")
    value = raw_value[1:-1]
    if quote == '"':
        value = (
            value.replace(r"\n", "\n")
            .replace(r"\r", "\r")
            .replace(r"\t", "\t")
            .replace(r"\"", '"')
            .replace(r"\\", "\\")
        )
    return value
