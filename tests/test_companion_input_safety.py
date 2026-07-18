from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SRC = ROOT / "third_party" / "Open-LLM-VTuber" / "src"
sys.path.insert(0, str(UPSTREAM_SRC))

from open_llm_vtuber.companion_input_safety import (  # noqa: E402
    RAW_VISUAL_INPUT_NOTICE,
    add_visual_unavailable_context,
    discard_raw_companion_images,
)


class CompanionInputSafetyTests(unittest.TestCase):
    def test_raw_images_are_discarded_and_turn_is_marked(self) -> None:
        images = [
            {
                "source": "camera",
                "data": "data:image/jpeg;base64,sensitive",
                "mime_type": "image/jpeg",
            }
        ]

        safe_images, metadata, discarded_count = discard_raw_companion_images(
            images, {"existing": True}
        )

        self.assertIsNone(safe_images)
        self.assertEqual(discarded_count, 1)
        self.assertEqual(
            metadata, {"existing": True, "raw_images_discarded": True}
        )

    def test_visual_guardrail_is_added_only_for_discarded_images(self) -> None:
        guarded = add_visual_unavailable_context(
            "你能看见我吗？", {"raw_images_discarded": True}
        )

        self.assertIn("你能看见我吗？", guarded)
        self.assertIn(RAW_VISUAL_INPUT_NOTICE, guarded)
        self.assertNotIn("base64", guarded)
        self.assertEqual(
            add_visual_unavailable_context("普通文字", None), "普通文字"
        )

    def test_empty_image_list_keeps_existing_metadata(self) -> None:
        metadata = {"skip_history": True}

        safe_images, safe_metadata, discarded_count = discard_raw_companion_images(
            [], metadata
        )

        self.assertIsNone(safe_images)
        self.assertIs(safe_metadata, metadata)
        self.assertEqual(discarded_count, 0)


if __name__ == "__main__":
    unittest.main()
