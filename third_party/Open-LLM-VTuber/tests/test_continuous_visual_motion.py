from __future__ import annotations

import unittest

from src.open_llm_vtuber.websocket_handler import (
    _cooldown_motion,
    _visual_expression_index,
)


class ContinuousVisualMotionTests(unittest.TestCase):
    def test_active_conversation_suppresses_only_visual_expression(self) -> None:
        self.assertIsNone(_visual_expression_index([5], conversation_active=True))
        self.assertEqual(
            _visual_expression_index([5], conversation_active=False),
            5,
        )

    def test_repeated_greeting_is_suppressed_during_cooldown(self) -> None:
        motion, previous, emitted = _cooldown_motion(
            "greeting",
            now=10.0,
            previous_event_motion=None,
            last_emitted_at={},
            cooldown_seconds=5,
        )
        self.assertEqual(
            (motion, previous, emitted), ("greeting", "greeting", {"greeting": 10.0})
        )

        motion, previous, emitted = _cooldown_motion(
            "greeting",
            now=12.0,
            previous_event_motion=previous,
            last_emitted_at=emitted,
            cooldown_seconds=5,
        )
        self.assertEqual((motion, previous), ("idle", "greeting"))

        motion, previous, emitted = _cooldown_motion(
            "idle",
            now=13.0,
            previous_event_motion=previous,
            last_emitted_at=emitted,
            cooldown_seconds=5,
        )
        self.assertEqual((motion, previous), ("idle", None))

        motion, previous, emitted = _cooldown_motion(
            "greeting",
            now=15.0,
            previous_event_motion=previous,
            last_emitted_at=emitted,
            cooldown_seconds=5,
        )
        self.assertEqual(
            (motion, previous, emitted), ("greeting", "greeting", {"greeting": 15.0})
        )

    def test_observe_is_edge_triggered_and_does_not_block_greeting(self) -> None:
        motion, previous, emitted = _cooldown_motion(
            "observe",
            now=2.0,
            previous_event_motion=None,
            last_emitted_at={},
            cooldown_seconds=5,
        )
        self.assertEqual((motion, previous), ("observe", "observe"))

        motion, previous, emitted = _cooldown_motion(
            "observe",
            now=8.0,
            previous_event_motion=previous,
            last_emitted_at=emitted,
            cooldown_seconds=5,
        )
        self.assertEqual((motion, previous), ("idle", "observe"))

        motion, previous, emitted = _cooldown_motion(
            "greeting",
            now=8.1,
            previous_event_motion=previous,
            last_emitted_at=emitted,
            cooldown_seconds=5,
        )
        self.assertEqual((motion, previous), ("greeting", "greeting"))


if __name__ == "__main__":
    unittest.main()
