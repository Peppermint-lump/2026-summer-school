"""Deterministic local quality checks for turn-scoped PCM WAV audio."""

from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudioQualityReport:
    quality: float
    duration_seconds: float
    rms_level: float
    clipping_ratio: float
    reasons: tuple[str, ...] = ()


class AudioQualityEvaluator:
    """Estimate usability without transcribing or interpreting speech."""

    def evaluate(self, audio_path: Path) -> AudioQualityReport:
        if not audio_path.is_file():
            return _empty_report("audio_missing")
        try:
            with wave.open(str(audio_path), "rb") as audio:
                if audio.getcomptype() != "NONE" or audio.getsampwidth() != 2:
                    return _empty_report("unsupported_audio_quality_format")
                frame_rate = audio.getframerate()
                frame_count = audio.getnframes()
                channels = audio.getnchannels()
                if frame_rate <= 0 or frame_count <= 0 or channels <= 0:
                    return _empty_report("audio_empty")
                raw_audio = audio.readframes(frame_count)
        except (OSError, EOFError, wave.Error):
            return _empty_report("audio_unreadable")

        samples = array("h")
        samples.frombytes(raw_audio)
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            return _empty_report("audio_empty")

        duration_seconds = frame_count / frame_rate
        normalized = [sample / 32768.0 for sample in samples]
        rms_level = math.sqrt(
            sum(sample * sample for sample in normalized) / len(normalized)
        )
        clipping_ratio = sum(abs(sample) >= 0.98 for sample in normalized) / len(
            normalized
        )
        reasons: list[str] = []
        if duration_seconds < 0.25:
            reasons.append("audio_too_short")
        if rms_level < 0.008:
            reasons.append("audio_level_too_low")
        if clipping_ratio > 0.05:
            reasons.append("audio_clipping")

        duration_score = min(1.0, duration_seconds / 1.0)
        level_score = min(1.0, max(0.0, (rms_level - 0.003) / 0.05))
        clipping_score = max(0.0, 1.0 - clipping_ratio / 0.10)
        quality = round(duration_score * level_score * clipping_score, 4)
        return AudioQualityReport(
            quality=quality,
            duration_seconds=round(duration_seconds, 4),
            rms_level=round(rms_level, 6),
            clipping_ratio=round(clipping_ratio, 6),
            reasons=tuple(reasons),
        )


def _empty_report(reason: str) -> AudioQualityReport:
    return AudioQualityReport(
        quality=0.0,
        duration_seconds=0.0,
        rms_level=0.0,
        clipping_ratio=0.0,
        reasons=(reason,),
    )
