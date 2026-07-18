"""Privacy-safe, per-turn structured traces for the emotion debug pipeline."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class DebugTraceStore:
    """Write metadata-only JSON stages below an application-owned directory."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.resolve()

    def turn_directory(self, turn_id: str) -> Path:
        safe_turn_id = _validate_turn_id(turn_id)
        target = (self.output_root / safe_turn_id).resolve()
        try:
            target.relative_to(self.output_root)
        except ValueError as exc:
            raise ValueError("debug trace path escapes output root") from exc
        return target

    def write_stage(
        self,
        turn_id: str,
        filename: str,
        payload: Mapping[str, Any],
    ) -> Path:
        if not filename.endswith(".json") or "/" in filename or "\\" in filename:
            raise ValueError("debug stage filename must be a plain JSON filename")
        turn_directory = self.turn_directory(turn_id)
        turn_directory.mkdir(parents=True, exist_ok=True)
        target = turn_directory / filename
        temporary = turn_directory / f".{filename}.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target


def _validate_turn_id(turn_id: str) -> str:
    if not turn_id or turn_id in {".", ".."}:
        raise ValueError("turn_id must be non-empty")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if any(character not in allowed for character in turn_id):
        raise ValueError("turn_id contains unsafe path characters")
    return turn_id
