from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SRC = ROOT / "third_party" / "Open-LLM-VTuber" / "src"
sys.path.insert(0, str(UPSTREAM_SRC))

from open_llm_vtuber.live2d_discovery import (  # noqa: E402
    discover_live2d_characters,
)


class Live2DModelDiscoveryTests(unittest.TestCase):
    def test_registered_nested_runtime_models_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models = root / "live2d-models"
            xiaohudie = models / "xiaohudie" / "runtime"
            felix = models / "felix" / "runtime"
            xiaohudie.mkdir(parents=True)
            felix.mkdir(parents=True)
            (xiaohudie / "xiaohudie.model3.json").write_text("{}")
            (felix / "wd66.model3.json").write_text("{}")
            registry = root / "model_dict.json"
            registry.write_text(
                json.dumps(
                    [
                        {
                            "name": "xiaohudie",
                            "url": (
                                "/live2d-models/xiaohudie/runtime/xiaohudie.model3.json"
                            ),
                        },
                        {
                            "name": "felix",
                            "url": "/live2d-models/felix/runtime/wd66.model3.json",
                        },
                    ]
                )
            )

            discovered = discover_live2d_characters(models, registry)

            self.assertEqual(
                [item["name"] for item in discovered], ["felix", "xiaohudie"]
            )
            self.assertEqual(
                discovered[0]["model_path"],
                "live2d-models/felix/runtime/wd66.model3.json",
            )

    def test_registry_cannot_escape_live2d_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "live2d-models" / "unsafe"
            model_dir.mkdir(parents=True)
            outside = root / "outside.model3.json"
            outside.write_text("{}")
            registry = root / "model_dict.json"
            registry.write_text(
                json.dumps(
                    [
                        {
                            "name": "unsafe",
                            "url": "/live2d-models/unsafe/../../outside.model3.json",
                        }
                    ]
                )
            )

            self.assertEqual(
                discover_live2d_characters(root / "live2d-models", registry), []
            )

    def test_legacy_flat_layout_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_dir = root / "live2d-models" / "legacy"
            model_dir.mkdir(parents=True)
            (model_dir / "legacy.model3.json").write_text("{}")

            discovered = discover_live2d_characters(
                root / "live2d-models",
                root / "missing-model-dict.json",
            )

            self.assertEqual(discovered[0]["name"], "legacy")


if __name__ == "__main__":
    unittest.main()
