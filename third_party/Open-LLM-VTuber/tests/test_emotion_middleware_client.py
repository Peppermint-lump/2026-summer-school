from __future__ import annotations

import base64
import io
import unittest
import wave

import numpy as np

from src.open_llm_vtuber.emotion_middleware_client import (
    _encode_audio_wav,
    _parse_result,
    apply_emotion_context,
)


class EmotionMiddlewareClientTests(unittest.TestCase):
    def test_raw_float_audio_is_encoded_as_mono_pcm16_wav(self) -> None:
        samples = np.array([-1.0, -0.25, 0.25, 1.0], dtype=np.float32)
        encoded = _encode_audio_wav(samples, 16000)

        self.assertIsNotNone(encoded)
        assert encoded is not None
        with wave.open(io.BytesIO(encoded), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(wav_file.getframerate(), 16000)
            self.assertEqual(wav_file.getnframes(), 4)

    def test_result_parser_accepts_only_canonical_avatar_state(self) -> None:
        parsed = _parse_result(
            {
                "turn_id": "turn_1",
                "companion_context": "safe summary",
                "trace_directory": "/tmp/debug/turn_1",
                "avatar_state": {"expression": "heart", "motion": "greeting"},
            }
        )
        self.assertEqual(parsed.expression, "heart")
        self.assertEqual(parsed.motion, "greeting")

        with self.assertRaises(ValueError):
            _parse_result(
                {
                    "turn_id": "turn_1",
                    "companion_context": "safe summary",
                    "avatar_state": {
                        "expression": "arbitrary-provider-value",
                        "motion": "idle",
                    },
                }
            )

    def test_companion_receives_summary_not_audio(self) -> None:
        raw_audio = base64.b64encode(b"raw-media-sentinel").decode("ascii")
        combined = apply_emotion_context(
            "你好",
            {
                "emotion_companion_context": (
                    "[System context: text=positive; strategy=normal_conversation]"
                ),
                "audio_wav_base64": raw_audio,
            },
        )
        self.assertIn("text=positive", combined)
        self.assertNotIn(raw_audio, combined)


if __name__ == "__main__":
    unittest.main()
