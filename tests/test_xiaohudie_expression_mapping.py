import asyncio
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "third_party" / "Open-LLM-VTuber"
sys.path.insert(0, str(UPSTREAM))

from src.open_llm_vtuber.agent.transformers import actions_extractor  # noqa: E402
from src.open_llm_vtuber.live2d_model import Live2dModel  # noqa: E402
from src.open_llm_vtuber.utils.sentence_divider import (  # noqa: E402
    SentenceWithTags,
)


class XiaohudieExpressionMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.model = Live2dModel("xiaohudie", str(UPSTREAM / "model_dict.json"))

    def test_joy_aliases_the_registered_star_expression(self) -> None:
        self.assertEqual(self.model.extract_emotion("[joy] 太好了"), [4])
        self.assertEqual(self.model.extract_emotion("[star] 太好了"), [4])
        self.assertEqual(self.model.remove_emotion_keywords("[joy] 太好了"), " 太好了")

    def test_blackening_expression_is_not_exposed_as_joy(self) -> None:
        self.assertNotIn(3, self.model.emo_map.values())
        self.assertEqual(self.model.extract_emotion("[blackening] test"), [])

    def test_action_extractor_dispatches_joy(self) -> None:
        async def sentence_stream():
            yield SentenceWithTags(text="[joy] 太好了", tags=[])

        async def collect_actions():
            decorated = actions_extractor(self.model)(sentence_stream)
            return [item async for item in decorated()]

        output = asyncio.run(collect_actions())
        _, actions = output[0]
        self.assertEqual(actions.expressions, [4])


if __name__ == "__main__":
    unittest.main()
