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
    action_minimum_confidence: 0.60
    action_emotion_weight: 0.25
  text:
    enabled: false
    provider: glm
    model: glm-4.7-flash
    base_url: https://glm.invalid/v4
    api_key_secret_name: GLM_API_KEY
    timeout_seconds: 12
    max_retries: 2
    prompt_path: prompt.txt
    prompt_version: text_emotion_v1
fusion:
  reliable_threshold: 0.55
  positive_threshold: 0.25
  negative_threshold: -0.25
  text_weight: 0.45
  audio_weight: 0.25
  video_weight: 0.30
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

    def test_environment_overrides_provider_model_endpoint_and_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prompt.txt").write_text("visual only", encoding="utf-8")
            path = root / "config.yaml"
            path.write_text(VALID_CONFIG, encoding="utf-8")

            config = load_app_config(
                path,
                repository_root=root,
                environment={
                    "VIDEO_EMOTION_ENABLED": "true",
                    "TEXT_EMOTION_ENABLED": "true",
                    "VIDEO_EMOTION_PROVIDER": "mimo",
                    "VIDEO_EMOTION_TIMEOUT_SECONDS": "45",
                    "MIMO_MODEL": "mimo-test-model",
                    "MIMO_BASE_URL": "https://mimo.example/v1",
                    "GLM_TEXT_EMOTION_MODEL": "glm-test-model",
                    "GLM_BASE_URL": "https://glm.example/v4",
                    "TEXT_EMOTION_TIMEOUT_SECONDS": "30",
                },
            )

            self.assertTrue(config.video_emotion.enabled)
            self.assertEqual(config.video_emotion.model, "mimo-test-model")
            self.assertEqual(config.video_emotion.base_url, "https://mimo.example/v1")
            self.assertEqual(config.video_emotion.timeout_seconds, 45)
            self.assertEqual(config.text_emotion.model, "glm-test-model")
            self.assertEqual(config.text_emotion.timeout_seconds, 30)
            self.assertTrue(config.text_emotion.enabled)

    def test_rejects_invalid_environment_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prompt.txt").write_text("visual only", encoding="utf-8")
            path = root / "config.yaml"
            path.write_text(VALID_CONFIG, encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_app_config(
                    path,
                    repository_root=root,
                    environment={"TEXT_EMOTION_TIMEOUT_SECONDS": "zero"},
                )

    def test_secret_store_does_not_fabricate_missing_key(self) -> None:
        with self.assertRaises(ConfigError):
            EnvironmentSecretStore({}).get_required("MIMO_API_KEY")


if __name__ == "__main__":
    unittest.main()
