from __future__ import annotations

import asyncio
import math
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from apps.backend.app.emotion.audio.quality import AudioQualityEvaluator
from apps.backend.app.emotion.audio.service import (
    AudioEmotionService,
    AudioEmotionServiceConfig,
)
from apps.backend.app.emotion.providers.base import AudioEmotionRequest
from packages.schemas import EmotionLabel, EmotionStatus, ModalityEmotion


class SuccessfulAudioProvider:
    async def analyze_audio(self, request: AudioEmotionRequest) -> ModalityEmotion:
        return ModalityEmotion.audio_result(
            label=EmotionLabel.POSITIVE,
            confidence=0.8,
            quality=request.quality,
            status=EmotionStatus.OK,
        )


class SlowAudioProvider:
    async def analyze_audio(self, _request: AudioEmotionRequest) -> ModalityEmotion:
        await asyncio.sleep(1)
        raise AssertionError("timeout should cancel provider work")


def write_test_wav(path: Path, *, amplitude: float, seconds: float = 1.0) -> None:
    sample_rate = 16_000
    sample_count = int(sample_rate * seconds)
    samples = array(
        "h",
        (
            int(32767 * amplitude * math.sin(2 * math.pi * 220 * i / sample_rate))
            for i in range(sample_count)
        ),
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


class AudioEmotionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_audio_is_independent_insufficient_evidence(self) -> None:
        service = AudioEmotionService(
            SuccessfulAudioProvider(),
            AudioQualityEvaluator(),
            AudioEmotionServiceConfig(enabled=True),
        )

        result = await service.analyze(turn_id="turn_1", audio_path=None)

        self.assertEqual(result.status, EmotionStatus.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.evidence, ("audio_missing",))

    async def test_low_level_audio_skips_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "quiet.wav"
            write_test_wav(audio, amplitude=0.0001)
            service = AudioEmotionService(
                SuccessfulAudioProvider(),
                AudioQualityEvaluator(),
                AudioEmotionServiceConfig(enabled=True),
            )

            result = await service.analyze(turn_id="turn_1", audio_path=audio)

        self.assertEqual(result.status, EmotionStatus.INSUFFICIENT_EVIDENCE)
        self.assertIn("audio_level_too_low", result.evidence)

    async def test_audio_quality_contributes_to_reliability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "voice.wav"
            write_test_wav(audio, amplitude=0.2)
            service = AudioEmotionService(
                SuccessfulAudioProvider(),
                AudioQualityEvaluator(),
                AudioEmotionServiceConfig(enabled=True),
            )

            result = await service.analyze(turn_id="turn_1", audio_path=audio)

        self.assertEqual(result.status, EmotionStatus.OK)
        self.assertGreaterEqual(result.reliability, 0.75)

    async def test_timeout_fails_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "voice.wav"
            write_test_wav(audio, amplitude=0.2)
            service = AudioEmotionService(
                SlowAudioProvider(),
                AudioQualityEvaluator(),
                AudioEmotionServiceConfig(
                    enabled=True,
                    provider_timeout_seconds=0.01,
                ),
            )

            result = await service.analyze(turn_id="turn_1", audio_path=audio)

        self.assertEqual(result.status, EmotionStatus.TIMEOUT)
        self.assertEqual(result.evidence, ("provider_timeout",))


if __name__ == "__main__":
    unittest.main()
