from __future__ import annotations

import unittest
from typing import Any

from apps.backend.app.emotion.providers.base import TextEmotionRequest
from apps.backend.app.emotion.providers.glm import (
    GlmTextConfig,
    GlmTextEmotionProvider,
)
from apps.backend.app.infrastructure.http_client import HttpResponse
from packages.schemas import EmotionLabel, Modality


class FakeHttpClient:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.payload: dict[str, Any] | None = None

    async def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.payload = payload
        return self.response


class GlmProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_only_prompt_and_current_transcript(self) -> None:
        client = FakeHttpClient(
            HttpResponse(
                status_code=200,
                data={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"label":"positive","confidence":0.8,'
                                    '"evidence":["explicit positive wording"]}'
                                )
                            }
                        }
                    ]
                },
                request_id="glm_request",
            )
        )
        provider = GlmTextEmotionProvider(
            GlmTextConfig(
                base_url="https://glm.invalid/v4",
                api_key="test-key-not-production",
                max_retries=0,
            ),
            client,
            prompt="text only",
        )

        result = await provider.analyze_text(
            TextEmotionRequest(
                turn_id="turn_1",
                transcript="今天很开心",
                quality=0.9,
                prompt_version="text_emotion_v1",
            )
        )

        self.assertEqual(result.modality, Modality.TEXT)
        self.assertEqual(result.label, EmotionLabel.POSITIVE)
        self.assertEqual(result.reliability, 0.72)
        self.assertIsNotNone(client.payload)
        messages = client.payload["messages"] if client.payload else []
        self.assertEqual(messages[-1]["content"], "今天很开心")
        self.assertNotIn("video", str(messages).lower())
        self.assertNotIn("audio", str(messages).lower())


if __name__ == "__main__":
    unittest.main()
