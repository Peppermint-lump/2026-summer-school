from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.start_open_llm_vtuber import prepare_emotion_config, prepare_vtuber_config


class VtuberEnvironmentConfigTests(unittest.TestCase):
    def test_initializes_missing_local_emotion_config_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_directory = root / "configs"
            config_directory.mkdir()
            example = config_directory / "app.example.yaml"
            example.write_text("camera: disabled\n", encoding="utf-8")

            local = prepare_emotion_config(root)
            self.assertEqual(local.read_text(encoding="utf-8"), "camera: disabled\n")

            local.write_text("camera: enabled\n", encoding="utf-8")
            prepare_emotion_config(root)
            self.assertEqual(local.read_text(encoding="utf-8"), "camera: enabled\n")

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

    def test_preserves_complete_ignored_conf_when_env_contract_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "conf.yaml"
            secret = "local-config-secret"
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "system_config": {"host": "127.0.0.1", "port": 12393},
                        "character_config": {
                            "live2d_model_name": "xiaohudie",
                            "agent_config": {
                                "agent_settings": {
                                    "basic_memory_agent": {
                                        "llm_provider": "zhipu_llm"
                                    }
                                },
                                "llm_configs": {
                                    "zhipu_llm": {
                                        "llm_api_key": secret,
                                        "model": "glm-local",
                                    }
                                },
                            },
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            prepare_vtuber_config(root, {})

            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            zhipu = loaded["character_config"]["agent_config"]["llm_configs"][
                "zhipu_llm"
            ]
            self.assertEqual(zhipu["llm_api_key"], secret)
            self.assertEqual(zhipu["model"], "glm-local")

    def test_rejects_partial_environment_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "conf.yaml").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "GLM_BASE_URL"):
                prepare_vtuber_config(root, {"GLM_API_KEY": "configured"})


if __name__ == "__main__":
    unittest.main()
