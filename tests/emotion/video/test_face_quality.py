from __future__ import annotations

import unittest
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from apps.backend.app.capture.camera_buffer import TimestampedFrame
from apps.backend.app.emotion.video.face_quality import (
    FaceBox,
    FaceQualityConfig,
    FaceQualityEvaluator,
)


class FixedDetector:
    def __init__(self, faces: Sequence[FaceBox]) -> None:
        self._faces = faces

    def detect(self, _frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
        return self._faces


def checkerboard(size: int = 100) -> NDArray[np.uint8]:
    grid = np.indices((size, size)).sum(axis=0) % 2
    image = (grid * 160 + 40).astype(np.uint8)
    return np.repeat(image[:, :, None], 3, axis=2)


class FaceQualityTests(unittest.TestCase):
    def test_valid_single_face_produces_sufficient_quality(self) -> None:
        frames = tuple(TimestampedFrame(index, checkerboard()) for index in range(5))
        evaluator = FaceQualityEvaluator(FixedDetector(((10, 10, 50, 50),)))
        report = evaluator.evaluate(frames)
        self.assertGreaterEqual(report.quality, evaluator.config.sufficient_quality)
        self.assertEqual(report.valid_face_frames, 5)
        self.assertNotIn("no_valid_face", report.reasons)

    def test_dark_frame_without_face_is_insufficient(self) -> None:
        dark = np.zeros((100, 100, 3), dtype=np.uint8)
        evaluator = FaceQualityEvaluator(FixedDetector(()))
        report = evaluator.evaluate((TimestampedFrame(1, dark),))
        self.assertLess(report.quality, evaluator.config.sufficient_quality)
        self.assertIn("too_dark", report.reasons)
        self.assertIn("no_valid_face", report.reasons)

    def test_multiple_faces_are_reported(self) -> None:
        evaluator = FaceQualityEvaluator(
            FixedDetector(((5, 5, 30, 30), (50, 50, 30, 30))),
            FaceQualityConfig(sufficient_quality=0.1),
        )
        report = evaluator.evaluate((TimestampedFrame(1, checkerboard()),))
        self.assertIn("multiple_faces", report.reasons)


if __name__ == "__main__":
    unittest.main()
