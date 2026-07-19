from __future__ import annotations

import asyncio
import unittest

from apps.backend.app.emotion.providers.base import (
    ProviderRateLimitError,
    TextEmotionRequest,
)
from apps.backend.app.emotion.text.service import (
    TextEmotionService,
    TextEmotionServiceConfig,
)
from packages.schemas import EmotionLabel, EmotionStatus, ModalityEmotion


class SuccessfulProvider:
    async def analyze_text(self, request: TextEmotionRequest) -> ModalityEmotion:
        return ModalityEmotion.text_result(
            label=EmotionLabel.POSITIVE,
            confidence=0.8,
            quality=request.quality,
            status=EmotionStatus.OK,
        )


class SlowProvider:
    async def analyze_text(self, _request: TextEmotionRequest) -> ModalityEmotion:
        await asyncio.sleep(1)
        raise AssertionError("timeout should cancel provider work")


class RateLimitedProvider:
    async def analyze_text(self, _request: TextEmotionRequest) -> ModalityEmotion:
        raise ProviderRateLimitError("rate limited")


class TextEmotionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_transcript_is_insufficient_evidence(self) -> None:
        service = TextEmotionService(
            SuccessfulProvider(), TextEmotionServiceConfig(enabled=True)
        )
        result = await service.analyze(turn_id="turn_1", transcript="  ")
        self.assertEqual(result.status, EmotionStatus.INSUFFICIENT_EVIDENCE)

    async def test_text_quality_contributes_to_reliability(self) -> None:
        service = TextEmotionService(
            SuccessfulProvider(), TextEmotionServiceConfig(enabled=True)
        )
        result = await service.analyze(
            turn_id="turn_1", transcript="我今天真的非常开心"
        )
        self.assertEqual(result.label, EmotionLabel.POSITIVE)
        self.assertGreater(result.reliability, 0.55)

    async def test_timeout_fails_open(self) -> None:
        service = TextEmotionService(
            SlowProvider(),
            TextEmotionServiceConfig(
                enabled=True,
                provider_timeout_seconds=0.01,
            ),
        )
        result = await service.analyze(turn_id="turn_1", transcript="普通文本")
        self.assertEqual(result.status, EmotionStatus.TIMEOUT)
        self.assertEqual(result.label, EmotionLabel.UNCERTAIN)
        self.assertEqual(result.evidence, ("provider_timeout",))

    async def test_rate_limit_is_visible_but_fails_open(self) -> None:
        service = TextEmotionService(
            RateLimitedProvider(), TextEmotionServiceConfig(enabled=True)
        )
        result = await service.analyze(turn_id="turn_1", transcript="普通文本")
        self.assertEqual(result.status, EmotionStatus.PROVIDER_ERROR)
        self.assertEqual(result.evidence, ("provider_rate_limited",))


if __name__ == "__main__":
    unittest.main()
