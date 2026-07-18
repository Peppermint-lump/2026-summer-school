from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from apps.backend.app.capture.camera_buffer import TimestampedFrame
from apps.backend.app.capture.video_export import (
    FrameExportConfig,
    FrameExporter,
    sample_timestamped_frames,
)
from packages.schemas import VideoArtifactStatus


class VideoExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frames = tuple(
            TimestampedFrame(timestamp, np.ones((8, 8, 3), dtype=np.uint8))
            for timestamp in range(0, 2000, 100)
        )

    def test_sampling_is_time_based_and_bounded(self) -> None:
        selected = sample_timestamped_frames(
            self.frames,
            sample_fps=2,
            max_frames=3,
        )
        self.assertEqual([item.timestamp_ms for item in selected], [0, 500, 1000])

    def test_export_uses_application_owned_turn_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            exporter = FrameExporter(
                Path(temporary),
                FrameExportConfig(sample_fps=2, max_frames=2),
                encoder=lambda _frame, _quality: b"jpeg",
                resize=lambda frame, _limit: frame,
            )
            artifact = exporter.export("turn_001", self.frames, quality=0.8)

            self.assertEqual(artifact.status, VideoArtifactStatus.OK)
            self.assertEqual(artifact.sampled_frame_count, 2)
            self.assertTrue(all(path.exists() for path in artifact.frame_paths))
            self.assertTrue(
                all(
                    "turns/turn_001/video" in str(path) for path in artifact.frame_paths
                )
            )

    def test_default_opencv_encoder_produces_readable_jpeg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            exporter = FrameExporter(
                Path(temporary),
                FrameExportConfig(sample_fps=2, max_frames=1),
            )
            artifact = exporter.export("turn_002", self.frames, quality=0.8)
            decoded = cv2.imread(str(artifact.frame_paths[0]))
            self.assertIsNotNone(decoded)

    def test_export_rejects_path_traversal_turn_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            exporter = FrameExporter(Path(temporary))
            with self.assertRaises(ValueError):
                exporter.export("../escape", self.frames, quality=0.8)


if __name__ == "__main__":
    unittest.main()
