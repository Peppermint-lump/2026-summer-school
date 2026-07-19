"""Observable, metadata-only debug orchestration for text and video emotion."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from apps.backend.app.capture.camera_buffer import CameraBuffer
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.capture.video_export import FrameEncodingError
from apps.backend.app.emotion.text.service import TextEmotionService
from apps.backend.app.emotion.video.face_quality import FaceQualityEvaluator
from apps.backend.app.emotion.video.preprocess import VideoTurnPreprocessor
from apps.backend.app.emotion.video.service import VideoEmotionService
from apps.backend.app.fusion.service import EmotionFusionService
from packages.schemas import (
    ConflictResult,
    ModalityEmotion,
    TurnRecord,
    VideoArtifactStatus,
    VideoTurnArtifact,
)

from .trace_store import DebugTraceStore

ProgressCallback = Callable[[str], None]


class EmotionDebugPipeline:
    """Capture one future window, analyze independent modalities, then fuse."""

    def __init__(
        self,
        *,
        camera: CameraBuffer,
        quality_evaluator: FaceQualityEvaluator,
        video_preprocessor: VideoTurnPreprocessor,
        video_service: VideoEmotionService,
        text_service: TextEmotionService,
        fusion_service: EmotionFusionService,
        media_cleaner: TurnMediaCleaner,
        trace_store: DebugTraceStore,
    ) -> None:
        self._camera = camera
        self._quality_evaluator = quality_evaluator
        self._video_preprocessor = video_preprocessor
        self._video_service = video_service
        self._text_service = text_service
        self._fusion_service = fusion_service
        self._media_cleaner = media_cleaner
        self._trace_store = trace_store

    def analyze(
        self,
        *,
        duration_seconds: float,
        transcript: str | None,
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        if not 1.0 <= duration_seconds <= 15.0:
            raise ValueError("duration_seconds must be between 1 and 15")
        normalized_transcript = transcript.strip() if transcript else None
        start_ms = time.time_ns() // 1_000_000
        turn_id = f"debug_{start_ms}"
        turn = TurnRecord(
            session_id="camera_preview_debug",
            turn_id=turn_id,
            speech_start_ms=start_ms,
            speech_end_ms=start_ms,
            transcript=normalized_transcript,
        )
        self._trace_store.write_stage(
            turn_id,
            "00_request.json",
            {
                "schema_version": "1.0",
                "session_id": turn.session_id,
                "turn_id": turn.turn_id,
                "capture_duration_seconds": duration_seconds,
                "transcript_provided": normalized_transcript is not None,
                "transcript_character_count": len(normalized_transcript or ""),
                "audio_included": False,
                "raw_media_retained": False,
            },
        )

        progress("capturing")
        time.sleep(duration_seconds)
        end_ms = time.time_ns() // 1_000_000
        turn = TurnRecord(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            speech_start_ms=start_ms,
            speech_end_ms=end_ms,
            transcript=normalized_transcript,
        )
        frames = self._camera.frames_between(start_ms, end_ms)
        quality_report = self._quality_evaluator.evaluate(frames)
        self._trace_store.write_stage(
            turn_id,
            "01_capture_quality.json",
            {
                "schema_version": "1.0",
                "turn_id": turn_id,
                **asdict(quality_report),
                "capture_start_ms": start_ms,
                "capture_end_ms": end_ms,
            },
        )

        progress("preprocessing")
        cleanup_payload: dict[str, Any]
        try:
            artifact = self._prepare_artifact(turn)
            self._trace_store.write_stage(
                turn_id,
                "02_frame_sampling.json",
                _artifact_payload(artifact),
            )
            progress("provider_analysis")
            video_result, text_result = asyncio.run(
                self._analyze_modalities(artifact, turn)
            )
            self._trace_store.write_stage(
                turn_id,
                "03_video_observation.json",
                _observation_payload(video_result),
            )
            self._trace_store.write_stage(
                turn_id,
                "04_text_observation.json",
                _observation_payload(text_result),
            )
            progress("fusion")
            fusion = self._fusion_service.fuse((text_result, video_result))
            fusion_payload = _fusion_payload(fusion)
            self._trace_store.write_stage(
                turn_id,
                "05_fusion.json",
                fusion_payload,
            )
        finally:
            try:
                removed = self._media_cleaner.cleanup_turn(turn_id)
                cleanup_payload = {
                    "schema_version": "1.0",
                    "turn_id": turn_id,
                    "status": "completed",
                    "temporary_media_removed": removed,
                    "raw_media_may_remain": False,
                }
            except OSError:
                cleanup_payload = {
                    "schema_version": "1.0",
                    "turn_id": turn_id,
                    "status": "error",
                    "temporary_media_removed": False,
                    "raw_media_may_remain": True,
                }
            self._trace_store.write_stage(
                turn_id,
                "06_cleanup.json",
                cleanup_payload,
            )

        summary = {
            "schema_version": "1.0",
            "turn_id": turn_id,
            "trace_directory": str(self._trace_store.turn_directory(turn_id)),
            "capture": {
                "total_frames": quality_report.total_frames,
                "valid_face_frames": quality_report.valid_face_frames,
                "quality": quality_report.quality,
                "reasons": list(quality_report.reasons),
            },
            "video": _observation_payload(video_result),
            "text": _observation_payload(text_result),
            "fusion": fusion_payload,
            "audio": {
                "status": "not_provided_by_camera_preview",
                "included_in_fusion": False,
            },
            "cleanup": cleanup_payload,
            "raw_media_retained": cleanup_payload["raw_media_may_remain"],
        }
        self._trace_store.write_stage(turn_id, "summary.json", summary)
        progress("completed")
        return summary

    def _prepare_artifact(self, turn: TurnRecord) -> VideoTurnArtifact:
        try:
            return self._video_preprocessor.prepare(
                turn.turn_id,
                turn.speech_start_ms,
                turn.speech_end_ms,
            )
        except (FrameEncodingError, OSError):
            return VideoTurnArtifact(
                turn_id=turn.turn_id,
                status=VideoArtifactStatus.CAPTURE_ERROR,
                quality_reasons=("video_capture_error",),
            )

    async def _analyze_modalities(
        self,
        artifact: VideoTurnArtifact,
        turn: TurnRecord,
    ) -> tuple[ModalityEmotion, ModalityEmotion]:
        return await asyncio.gather(
            self._video_service.analyze(artifact),
            self._text_service.analyze(
                turn_id=turn.turn_id,
                transcript=turn.transcript,
            ),
        )


def _artifact_payload(artifact: VideoTurnArtifact) -> dict[str, Any]:
    return {
        "schema_version": artifact.schema_version,
        "turn_id": artifact.turn_id,
        "status": artifact.status.value,
        "captured_frame_count": artifact.captured_frame_count,
        "sampled_frame_count": artifact.sampled_frame_count,
        "quality": artifact.quality,
        "quality_reasons": list(artifact.quality_reasons),
        "provider_upload_frame_count": len(artifact.frame_paths),
        "frame_paths_recorded": False,
        "raw_media_retained_after_analysis": False,
    }


def _observation_payload(observation: ModalityEmotion) -> dict[str, Any]:
    return {
        "schema_version": observation.schema_version,
        "modality": observation.modality.value,
        "label": observation.label.value,
        "fine_emotion": observation.fine_emotion,
        "confidence": observation.confidence,
        "quality": observation.quality,
        "reliability": observation.reliability,
        "status": observation.status.value,
        "evidence": list(observation.evidence),
        "observed_actions": [
            {
                "type": action.action.value,
                "confidence": action.confidence,
                "evidence": action.evidence,
            }
            for action in observation.observed_actions
        ],
        "provider": observation.raw_metadata.get("provider"),
        "model": observation.raw_metadata.get("model"),
        "prompt_version": observation.raw_metadata.get("prompt_version"),
        "action_emotion_weight": observation.raw_metadata.get("action_emotion_weight"),
    }


def _fusion_payload(fusion: ConflictResult) -> dict[str, Any]:
    return {
        "schema_version": fusion.schema_version,
        "final_emotion": fusion.fused_label.value,
        "weighted_score": fusion.weighted_score,
        "conflict": fusion.conflict,
        "conflict_type": fusion.conflict_type.value,
        "conflict_score": fusion.conflict_score,
        "reliable_modalities": [item.value for item in fusion.reliable_modalities],
        "strategy": fusion.strategy.value,
        "explanation": fusion.explanation,
    }
