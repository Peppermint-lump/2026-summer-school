from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.backend.app.avatar.state_mapper import AvatarStateMapper
from apps.backend.app.debug.trace_store import DebugTraceStore
from apps.backend.app.fusion.service import EmotionFusionService
from apps.backend.app.integration.loopback_server import LoopbackEmotionServer
from packages.schemas import (
    EmotionLabel,
    EmotionStatus,
    EmotionTurnAnalysis,
    EmotionTurnResult,
    ModalityEmotion,
    TurnRecord,
)


class FakeMiddleware:
    async def analyze_turn(self, turn: TurnRecord) -> EmotionTurnResult:
        observations = (
            ModalityEmotion.text_result(
                label=EmotionLabel.POSITIVE,
                confidence=0.9,
                quality=0.9,
                status=EmotionStatus.OK,
                fine_emotion="happy",
            ),
            ModalityEmotion.audio_result(
                label=EmotionLabel.UNCERTAIN,
                confidence=0.0,
                quality=0.0,
                status=EmotionStatus.INSUFFICIENT_EVIDENCE,
                evidence=("audio_missing",),
            ),
            ModalityEmotion.video_result(
                label=EmotionLabel.UNCERTAIN,
                confidence=0.0,
                quality=0.0,
                status=EmotionStatus.DISABLED,
            ),
        )
        analysis = EmotionTurnAnalysis(
            observations=observations,
            fusion=EmotionFusionService().fuse(observations),
        )
        return EmotionTurnResult(
            analysis=analysis,
            avatar_state=AvatarStateMapper().map(analysis),
        )


class FakeRuntime:
    middleware = FakeMiddleware()
    camera_enabled = False


class LoopbackTraceTests(unittest.TestCase):
    def test_every_canonical_stage_is_written_without_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = object.__new__(LoopbackEmotionServer)
            server._runtime = FakeRuntime()  # type: ignore[attr-defined]
            server._runtime_root = root / "runtime"  # type: ignore[attr-defined]
            server._trace_store = DebugTraceStore(  # type: ignore[attr-defined]
                root / "debug"
            )

            result = server._analyze_payload(  # type: ignore[attr-defined]
                {
                    "session_id": "session_1",
                    "turn_id": "turn_1",
                    "speech_start_ms": 1,
                    "speech_end_ms": 2,
                    "transcript": "private transcript sentinel",
                    "audio_wav_base64": None,
                }
            )

            trace_directory = Path(result["trace_directory"])
            self.assertEqual(
                {path.name for path in trace_directory.glob("*.json")},
                {
                    "00_request.json",
                    "01_text_observation.json",
                    "02_audio_observation.json",
                    "03_video_observation.json",
                    "04_fusion.json",
                    "05_avatar_state.json",
                    "06_cleanup.json",
                    "summary.json",
                },
            )
            request_text = (trace_directory / "00_request.json").read_text()
            self.assertNotIn("private transcript sentinel", request_text)
            avatar = json.loads(
                (trace_directory / "05_avatar_state.json").read_text()
            )
            self.assertEqual(avatar["expression"], "heart")
            self.assertEqual(result["analysis"]["fusion"]["fused_label"], "uncertain")


if __name__ == "__main__":
    unittest.main()
