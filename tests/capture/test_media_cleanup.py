from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.backend.app.capture.media_cleanup import (
    TurnMediaCleaner,
    UnsafeMediaPathError,
)


class MediaCleanupTests(unittest.TestCase):
    def test_default_cleanup_removes_only_the_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            turn = root / "turns" / "turn_1"
            turn.mkdir(parents=True)
            (turn / "frame.jpg").write_bytes(b"private")
            self.assertTrue(TurnMediaCleaner(root).cleanup_turn("turn_1"))
            self.assertFalse(turn.exists())
            self.assertTrue(root.exists())

    def test_retention_flag_preserves_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            turn = root / "turns" / "turn_1"
            turn.mkdir(parents=True)
            cleaner = TurnMediaCleaner(root, retain_media=True)
            self.assertFalse(cleaner.cleanup_turn("turn_1"))
            self.assertTrue(turn.exists())

    def test_cleanup_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UnsafeMediaPathError):
                TurnMediaCleaner(Path(temporary)).cleanup_turn("../../outside")


if __name__ == "__main__":
    unittest.main()
