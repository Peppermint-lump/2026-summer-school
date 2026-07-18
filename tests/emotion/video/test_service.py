from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from apps.backend.app.emotion.providers.base import VideoEmotionRequest
from apps.backend.app.emotion.video.service import (
    VideoEmotionService,
    VideoEmotionServiceConfig,
)
from packages.schemas import (
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    VideoArtifactStatus,
    VideoTurnArtifact,
)


class SuccessfulProvider:
    async def analyze_video(self, request: VideoEmotionRequest) -> ModalityEmotion:
        return ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.8,
            quality=request.quality,
            status=EmotionStatus.OK,
        )


class SlowProvider:
    async def analyze_video(self, _request: VideoEmotionRequest) -> ModalityEmotion:
        await asyncio.sleep(1)
        raise AssertionError("timeout should cancel provider work")


class VideoEmotionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_camera_fails_open(self) -> None:
        service = VideoEmotionService(SuccessfulProvider())
        artifact = VideoTurnArtifact(
            turn_id="turn_1",
            status=VideoArtifactStatus.DISABLED,
        )
        result = await service.analyze(artifact)
        self.assertEqual(result.status, EmotionStatus.DISABLED)
        self.assertEqual(result.reliability, 0.0)

    async def test_insufficient_video_skips_provider(self) -> None:
        service = VideoEmotionService(
            SuccessfulProvider(),
            VideoEmotionServiceConfig(enabled=True),
        )
        artifact = VideoTurnArtifact(
            turn_id="turn_1",
            status=VideoArtifactStatus.INSUFFICIENT_EVIDENCE,
            quality=0.2,
            quality_reasons=("no_valid_face",),
        )
        result = await service.analyze(artifact)
        self.assertEqual(result.status, EmotionStatus.INSUFFICIENT_EVIDENCE)
        self.assertIn("no_valid_face", result.evidence)

    async def test_success_preserves_local_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.jpg"
            frame.write_bytes(b"jpeg")
            service = VideoEmotionService(
                SuccessfulProvider(),
                VideoEmotionServiceConfig(enabled=True),
            )
            artifact = VideoTurnArtifact(
                turn_id="turn_1",
                status=VideoArtifactStatus.OK,
                frame_paths=(frame,),
                captured_frame_count=1,
                sampled_frame_count=1,
                quality=0.75,
            )
            result = await service.analyze(artifact)
            self.assertEqual(result.status, EmotionStatus.OK)
            self.assertEqual(result.quality, 0.75)
            self.assertEqual(result.reliability, 0.6)

    async def test_provider_timeout_degrades_to_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frame = Path(temporary) / "frame.jpg"
            frame.write_bytes(b"jpeg")
            service = VideoEmotionService(
                SlowProvider(),
                VideoEmotionServiceConfig(
                    enabled=True,
                    provider_timeout_seconds=0.01,
                ),
            )
            artifact = VideoTurnArtifact(
                turn_id="turn_1",
                status=VideoArtifactStatus.OK,
                frame_paths=(frame,),
                sampled_frame_count=1,
                quality=0.8,
            )
            result = await service.analyze(artifact)
            self.assertEqual(result.status, EmotionStatus.TIMEOUT)
            self.assertEqual(result.label, EmotionLabel.UNCERTAIN)


if __name__ == "__main__":
    unittest.main()
