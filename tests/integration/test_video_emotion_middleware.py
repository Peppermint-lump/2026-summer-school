from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from apps.backend.app.capture.camera_buffer import CameraBuffer
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.capture.video_export import FrameExporter
from apps.backend.app.emotion.providers.base import VideoEmotionRequest
from apps.backend.app.emotion.video.face_quality import FaceBox, FaceQualityEvaluator
from apps.backend.app.emotion.video.preprocess import VideoTurnPreprocessor
from apps.backend.app.emotion.video.service import (
    VideoEmotionService,
    VideoEmotionServiceConfig,
)
from apps.backend.app.integration.video_emotion_middleware import (
    VideoEmotionMiddleware,
)
from packages.schemas import (
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    TurnRecord,
)


class SingleFaceDetector:
    def detect(self, _frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
        return ((10, 10, 60, 60),)


class FileCheckingProvider:
    async def analyze_video(self, request: VideoEmotionRequest) -> ModalityEmotion:
        if not all(path.exists() for path in request.frame_paths):
            raise AssertionError("turn media was removed before provider analysis")
        return ModalityEmotion.video_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.7,
            quality=request.quality,
            status=EmotionStatus.OK,
        )


class VideoEmotionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_media_is_removed_after_successful_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary)
            camera = CameraBuffer()
            grid = np.indices((100, 100)).sum(axis=0) % 2
            image = np.repeat(((grid * 160 + 40).astype(np.uint8))[:, :, None], 3, 2)
            for timestamp in (100, 200, 300):
                camera.append_frame(timestamp, image)
            middleware = VideoEmotionMiddleware(
                VideoTurnPreprocessor(
                    camera,
                    FaceQualityEvaluator(SingleFaceDetector()),
                    FrameExporter(runtime_root),
                ),
                VideoEmotionService(
                    FileCheckingProvider(),
                    VideoEmotionServiceConfig(enabled=True),
                ),
                TurnMediaCleaner(runtime_root),
                camera_enabled=True,
            )
            turn = TurnRecord(
                session_id="session_1",
                turn_id="turn_1",
                speech_start_ms=100,
                speech_end_ms=300,
            )

            result = await middleware.analyze_turn(turn)

            self.assertEqual(result.status, EmotionStatus.OK)
            self.assertFalse((runtime_root / "turns" / "turn_1").exists())

    async def test_camera_disabled_returns_without_creating_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary)
            middleware = VideoEmotionMiddleware(
                VideoTurnPreprocessor(
                    CameraBuffer(),
                    FaceQualityEvaluator(SingleFaceDetector()),
                    FrameExporter(runtime_root),
                ),
                VideoEmotionService(FileCheckingProvider()),
                TurnMediaCleaner(runtime_root),
                camera_enabled=False,
            )
            result = await middleware.analyze_turn(
                TurnRecord(
                    session_id="session_1",
                    turn_id="turn_2",
                    speech_start_ms=100,
                    speech_end_ms=200,
                )
            )
            self.assertEqual(result.status, EmotionStatus.DISABLED)
            self.assertFalse((runtime_root / "turns").exists())


if __name__ == "__main__":
    unittest.main()
