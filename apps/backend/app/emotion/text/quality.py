"""Local quality heuristic for ASR transcript evidence."""

from __future__ import annotations


def estimate_text_quality(transcript: str) -> float:
    stripped = transcript.strip()
    if not stripped:
        return 0.0
    meaningful = [character for character in stripped if character.isalnum()]
    if not meaningful:
        return 0.1
    length_score = min(1.0, len(meaningful) / 12.0)
    replacement_ratio = stripped.count("�") / len(stripped)
    quality = (0.4 + 0.6 * length_score) * (1.0 - replacement_ratio)
    return round(max(0.0, min(1.0, quality)), 4)
