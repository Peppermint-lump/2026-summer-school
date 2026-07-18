"""Build a provider-ready, quality-scored artifact for one speech turn."""

from __future__ import annotations

from apps.backend.app.capture.camera_buffer import CameraBuffer
from apps.backend.app.capture.video_export import FrameExporter
from packages.schemas import VideoArtifactStatus, VideoTurnArtifact

from .face_quality import FaceQualityEvaluator


class VideoTurnPreprocessor:
    def __init__(
        self,
        camera_buffer: CameraBuffer,
        quality_evaluator: FaceQualityEvaluator,
        frame_exporter: FrameExporter,
    ) -> None:
        self._camera_buffer = camera_buffer
        self._quality_evaluator = quality_evaluator
        self._frame_exporter = frame_exporter

    def prepare(self, turn_id: str, start_ms: int, end_ms: int) -> VideoTurnArtifact:
        frames = self._camera_buffer.frames_between(start_ms, end_ms)
        report = self._quality_evaluator.evaluate(frames)
        if (
            report.quality < self._quality_evaluator.config.sufficient_quality
            or "no_valid_face" in report.reasons
        ):
            return VideoTurnArtifact(
                turn_id=turn_id,
                status=VideoArtifactStatus.INSUFFICIENT_EVIDENCE,
                captured_frame_count=len(frames),
                quality=report.quality,
                quality_reasons=report.reasons,
            )
        return self._frame_exporter.export(
            turn_id,
            frames,
            quality=report.quality,
            quality_reasons=report.reasons,
        )
