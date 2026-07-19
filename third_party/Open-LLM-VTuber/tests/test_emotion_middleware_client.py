from __future__ import annotations

import base64
import io
import unittest
import wave

import numpy as np

from src.open_llm_vtuber.emotion_middleware_client import (
    _encode_audio_wav,
    _parse_result,
    _parse_visual_update,
    _turn_start_times,
    apply_emotion_context,
    canonical_visual_observation_available,
)


class EmotionMiddlewareClientTests(unittest.TestCase):
    def test_canonical_video_availability_requires_observed_video(self) -> None:
        self.assertTrue(
            canonical_visual_observation_available(
                {
                    "analysis": {
                        "observations": [
                            {"modality": "text", "status": "ok"},
                            {"modality": "video", "status": "ok"},
                        ]
                    }
                }
            )
        )
        self.assertFalse(
            canonical_visual_observation_available(
                {
                    "analysis": {
                        "observations": [
                            {
                                "modality": "video",
                                "status": "insufficient_evidence",
                            }
                        ]
                    }
                }
            )
        )

    def test_typed_turn_uses_recent_visual_window_without_fake_speech(self) -> None:
        self.assertEqual(
            _turn_start_times(
                end_ms=10_000,
                audio_duration_ms=0,
                text_visual_window_seconds=3,
            ),
            (10_000, 7_000),
        )

    def test_audio_turn_aligns_visual_window_to_real_speech(self) -> None:
        self.assertEqual(
            _turn_start_times(
                end_ms=10_000,
                audio_duration_ms=1_500,
                text_visual_window_seconds=3,
            ),
            (8_500, 8_500),
        )

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

        observe = _parse_result(
            {
                "turn_id": "turn_2",
                "companion_context": "visible action, semantics uncertain",
                "avatar_state": {"expression": "neutral", "motion": "observe"},
            }
        )
        self.assertEqual(observe.motion, "observe")

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

    def test_visual_update_is_emitted_only_for_a_new_sequence(self) -> None:
        payload = {
            "available": True,
            "sequence": 4,
            "result": {
                "turn_id": "visual_4",
                "companion_context": "video only",
                "trace_directory": "/tmp/debug/visual_4",
                "avatar_state": {"expression": "heart", "motion": "greeting"},
            },
        }
        update = _parse_visual_update(payload, 3)
        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update[0], 4)
        self.assertEqual(update[1].motion, "greeting")
        self.assertIsNone(_parse_visual_update(payload, 4))


if __name__ == "__main__":
    unittest.main()
