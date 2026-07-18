"""Deterministic local visual-quality assessment; it does not infer emotion."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from apps.backend.app.capture.camera_buffer import TimestampedFrame

FaceBox = tuple[int, int, int, int]


class FaceDetector(Protocol):
    def detect(self, frame: NDArray[np.uint8]) -> Sequence[FaceBox]: ...


class OpenCVFaceDetector:
    """Frontal-face detector used only for evidence quality and face count."""

    def __init__(self) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed") from exc
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cv2 = cv2
        self._classifier = cv2.CascadeClassifier(cascade_path)
        if self._classifier.empty():
            raise RuntimeError("OpenCV frontal-face cascade could not be loaded")

    def detect(self, frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
        grayscale = _to_grayscale(frame)
        faces = self._classifier.detectMultiScale(
            grayscale,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(40, 40),
        )
        return tuple(
            cast(FaceBox, tuple(int(value) for value in face)) for face in faces
        )


@dataclass(frozen=True, slots=True)
class FaceQualityConfig:
    minimum_brightness: float = 0.18
    maximum_brightness: float = 0.90
    minimum_sharpness: float = 0.06
    minimum_face_area_ratio: float = 0.025
    minimum_valid_face_ratio: float = 0.40
    sufficient_quality: float = 0.45

    def __post_init__(self) -> None:
        values = (
            self.minimum_brightness,
            self.maximum_brightness,
            self.minimum_sharpness,
            self.minimum_face_area_ratio,
            self.minimum_valid_face_ratio,
            self.sufficient_quality,
        )
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("quality thresholds must be between 0 and 1")
        if self.minimum_brightness >= self.maximum_brightness:
            raise ValueError("brightness thresholds are inverted")


@dataclass(frozen=True, slots=True)
class VideoQualityReport:
    quality: float
    total_frames: int
    valid_face_frames: int
    multiple_face_frames: int
    mean_brightness: float
    mean_sharpness: float
    reasons: tuple[str, ...]

    @property
    def has_sufficient_evidence(self) -> bool:
        return self.total_frames > 0 and "no_valid_face" not in self.reasons


def _to_grayscale(frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
    if frame.ndim == 2:
        return frame
    if frame.shape[2] < 3:
        return frame[:, :, 0]
    # OpenCV frames are BGR. These weights only assess luminance.
    blue = frame[:, :, 0].astype(np.float32)
    green = frame[:, :, 1].astype(np.float32)
    red = frame[:, :, 2].astype(np.float32)
    return np.clip(0.114 * blue + 0.587 * green + 0.299 * red, 0, 255).astype(np.uint8)


def _normalized_sharpness(grayscale: NDArray[np.uint8]) -> float:
    source = grayscale.astype(np.float32) / 255.0
    if min(source.shape[:2]) < 3:
        return 0.0
    vertical = np.abs(np.diff(source, axis=0)).mean()
    horizontal = np.abs(np.diff(source, axis=1)).mean()
    return float(min(1.0, (vertical + horizontal) * 4.0))


class FaceQualityEvaluator:
    def __init__(
        self,
        detector: FaceDetector,
        config: FaceQualityConfig | None = None,
    ) -> None:
        self._detector = detector
        self.config = config or FaceQualityConfig()

    def evaluate(self, frames: Sequence[TimestampedFrame]) -> VideoQualityReport:
        if not frames:
            return VideoQualityReport(
                quality=0.0,
                total_frames=0,
                valid_face_frames=0,
                multiple_face_frames=0,
                mean_brightness=0.0,
                mean_sharpness=0.0,
                reasons=("no_frames_in_turn", "no_valid_face"),
            )

        brightness_values: list[float] = []
        sharpness_values: list[float] = []
        valid_face_frames = 0
        multiple_face_frames = 0
        for item in frames:
            grayscale = _to_grayscale(item.frame)
            brightness = float(np.mean(grayscale) / 255.0)
            sharpness = _normalized_sharpness(grayscale)
            brightness_values.append(brightness)
            sharpness_values.append(sharpness)
            faces = self._detector.detect(item.frame)
            if len(faces) > 1:
                multiple_face_frames += 1
            if len(faces) != 1:
                continue
            x, y, width, height = faces[0]
            frame_area = item.frame.shape[0] * item.frame.shape[1]
            face_area_ratio = max(0, width) * max(0, height) / max(1, frame_area)
            well_lit = (
                self.config.minimum_brightness
                <= brightness
                <= self.config.maximum_brightness
            )
            if (
                well_lit
                and sharpness >= self.config.minimum_sharpness
                and face_area_ratio >= self.config.minimum_face_area_ratio
                and x >= 0
                and y >= 0
            ):
                valid_face_frames += 1

        total = len(frames)
        valid_ratio = valid_face_frames / total
        multiple_ratio = multiple_face_frames / total
        mean_brightness = float(np.mean(brightness_values))
        mean_sharpness = float(np.mean(sharpness_values))
        brightness_score = _brightness_score(
            mean_brightness,
            self.config.minimum_brightness,
            self.config.maximum_brightness,
        )
        sharpness_score = min(1.0, mean_sharpness / self.config.minimum_sharpness)
        single_face_score = 1.0 - multiple_ratio
        quality = round(
            max(
                0.0,
                min(
                    1.0,
                    0.60 * valid_ratio
                    + 0.15 * brightness_score
                    + 0.15 * sharpness_score
                    + 0.10 * single_face_score,
                ),
            ),
            4,
        )

        reasons: list[str] = []
        if valid_ratio < self.config.minimum_valid_face_ratio:
            reasons.append("no_valid_face")
        if multiple_face_frames:
            reasons.append("multiple_faces")
        if mean_brightness < self.config.minimum_brightness:
            reasons.append("too_dark")
        elif mean_brightness > self.config.maximum_brightness:
            reasons.append("overexposed")
        if mean_sharpness < self.config.minimum_sharpness:
            reasons.append("blurred")
        if quality < self.config.sufficient_quality:
            reasons.append("low_visual_quality")

        return VideoQualityReport(
            quality=quality,
            total_frames=total,
            valid_face_frames=valid_face_frames,
            multiple_face_frames=multiple_face_frames,
            mean_brightness=round(mean_brightness, 4),
            mean_sharpness=round(mean_sharpness, 4),
            reasons=tuple(dict.fromkeys(reasons)),
        )


def _brightness_score(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return max(0.0, value / minimum)
    if value > maximum:
        return max(0.0, (1.0 - value) / (1.0 - maximum))
    return 1.0
