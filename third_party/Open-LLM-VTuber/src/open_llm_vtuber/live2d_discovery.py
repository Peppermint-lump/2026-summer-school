"""Discover registered Live2D runtime models without assuming a flat layout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


class Live2DCharacterInfo(TypedDict):
    name: str
    avatar: str | None
    model_path: str


def discover_live2d_characters(
    live2d_dir: Path,
    model_dict_path: Path,
) -> list[Live2DCharacterInfo]:
    """Return models whose registered or legacy model3 file exists locally."""
    root = live2d_dir.resolve()
    if not root.is_dir():
        return []

    registry = _load_registry(model_dict_path)
    characters: list[Live2DCharacterInfo] = []
    for model_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if not model_dir.is_dir():
            continue
        model_path = _registered_model_path(
            root,
            model_dir.name,
            registry.get(model_dir.name),
        )
        if model_path is None:
            legacy_path = model_dir / f"{model_dir.name}.model3.json"
            model_path = legacy_path if legacy_path.is_file() else None
        if model_path is None:
            continue

        avatar_path = next(
            (
                candidate
                for extension in (".png", ".jpg", ".jpeg")
                if (candidate := model_dir / f"{model_dir.name}{extension}").is_file()
            ),
            None,
        )
        characters.append(
            {
                "name": model_dir.name,
                "avatar": _response_path(root, avatar_path) if avatar_path else None,
                "model_path": _response_path(root, model_path),
            }
        )
    return characters


def _load_registry(model_dict_path: Path) -> dict[str, str]:
    try:
        raw_registry = json.loads(model_dict_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_registry, list):
        return {}
    return {
        item["name"]: item["url"]
        for item in raw_registry
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("url"), str)
    }


def _registered_model_path(
    root: Path,
    model_name: str,
    registered_url: str | None,
) -> Path | None:
    if not registered_url:
        return None
    relative_url = registered_url.lstrip("/")
    expected_prefix = f"{root.name}/{model_name}/"
    if not relative_url.startswith(expected_prefix):
        return None
    candidate = (root.parent / relative_url).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _response_path(root: Path, path: Path) -> str:
    return (Path(root.name) / path.resolve().relative_to(root)).as_posix()
