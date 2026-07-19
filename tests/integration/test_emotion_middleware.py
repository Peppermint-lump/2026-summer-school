from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.backend.app.avatar.state_mapper import AvatarStateMapper
from apps.backend.app.capture.media_cleanup import TurnMediaCleaner
from apps.backend.app.fusion.service import EmotionFusionService
from apps.backend.app.integration.emotion_middleware import EmotionMiddleware
from packages.schemas import (
    ConflictType,
    EmotionLabel,
    EmotionStatus,
    Modality,
    ModalityEmotion,
    TurnRecord,
)


class FakeTextService:
    async def analyze(self, *, turn_id: str, transcript: str | None) -> ModalityEmotion:
        assert turn_id == "turn_1"
        assert transcript == "我很好"
        return ModalityEmotion.text_result(
            label=EmotionLabel.POSITIVE,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
        )


class FakeVideoMiddleware:
    async def analyze_turn(self, turn: TurnRecord) -> ModalityEmotion:
        assert turn.turn_id == "turn_1"
        return ModalityEmotion.video_result(
            label=EmotionLabel.NEGATIVE,
            confidence=0.9,
            quality=0.9,
            status=EmotionStatus.OK,
        )


class FakeAudioService:
    async def analyze(self, *, turn_id: str, audio_path: object) -> ModalityEmotion:
        assert turn_id == "turn_1"
        assert audio_path is None
        return ModalityEmotion.audio_result(
            label=EmotionLabel.NEUTRAL,
            confidence=0.8,
            quality=0.8,
            status=EmotionStatus.OK,
        )


class EmotionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_typed_text_and_visual_observations_fuse_without_audio(self) -> None:
        class MissingAudioService:
            async def analyze(
                self, *, turn_id: str, audio_path: object
            ) -> ModalityEmotion:
                self_test.assertEqual(turn_id, "turn_1")
                self_test.assertIsNone(audio_path)
                return ModalityEmotion.audio_result(
                    label=EmotionLabel.UNCERTAIN,
                    confidence=0.0,
                    quality=0.0,
                    status=EmotionStatus.INSUFFICIENT_EVIDENCE,
                )

        self_test = self
        middleware = EmotionMiddleware(  # type: ignore[arg-type]
            FakeTextService(),
            MissingAudioService(),  # type: ignore[arg-type]
            FakeVideoMiddleware(),
            EmotionFusionService(),
            AvatarStateMapper(),
        )

        result = await middleware.analyze_turn(
            TurnRecord(
                session_id="session_1",
                turn_id="turn_1",
                speech_start_ms=300,
                speech_end_ms=300,
                visual_start_ms=100,
                visual_end_ms=300,
                transcript="我很好",
            )
        )

        self.assertEqual(
            result.analysis.fusion.reliable_modalities,
            (Modality.TEXT, Modality.VIDEO),
        )
        self.assertEqual(
            result.analysis.fusion.conflict_type,
            ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE,
        )

    async def test_independent_results_are_fused_after_both_complete(self) -> None:
        middleware = EmotionMiddleware(  # type: ignore[arg-type]
            FakeTextService(),
            FakeAudioService(),  # type: ignore[arg-type]
            FakeVideoMiddleware(),
            EmotionFusionService(),
            AvatarStateMapper(),
        )
        result = await middleware.analyze_turn(
            TurnRecord(
                session_id="session_1",
                turn_id="turn_1",
                speech_start_ms=1,
                speech_end_ms=2,
                transcript="我很好",
            )
        )

        self.assertEqual(len(result.analysis.observations), 3)
        self.assertEqual(
            result.analysis.fusion.conflict_type,
            ConflictType.VERBAL_POSITIVE_BEHAVIOR_NEGATIVE,
        )
        self.assertEqual(
            result.avatar_state.source_label,
            result.analysis.fusion.fused_label,
        )

    async def test_turn_media_is_cleaned_only_after_audio_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime"
            turn_directory = runtime_root / "turns" / "turn_1"
            turn_directory.mkdir(parents=True)
            audio_path = turn_directory / "audio.wav"
            audio_path.write_bytes(b"temporary audio")

            class FileAwareAudioService:
                async def analyze(
                    self, *, turn_id: str, audio_path: object
                ) -> ModalityEmotion:
                    self_test.assertEqual(turn_id, "turn_1")
                    self_test.assertIsInstance(audio_path, Path)
                    assert isinstance(audio_path, Path)
                    self_test.assertTrue(audio_path.exists())
                    return ModalityEmotion.audio_result(
                        label=EmotionLabel.NEUTRAL,
                        confidence=0.8,
                        quality=0.8,
                        status=EmotionStatus.OK,
                    )

            self_test = self
            middleware = EmotionMiddleware(  # type: ignore[arg-type]
                FakeTextService(),
                FileAwareAudioService(),  # type: ignore[arg-type]
                FakeVideoMiddleware(),
                EmotionFusionService(),
                AvatarStateMapper(),
                media_cleaner=TurnMediaCleaner(runtime_root),
            )
            await middleware.analyze_turn(
                TurnRecord(
                    session_id="session_1",
                    turn_id="turn_1",
                    speech_start_ms=1,
                    speech_end_ms=2,
                    audio_path=audio_path,
                    transcript="我很好",
                )
            )
            self.assertFalse(turn_directory.exists())


if __name__ == "__main__":
    unittest.main()
