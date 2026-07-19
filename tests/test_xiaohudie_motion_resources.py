from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOTIONS = (
    ROOT
    / "third_party"
    / "Open-LLM-VTuber"
    / "live2d-models"
    / "xiaohudie"
    / "runtime"
    / "motions"
)
ORIGINAL_MOTIONS = ROOT / "【VTS用】2.0小蝴蝶运行文件" / "2.0小蝴蝶"
ORIGINAL_NAMES = {
    "greeting.motion3.json": "打招呼5秒动画Scene1.motion3.json",
    "catch_butterfly.motion3.json": "接蝴蝶6秒动画Scene1.motion3.json",
    "hold_bear.motion3.json": "3秒接熊动画Scene1.motion3.json",
}


class XiaohudieMotionResourceTests(unittest.TestCase):
    def test_special_motions_are_one_shot(self) -> None:
        for name in (
            "greeting.motion3.json",
            "catch_butterfly.motion3.json",
            "hold_bear.motion3.json",
        ):
            motion = json.loads((MOTIONS / name).read_text(encoding="utf-8"))
            self.assertFalse(motion["Meta"]["Loop"])

    def test_idle_does_not_cover_special_motion_targets(self) -> None:
        idle = json.loads(
            (MOTIONS / "idle.motion3.json").read_text(encoding="utf-8")
        )
        idle_targets = {
            (curve["Target"], curve["Id"]) for curve in idle["Curves"]
        }

        for name in (
            "greeting.motion3.json",
            "catch_butterfly.motion3.json",
            "hold_bear.motion3.json",
        ):
            motion = json.loads((MOTIONS / name).read_text(encoding="utf-8"))
            special_targets = {
                (curve["Target"], curve["Id"]) for curve in motion["Curves"]
            }
            self.assertTrue(special_targets.isdisjoint(idle_targets))

    def test_special_motions_only_contain_parameter_curves(self) -> None:
        for name in (
            "greeting.motion3.json",
            "catch_butterfly.motion3.json",
            "hold_bear.motion3.json",
        ):
            motion = json.loads((MOTIONS / name).read_text(encoding="utf-8"))
            self.assertEqual(
                {curve["Target"] for curve in motion["Curves"]}, {"Parameter"}
            )

    def test_runtime_curves_match_original_assets(self) -> None:
        for runtime_name, original_name in ORIGINAL_NAMES.items():
            runtime = json.loads((MOTIONS / runtime_name).read_text(encoding="utf-8"))
            original = json.loads(
                (ORIGINAL_MOTIONS / original_name).read_text(encoding="utf-8-sig")
            )
            runtime["Meta"]["Loop"] = original["Meta"]["Loop"]
            self.assertEqual(runtime, original)


if __name__ == "__main__":
    unittest.main()
