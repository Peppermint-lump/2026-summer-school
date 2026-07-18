from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from apps.backend.app.capture.camera_buffer import CameraBuffer, CameraState
from apps.backend.app.debug.camera_preview import (
    CameraPreviewApplication,
    PreviewHTTPServer,
)
from apps.backend.app.emotion.video.face_quality import FaceBox, FaceQualityEvaluator


class RunningCameraBuffer(CameraBuffer):
    @property
    def state(self) -> CameraState:
        return CameraState.RUNNING


class SingleFaceDetector:
    def detect(self, _frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
        return ((2, 2, 8, 8),)


class CameraPreviewTests(unittest.TestCase):
    def build_application(self) -> CameraPreviewApplication:
        camera = RunningCameraBuffer()
        timestamp_ms = time.time_ns() // 1_000_000
        grid = np.indices((20, 20)).sum(axis=0) % 2
        frame = np.repeat(((grid * 160 + 40).astype(np.uint8))[:, :, None], 3, 2)
        camera.append_frame(timestamp_ms, frame)
        return CameraPreviewApplication(
            camera,
            FaceQualityEvaluator(SingleFaceDetector()),
        )

    def test_status_proves_pipeline_received_recent_frame(self) -> None:
        status = self.build_application().status()
        self.assertTrue(status["pipeline_receiving_frames"])
        self.assertEqual(status["recent_frame_count"], 1)
        self.assertEqual(status["gesture_recognition"], "not_implemented")
        self.assertFalse(status["retained_media"])

    def test_preview_jpeg_is_memory_only_and_valid(self) -> None:
        jpeg = self.build_application().latest_jpeg()
        self.assertIsNotNone(jpeg)
        assert jpeg is not None
        self.assertTrue(jpeg.startswith(b"\xff\xd8\xff"))

    def test_status_endpoint_requires_ephemeral_token(self) -> None:
        try:
            server = PreviewHTTPServer(
                ("127.0.0.1", 0), self.build_application(), "token"
            )
        except PermissionError:
            self.skipTest("local socket binding is disabled by the test sandbox")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/status?token=token",
                timeout=2,
            ) as response:
                status = json.loads(response.read())
            self.assertTrue(status["pipeline_receiving_frames"])
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/status",
                    timeout=2,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
