"""Export sampled, resized JPEG frames to an application-owned turn directory."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from packages.schemas import VideoArtifactStatus, VideoTurnArtifact

from .camera_buffer import TimestampedFrame


class FrameEncodingError(RuntimeError):
    """Raised when OpenCV cannot encode a sampled frame."""


@dataclass(frozen=True, slots=True)
class FrameExportConfig:
    sample_fps: float = 2.0
    max_frames: int = 12
    max_dimension: int = 768
    jpeg_quality: int = 82

    def __post_init__(self) -> None:
        if self.sample_fps <= 0 or self.max_frames <= 0 or self.max_dimension <= 0:
            raise ValueError("frame export limits must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")


def sample_timestamped_frames(
    frames: Sequence[TimestampedFrame],
    *,
    sample_fps: float,
    max_frames: int,
) -> tuple[TimestampedFrame, ...]:
    if sample_fps <= 0 or max_frames <= 0:
        raise ValueError("sample_fps and max_frames must be positive")
    if not frames:
        return ()
    interval_ms = 1000.0 / sample_fps
    selected: list[TimestampedFrame] = []
    next_timestamp = float(frames[0].timestamp_ms)
    for item in frames:
        if item.timestamp_ms >= next_timestamp:
            selected.append(item)
            next_timestamp = item.timestamp_ms + interval_ms
            if len(selected) >= max_frames:
                break
    return tuple(selected)


def _opencv_encoder(frame: NDArray[np.uint8], jpeg_quality: int) -> bytes:
    try:
        import cv2
    except ImportError as exc:
        raise FrameEncodingError("OpenCV is not installed") from exc
    ok, encoded = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
    )
    if not ok:
        raise FrameEncodingError("OpenCV failed to encode a frame")
    return cast(bytes, encoded.tobytes())


def resize_to_fit(frame: NDArray[np.uint8], max_dimension: int) -> NDArray[np.uint8]:
    if max(frame.shape[:2]) <= max_dimension:
        return frame
    scale = max_dimension / max(frame.shape[:2])
    new_height = max(1, round(frame.shape[0] * scale))
    new_width = max(1, round(frame.shape[1] * scale))
    try:
        import cv2
    except ImportError as exc:
        raise FrameEncodingError("OpenCV is required to resize frames") from exc
    return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)


class FrameExporter:
    def __init__(
        self,
        runtime_root: Path,
        config: FrameExportConfig | None = None,
        *,
        encoder: Callable[[NDArray[np.uint8], int], bytes] = _opencv_encoder,
        resize: Callable[[NDArray[np.uint8], int], NDArray[np.uint8]] = resize_to_fit,
    ) -> None:
        self._runtime_root = runtime_root.resolve()
        self.config = config or FrameExportConfig()
        self._encoder = encoder
        self._resize = resize

    def export(
        self,
        turn_id: str,
        frames: Sequence[TimestampedFrame],
        *,
        quality: float,
        quality_reasons: tuple[str, ...] = (),
    ) -> VideoTurnArtifact:
        safe_turn_id = self._validate_turn_id(turn_id)
        selected = sample_timestamped_frames(
            frames,
            sample_fps=self.config.sample_fps,
            max_frames=self.config.max_frames,
        )
        if not selected:
            return VideoTurnArtifact(
                turn_id=safe_turn_id,
                status=VideoArtifactStatus.INSUFFICIENT_EVIDENCE,
                captured_frame_count=len(frames),
                quality=0.0,
                quality_reasons=("no_frames_in_turn",),
            )

        output_dir = self._runtime_root / "turns" / safe_turn_id / "video"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_paths: list[Path] = []
        for index, item in enumerate(selected):
            resized = self._resize(item.frame, self.config.max_dimension)
            encoded = self._encoder(resized, self.config.jpeg_quality)
            path = output_dir / f"frame_{index:06d}_{item.timestamp_ms}.jpg"
            path.write_bytes(encoded)
            output_paths.append(path)

        return VideoTurnArtifact(
            turn_id=safe_turn_id,
            status=VideoArtifactStatus.OK,
            frame_paths=tuple(output_paths),
            captured_frame_count=len(frames),
            sampled_frame_count=len(output_paths),
            quality=quality,
            quality_reasons=quality_reasons,
        )

    @staticmethod
    def _validate_turn_id(turn_id: str) -> str:
        if not turn_id or turn_id in {".", ".."}:
            raise ValueError("turn_id must be non-empty")
        if any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in turn_id
        ):
            raise ValueError("turn_id contains unsafe path characters")
        return turn_id
