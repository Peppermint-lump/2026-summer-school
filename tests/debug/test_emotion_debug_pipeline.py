from __future__ import annotations

import json
import tempfile
import time
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import numpy as np
from numpy.typing import NDArray

from apps.backend.app.capture.camera_buffer import CameraBuffer
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.debug.emotion_pipeline import EmotionDebugPipeline
from apps.backend.app.debug.trace_store import DebugTraceStore
from apps.backend.app.emotion.text.service import TextEmotionService
from apps.backend.app.emotion.video.face_quality import FaceBox, FaceQualityEvaluator
from apps.backend.app.emotion.video.preprocess import VideoTurnPreprocessor
from apps.backend.app.emotion.video.service import VideoEmotionService
from apps.backend.app.fusion.service import EmotionFusionService
from packages.schemas import (
    ActionType,
    EmotionLabel,
    EmotionStatus,
    ModalityEmotion,
    ObservedAction,
    VideoArtifactStatus,
    VideoTurnArtifact,
)


class SingleFaceDetector:
    def detect(self, _frame: NDArray[np.uint8]) -> Sequence[FaceBox]:
        return ((2, 2, 16, 16),)


class FakePreprocessor(VideoTurnPreprocessor):
    def __init__(self) -> None:
        pass

    def prepare(self, turn_id: str, start_ms: int, end_ms: int) -> VideoTurnArtifact:
        del start_ms, end_ms
        return VideoTurnArtifact(
            turn_id=turn_id,
            status=VideoArtifactStatus.OK,
            frame_paths=(Path("temporary-frame.jpg"),),
            captured_frame_count=1,
            sampled_frame_count=1,
            quality=0.9,
        )


class FakeVideoService(VideoEmotionService):
    def __init__(self) -> None:
        pass

    async def analyze(self, artifact: VideoTurnArtifact) -> ModalityEmotion:
        del artifact
        return ModalityEmotion.video_result(
            label=EmotionLabel.POSITIVE,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
            fine_emotion="happy",
            observed_actions=(
                ObservedAction(
                    action=ActionType.WAVE,
                    confidence=0.92,
                    evidence="hand moves side to side across ordered frames",
                ),
            ),
            raw_metadata={"provider": "fake", "prompt_version": "test"},
        )


class FakeTextService(TextEmotionService):
    def __init__(self) -> None:
        pass

    async def analyze(self, *, turn_id: str, transcript: str | None) -> ModalityEmotion:
        del turn_id, transcript
        return ModalityEmotion.text_result(
            label=EmotionLabel.POSITIVE,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
            fine_emotion="happy",
            raw_metadata={"provider": "fake", "prompt_version": "test"},
        )


class RecordingCleaner(TurnMediaCleaner):
    def __init__(self, runtime_root: Path) -> None:
        super().__init__(runtime_root)
        self.cleaned_turns: list[str] = []

    def cleanup_turn(self, turn_id: str) -> bool:
        self.cleaned_turns.append(turn_id)
        return False


class EmotionDebugPipelineTests(unittest.TestCase):
    def test_writes_every_metadata_stage_and_cleans_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            camera = CameraBuffer()
            evaluator = FaceQualityEvaluator(SingleFaceDetector())
            cleaner = RecordingCleaner(root / "runtime")

            def append_captured_frame(_duration: float) -> None:
                grid = np.indices((24, 24)).sum(axis=0) % 2
                frame = np.repeat(
                    ((grid * 160 + 40).astype(np.uint8))[:, :, None], 3, 2
                )
                camera.append_frame(time.time_ns() // 1_000_000, frame)

            pipeline = EmotionDebugPipeline(
                camera=camera,
                quality_evaluator=evaluator,
                video_preprocessor=FakePreprocessor(),
                video_service=FakeVideoService(),
                text_service=FakeTextService(),
                fusion_service=EmotionFusionService(),
                media_cleaner=cleaner,
                trace_store=DebugTraceStore(root / "debug"),
            )
            states: list[str] = []
            with patch(
                "apps.backend.app.debug.emotion_pipeline.time.sleep",
                side_effect=append_captured_frame,
            ):
                result = pipeline.analyze(
                    duration_seconds=5,
                    transcript="今天很开心",
                    progress=states.append,
                )

            turn_directory = Path(result["trace_directory"])
            self.assertEqual(
                {path.name for path in turn_directory.glob("*.json")},
                {
                    "00_request.json",
                    "01_capture_quality.json",
                    "02_frame_sampling.json",
                    "03_video_observation.json",
                    "04_text_observation.json",
                    "05_fusion.json",
                    "06_cleanup.json",
                    "summary.json",
                },
            )
            video = json.loads(
                (turn_directory / "03_video_observation.json").read_text()
            )
            self.assertEqual(video["observed_actions"][0]["type"], "wave")
            self.assertEqual(result["fusion"]["final_emotion"], "positive")
            self.assertEqual(
                result["audio"]["status"], "not_provided_by_camera_preview"
            )
            self.assertFalse(result["raw_media_retained"])
            self.assertEqual(cleaner.cleaned_turns, [result["turn_id"]])
            self.assertEqual(states[-1], "completed")


if __name__ == "__main__":
    unittest.main()
