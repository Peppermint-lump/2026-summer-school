from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.start_open_llm_vtuber import prepare_vtuber_config


class VtuberEnvironmentConfigTests(unittest.TestCase):
    def test_writes_secret_references_instead_of_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "conf.yaml"
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "system_config": {"host": "0.0.0.0", "port": 12393},
                        "character_config": {
                            "live2d_model_name": "legacy",
                            "agent_config": {
                                "agent_settings": {
                                    "basic_memory_agent": {"llm_provider": "ollama_llm"}
                                },
                                "llm_configs": {
                                    "zhipu_llm": {
                                        "llm_api_key": "old-placeholder",
                                        "model": "old-model",
                                    }
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            secret = "a-real-secret-that-must-not-be-written"

            prepare_vtuber_config(
                root,
                {
                    "GLM_API_KEY": secret,
                    "GLM_BASE_URL": "https://glm.example/v4",
                    "GLM_COMPANION_MODEL": "glm-test",
                    "VTUBER_LLM_PROVIDER": "zhipu_llm",
                    "LIVE2D_DEFAULT_MODEL": "xiaohudie",
                },
            )

            content = config_path.read_text(encoding="utf-8")
            self.assertNotIn(secret, content)
            self.assertIn("${GLM_API_KEY}", content)
            self.assertIn("${GLM_BASE_URL}", content)
            self.assertIn("${GLM_COMPANION_MODEL}", content)
            self.assertIn("${LIVE2D_DEFAULT_MODEL}", content)
            loaded = yaml.safe_load(content)
            self.assertEqual(loaded["system_config"]["host"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
