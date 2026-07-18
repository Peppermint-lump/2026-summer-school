from __future__ import annotations

import unittest

from src.open_llm_vtuber.websocket_handler import _cooldown_motion


class ContinuousVisualMotionTests(unittest.TestCase):
    def test_repeated_greeting_is_suppressed_during_cooldown(self) -> None:
        motion, last = _cooldown_motion(
            "greeting", now=10.0, last_greeting_at=float("-inf"), cooldown_seconds=5
        )
        self.assertEqual((motion, last), ("greeting", 10.0))

        motion, last = _cooldown_motion(
            "greeting", now=12.0, last_greeting_at=last, cooldown_seconds=5
        )
        self.assertEqual((motion, last), ("idle", 10.0))

        motion, last = _cooldown_motion(
            "greeting", now=15.0, last_greeting_at=last, cooldown_seconds=5
        )
        self.assertEqual((motion, last), ("greeting", 15.0))

    def test_non_greeting_motion_is_unchanged(self) -> None:
        self.assertEqual(
            _cooldown_motion(
                "idle", now=2.0, last_greeting_at=1.0, cooldown_seconds=5
            ),
            ("idle", 1.0),
        )


if __name__ == "__main__":
    unittest.main()
