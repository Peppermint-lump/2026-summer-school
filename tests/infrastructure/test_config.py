from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.backend.app.infrastructure.config import (
    ConfigError,
    EnvironmentSecretStore,
    load_app_config,
)

VALID_CONFIG = """
capture:
  camera:
    enabled: true
    device_index: 0
    width: 640
    height: 480
    target_fps: 10
    buffer_seconds: 30
    sample_fps: 2
    max_sampled_frames: 12
    retain_media: false
emotion:
  video:
    enabled: false
    provider: mimo
    model: mimo-v2.5
    base_url: https://mimo.invalid/v1
    api_key_secret_name: MIMO_API_KEY
    timeout_seconds: 20
    max_retries: 2
    prompt_path: prompt.txt
    prompt_version: video_emotion_v1
    minimum_quality: 0.45
"""


class ConfigTests(unittest.TestCase):
    def test_loads_secret_free_validated_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prompt.txt").write_text("visual only", encoding="utf-8")
            path = root / "config.yaml"
            path.write_text(VALID_CONFIG, encoding="utf-8")
            config = load_app_config(path, repository_root=root)
            self.assertTrue(config.camera.enabled)
            self.assertFalse(config.video_emotion.enabled)
            self.assertEqual(config.video_emotion.model, "mimo-v2.5")

    def test_rejects_prompt_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "config.yaml"
            path.write_text(
                VALID_CONFIG.replace("prompt.txt", "../outside.txt"),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_app_config(path, repository_root=root)

    def test_secret_store_does_not_fabricate_missing_key(self) -> None:
        with self.assertRaises(ConfigError):
            EnvironmentSecretStore({}).get_required("MIMO_API_KEY")


if __name__ == "__main__":
    unittest.main()
