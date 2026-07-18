from __future__ import annotations

import unittest

import numpy as np

from apps.backend.app.capture.camera_buffer import (
    CameraBuffer,
    CameraBufferConfig,
    CameraState,
)


class FakeCapture:
    def __init__(self) -> None:
        self.released = False

    def isOpened(self) -> bool:  # noqa: N802
        return True

    def read(self) -> tuple[bool, np.ndarray]:
        return True, np.ones((4, 4, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True

    def set(self, _prop_id: int, _value: float) -> bool:
        return True


class CameraBufferTests(unittest.TestCase):
    def test_ring_buffer_is_bounded_and_turn_aligned(self) -> None:
        buffer = CameraBuffer(
            CameraBufferConfig(target_fps=2, buffer_seconds=2),
        )
        for timestamp in (100, 200, 300, 400, 500):
            buffer.append_frame(
                timestamp, np.full((4, 4, 3), timestamp % 255, np.uint8)
            )

        self.assertEqual(buffer.capacity, 4)
        self.assertEqual(
            [item.timestamp_ms for item in buffer.frames_between(250, 450)],
            [300, 400],
        )
        self.assertEqual(
            [item.timestamp_ms for item in buffer.frames_between(0, 1000)],
            [200, 300, 400, 500],
        )

    def test_frames_are_copied_at_capture_boundary(self) -> None:
        buffer = CameraBuffer()
        source = np.ones((3, 3, 3), dtype=np.uint8)
        buffer.append_frame(100, source)
        source[:] = 0
        self.assertTrue(np.all(buffer.frames_between(100, 100)[0].frame == 1))

    def test_rejects_non_monotonic_timestamps(self) -> None:
        buffer = CameraBuffer()
        frame = np.ones((2, 2), dtype=np.uint8)
        buffer.append_frame(200, frame)
        with self.assertRaises(ValueError):
            buffer.append_frame(100, frame)

    def test_explicit_start_and_stop_own_camera_lifecycle(self) -> None:
        capture = FakeCapture()
        buffer = CameraBuffer(
            CameraBufferConfig(target_fps=30, startup_timeout_seconds=0.5),
            capture_factory=lambda _index: capture,
        )
        buffer.start()
        self.assertEqual(buffer.state, CameraState.RUNNING)
        buffer.stop()
        self.assertEqual(buffer.state, CameraState.STOPPED)
        self.assertTrue(capture.released)


if __name__ == "__main__":
    unittest.main()
