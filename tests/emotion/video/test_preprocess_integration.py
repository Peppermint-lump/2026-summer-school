from __future__ import annotations

import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from apps.backend.app.capture.camera_buffer import CameraBuffer
from apps.backend.app.capture.video_export import FrameExporter
from apps.backend.app.emotion.video.face_quality import (
    FaceBox,
    FaceQualityConfig,
    FaceQualityEvaluator,
)
from apps.backend.app.emotion.video.preprocess import VideoTurnPreprocessor
from packages.schemas import VideoArtifactStatus


class SingleFaceDetector:
    def detect(self, _frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
        return ((10, 10, 60, 60),)


class VideoPreprocessIntegrationTests(unittest.TestCase):
    def test_turn_range_quality_and_export_form_one_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            camera = CameraBuffer()
            grid = np.indices((100, 100)).sum(axis=0) % 2
            image = np.repeat(((grid * 160 + 40).astype(np.uint8))[:, :, None], 3, 2)
            for timestamp in (100, 200, 300, 400, 500):
                camera.append_frame(timestamp, image)
            preprocessor = VideoTurnPreprocessor(
                camera,
                FaceQualityEvaluator(SingleFaceDetector()),
                FrameExporter(Path(temporary)),
            )

            artifact = preprocessor.prepare("turn_1", 200, 400)

            self.assertEqual(artifact.status, VideoArtifactStatus.OK)
            self.assertEqual(artifact.captured_frame_count, 3)
            self.assertGreater(artifact.quality, 0.45)
            self.assertTrue(all(path.exists() for path in artifact.frame_paths))

    def test_no_frames_returns_insufficient_evidence_without_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            preprocessor = VideoTurnPreprocessor(
                CameraBuffer(),
                FaceQualityEvaluator(SingleFaceDetector()),
                FrameExporter(Path(temporary)),
            )
            artifact = preprocessor.prepare("turn_2", 100, 200)
            self.assertEqual(
                artifact.status,
                VideoArtifactStatus.INSUFFICIENT_EVIDENCE,
            )
            self.assertFalse((Path(temporary) / "turns" / "turn_2").exists())

    def test_no_valid_face_never_reaches_export_even_with_low_threshold(self) -> None:
        class NoFaceDetector:
            def detect(self, _frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
                return ()

        with tempfile.TemporaryDirectory() as temporary:
            camera = CameraBuffer()
            grid = np.indices((100, 100)).sum(axis=0) % 2
            image = np.repeat(((grid * 160 + 40).astype(np.uint8))[:, :, None], 3, 2)
            camera.append_frame(100, image)
            preprocessor = VideoTurnPreprocessor(
                camera,
                FaceQualityEvaluator(
                    NoFaceDetector(),
                    FaceQualityConfig(sufficient_quality=0.1),
                ),
                FrameExporter(Path(temporary)),
            )
            artifact = preprocessor.prepare("turn_3", 100, 100)
            self.assertEqual(
                artifact.status,
                VideoArtifactStatus.INSUFFICIENT_EVIDENCE,
            )
            self.assertIn("no_valid_face", artifact.quality_reasons)
            self.assertFalse((Path(temporary) / "turns" / "turn_3").exists())


if __name__ == "__main__":
    unittest.main()
