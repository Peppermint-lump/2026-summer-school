from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "Open-LLM-VTuber" / "src"))

from open_llm_vtuber.agent.transformers import actions_extractor  # noqa: E402
from open_llm_vtuber.utils.sentence_divider import SentenceWithTags  # noqa: E402


class FakeLive2dModel:
    def extract_emotion(self, text: str) -> list[int]:
        return [5, 4]


class ExpressionActionLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_first_expression_is_dispatched(self) -> None:
        @actions_extractor(FakeLive2dModel())
        async def sentence_stream():
            yield SentenceWithTags(text="[heart][star] hello", tags=[])

        results = [item async for item in sentence_stream()]

        self.assertEqual(len(results), 1)
        _, actions = results[0]
        self.assertEqual(actions.expressions, [5])


if __name__ == "__main__":
    unittest.main()
