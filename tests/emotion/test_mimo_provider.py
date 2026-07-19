from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from apps.backend.app.emotion.providers.base import (
    AudioEmotionRequest,
    ProviderInvalidOutputError,
    VideoEmotionRequest,
)
from apps.backend.app.emotion.providers.mimo import (
    MiMoAudioConfig,
    MiMoAudioEmotionProvider,
    MiMoVideoConfig,
    MiMoVideoEmotionProvider,
)
from apps.backend.app.infrastructure.http_client import HttpResponse
from packages.schemas import ActionType, EmotionLabel, EmotionStatus, Modality


class FakeHttpClient:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = responses
        self.payloads: list[dict[str, Any]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.payloads.append(payload)
        return self._responses.pop(0)


def response_with_content(content: str, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status_code=status,
        data={"choices": [{"message": {"content": content}}]},
        request_id="request_1",
    )


class MiMoProviderTests(unittest.IsolatedAsyncioTestCase):
    def config(self, **changes: Any) -> MiMoVideoConfig:
        values: dict[str, Any] = {
            "base_url": "https://mimo.invalid/v1",
            "api_key": "test-key-not-production",
            "max_retries": 0,
        }
        values.update(changes)
        return MiMoVideoConfig(**values)

    def audio_config(self, **changes: Any) -> MiMoAudioConfig:
        values: dict[str, Any] = {
            "base_url": "https://mimo.invalid/v1",
            "api_key": "test-key-not-production",
            "max_retries": 0,
        }
        values.update(changes)
        return MiMoAudioConfig(**values)

    async def test_audio_payload_contains_only_raw_audio_and_prompt(self) -> None:
        client = FakeHttpClient(
            [
                response_with_content(
                    '{"label":"positive","fine_emotion":"bright prosody",'
                    '"confidence":0.8,"evidence":["rising energy"]}'
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            audio = Path(temporary) / "turn.wav"
            audio.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
            provider = MiMoAudioEmotionProvider(
                self.audio_config(), client, prompt="prosody only; ignore words"
            )
            result = await provider.analyze_audio(
                AudioEmotionRequest(
                    turn_id="turn_1",
                    audio_path=audio,
                    quality=0.75,
                    prompt_version="audio_emotion_v1",
                )
            )

        self.assertEqual(result.modality, Modality.AUDIO)
        self.assertEqual(result.reliability, 0.6)
        content = client.payloads[0]["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "input_audio")
        self.assertIn("data:audio/wav;base64", content[0]["input_audio"]["data"])
        self.assertNotIn("transcript", str(content).lower())

    async def test_normalizes_video_only_json(self) -> None:
        client = FakeHttpClient(
            [
                response_with_content(
                    '{"label":"消极","fine_emotion":"subdued",'
                    '"confidence":0.75,"evidence":["visible cue"]}'
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.jpg"
            frame.write_bytes(b"\xff\xd8\xffimage")
            provider = MiMoVideoEmotionProvider(
                self.config(), client, prompt="visual evidence only"
            )
            result = await provider.analyze_video(
                VideoEmotionRequest(
                    turn_id="turn_1",
                    frame_paths=(frame,),
                    quality=0.8,
                    prompt_version="video_emotion_v1",
                )
            )

        self.assertEqual(result.label, EmotionLabel.NEGATIVE)
        self.assertEqual(result.status, EmotionStatus.OK)
        self.assertEqual(result.reliability, 0.6)
        message = client.payloads[0]["messages"][0]
        self.assertNotIn("transcript", str(message).lower())
        self.assertIn("data:image/jpeg;base64", str(message))

    async def test_invalid_provider_json_is_typed_error(self) -> None:
        client = FakeHttpClient([response_with_content("not-json")])
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.jpg"
            frame.write_bytes(b"\xff\xd8\xffimage")
            provider = MiMoVideoEmotionProvider(
                self.config(), client, prompt="visual only"
            )
            with self.assertRaises(ProviderInvalidOutputError):
                await provider.analyze_video(
                    VideoEmotionRequest(
                        turn_id="turn_1",
                        frame_paths=(frame,),
                        quality=0.8,
                        prompt_version="video_emotion_v1",
                    )
                )

    async def test_normalizes_temporal_action_observations(self) -> None:
        client = FakeHttpClient(
            [
                response_with_content(
                    '{"label":"neutral","confidence":0.7,"evidence":[],'
                    '"actions":[{"type":"waving","confidence":0.9,'
                    '"evidence":"hand moves side to side across frames"}]}'
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.jpg"
            frame.write_bytes(b"\xff\xd8\xffimage")
            provider = MiMoVideoEmotionProvider(
                self.config(), client, prompt="ordered visual frames only"
            )
            result = await provider.analyze_video(
                VideoEmotionRequest(
                    turn_id="turn_1",
                    frame_paths=(frame,),
                    quality=0.9,
                    prompt_version="video_emotion_v1",
                )
            )

        self.assertEqual(result.observed_actions[0].action, ActionType.WAVE)
        self.assertEqual(result.observed_actions[0].confidence, 0.9)

    async def test_rate_limit_retry_is_bounded(self) -> None:
        client = FakeHttpClient(
            [
                HttpResponse(status_code=429, data={}),
                response_with_content(
                    '{"label":"neutral","confidence":0.5,"evidence":[]}'
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.jpg"
            frame.write_bytes(b"\xff\xd8\xffimage")
            provider = MiMoVideoEmotionProvider(
                self.config(max_retries=1, retry_base_seconds=0),
                client,
                prompt="visual only",
            )
            result = await provider.analyze_video(
                VideoEmotionRequest(
                    turn_id="turn_1",
                    frame_paths=(frame,),
                    quality=0.8,
                    prompt_version="video_emotion_v1",
                )
            )
        self.assertEqual(result.label, EmotionLabel.NEUTRAL)
        self.assertEqual(len(client.payloads), 2)


if __name__ == "__main__":
    unittest.main()
