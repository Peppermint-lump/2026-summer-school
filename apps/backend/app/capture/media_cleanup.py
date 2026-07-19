"""Recoverable, application-owned per-turn media cleanup."""

from __future__ import annotations

import shutil
from pathlib import Path


class UnsafeMediaPathError(ValueError):
    """Raised when cleanup is requested outside the configured runtime root."""


class TurnMediaCleaner:
    def __init__(self, runtime_root: Path, *, retain_media: bool = False) -> None:
        self._runtime_root = runtime_root.resolve()
        self._turns_root = self._runtime_root / "turns"
        self._retain_media = retain_media

    def cleanup_turn(self, turn_id: str) -> bool:
        if self._retain_media:
            return False
        target = (self._turns_root / turn_id).resolve()
        try:
            target.relative_to(self._turns_root.resolve())
        except ValueError as exc:
            raise UnsafeMediaPathError("turn path escapes runtime root") from exc
        if target == self._turns_root.resolve():
            raise UnsafeMediaPathError("refusing to remove turns root")
        if not target.exists():
            return False
        shutil.rmtree(target)
        return True
