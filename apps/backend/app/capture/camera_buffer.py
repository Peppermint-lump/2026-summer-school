"""Opt-in OpenCV camera capture backed by a timestamped ring buffer."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

Frame: TypeAlias = NDArray[np.uint8]


class CameraUnavailableError(RuntimeError):
    """Raised when an explicitly enabled camera cannot be opened."""


class CameraState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class CaptureDevice(Protocol):
    def isOpened(self) -> bool: ...  # noqa: N802 - OpenCV compatibility

    def read(self) -> tuple[bool, Frame]: ...

    def release(self) -> None: ...

    def set(self, prop_id: int, value: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class CameraBufferConfig:
    device_index: int = 0
    width: int = 640
    height: int = 480
    target_fps: float = 10.0
    buffer_seconds: float = 30.0
    startup_timeout_seconds: float = 3.0
    max_consecutive_read_failures: int = 10

    def __post_init__(self) -> None:
        if self.device_index < 0:
            raise ValueError("device_index must be non-negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera dimensions must be positive")
        if self.target_fps <= 0 or self.buffer_seconds <= 0:
            raise ValueError("target_fps and buffer_seconds must be positive")
        if self.max_consecutive_read_failures <= 0:
            raise ValueError("max_consecutive_read_failures must be positive")


@dataclass(frozen=True, slots=True)
class TimestampedFrame:
    timestamp_ms: int
    frame: Frame

    def __post_init__(self) -> None:
        if self.timestamp_ms < 0:
            raise ValueError("timestamp_ms must be non-negative")
        if self.frame.ndim not in (2, 3) or self.frame.size == 0:
            raise ValueError("frame must be a non-empty image array")


def _opencv_capture_factory(device_index: int) -> CaptureDevice:
    try:
        import cv2
    except ImportError as exc:
        raise CameraUnavailableError("OpenCV is not installed") from exc
    return cast(CaptureDevice, cv2.VideoCapture(device_index))


class CameraBuffer:
    """Own one capture thread and retain only a bounded window of copied frames."""

    def __init__(
        self,
        config: CameraBufferConfig | None = None,
        *,
        capture_factory: Callable[[int], CaptureDevice] = _opencv_capture_factory,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.config = config or CameraBufferConfig()
        capacity = max(1, int(self.config.target_fps * self.config.buffer_seconds))
        self._frames: deque[TimestampedFrame] = deque(maxlen=capacity)
        self._capture_factory = capture_factory
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._state = CameraState.STOPPED
        self._state_lock = threading.Lock()
        self._frames_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._capture: CaptureDevice | None = None
        self._thread: threading.Thread | None = None
        self._failure: CameraUnavailableError | None = None

    @property
    def state(self) -> CameraState:
        with self._state_lock:
            return self._state

    @property
    def capacity(self) -> int:
        return self._frames.maxlen or 0

    def start(self) -> None:
        """Start capture only after the caller has obtained explicit user consent."""
        with self._state_lock:
            if self._state in (CameraState.STARTING, CameraState.RUNNING):
                return
            self._state = CameraState.STARTING
            self._failure = None
        try:
            # AVFoundation must open the device and request macOS permission on the
            # calling/main thread. Frame reads remain isolated on the worker thread.
            capture = self._capture_factory(self.config.device_index)
            if not capture.isOpened():
                capture.release()
                raise CameraUnavailableError("camera device could not be opened")
            self._configure_capture(capture)
            self._capture = capture
        except (CameraUnavailableError, OSError) as exc:
            failure = CameraUnavailableError("camera device initialization failed")
            if isinstance(exc, CameraUnavailableError):
                failure = exc
            self._failure = failure
            with self._state_lock:
                self._state = CameraState.FAILED
            if failure is exc:
                raise
            raise failure from exc
        self._stop_event.clear()
        self._started_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="camera-buffer",
            daemon=True,
        )
        self._thread.start()
        if not self._started_event.wait(self.config.startup_timeout_seconds):
            self.stop()
            raise CameraUnavailableError("camera startup timed out")
        if self.state is CameraState.FAILED:
            failure = self._failure or CameraUnavailableError("camera failed to start")
            self.stop()
            raise failure

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=self.config.startup_timeout_seconds)
        capture = self._capture
        if capture is not None:
            capture.release()
        self._capture = None
        self._thread = None
        with self._state_lock:
            self._state = CameraState.STOPPED

    def clear(self) -> None:
        with self._frames_lock:
            self._frames.clear()

    def append_frame(self, timestamp_ms: int, frame: Frame) -> None:
        """Append a copied frame for capture adapters and deterministic tests."""
        timestamped = TimestampedFrame(timestamp_ms, np.ascontiguousarray(frame.copy()))
        with self._frames_lock:
            if self._frames and timestamp_ms < self._frames[-1].timestamp_ms:
                raise ValueError("camera timestamps must be monotonically increasing")
            self._frames.append(timestamped)

    def frames_between(
        self, start_ms: int, end_ms: int
    ) -> tuple[TimestampedFrame, ...]:
        if start_ms < 0 or end_ms < start_ms:
            raise ValueError("invalid frame time range")
        with self._frames_lock:
            return tuple(
                item for item in self._frames if start_ms <= item.timestamp_ms <= end_ms
            )

    def latest_frame(self) -> TimestampedFrame | None:
        """Return a copied latest frame for a local preview consumer."""
        with self._frames_lock:
            if not self._frames:
                return None
            latest = self._frames[-1]
            return TimestampedFrame(latest.timestamp_ms, latest.frame.copy())

    def _capture_loop(self) -> None:
        try:
            capture = self._capture
            if capture is None:
                raise CameraUnavailableError("camera device was not initialized")
            with self._state_lock:
                self._state = CameraState.RUNNING
            self._started_event.set()
            failures = 0
            frame_interval = 1.0 / self.config.target_fps
            while not self._stop_event.is_set():
                loop_started = time.monotonic()
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    failures += 1
                    if failures >= self.config.max_consecutive_read_failures:
                        raise CameraUnavailableError(
                            "camera repeatedly failed to read frames"
                        )
                else:
                    failures = 0
                    self.append_frame(self._clock_ms(), frame)
                remaining = frame_interval - (time.monotonic() - loop_started)
                if remaining > 0:
                    self._stop_event.wait(remaining)
        except CameraUnavailableError as exc:
            self._failure = exc
            with self._state_lock:
                self._state = CameraState.FAILED
            self._started_event.set()
        finally:
            capture_to_release = self._capture
            if capture_to_release is not None:
                capture_to_release.release()
            self._capture = None

    def _configure_capture(self, capture: CaptureDevice) -> None:
        try:
            import cv2
        except ImportError:
            return
        properties: tuple[tuple[int, Any], ...] = (
            (cv2.CAP_PROP_FRAME_WIDTH, self.config.width),
            (cv2.CAP_PROP_FRAME_HEIGHT, self.config.height),
            (cv2.CAP_PROP_FPS, self.config.target_fps),
        )
        for property_id, value in properties:
            capture.set(property_id, float(value))
