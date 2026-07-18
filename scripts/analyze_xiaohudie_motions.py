"""Report Xiaohudie motion targets, endpoints, fades, and Idle coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DIRECTORY = Path(
    "third_party/Open-LLM-VTuber/live2d-models/xiaohudie/runtime/motions"
)
MOTION_NAMES = (
    "idle.motion3.json",
    "greeting.motion3.json",
    "catch_butterfly.motion3.json",
    "hold_bear.motion3.json",
)


def curve_endpoint(curve: dict[str, Any]) -> float | None:
    segments = curve.get("Segments", [])
    return segments[-1] if segments else None


def segment_count(curve: dict[str, Any]) -> int:
    segments = curve.get("Segments", [])
    offset = 2
    count = 0
    while offset < len(segments):
        segment_type = int(segments[offset])
        offset += 7 if segment_type == 1 else 3
        count += 1
    if offset != len(segments):
        raise ValueError(f"Malformed segments for curve {curve.get('Id')}")
    return count


def analyze(directory: Path) -> dict[str, Any]:
    motions = {
        name: json.loads((directory / name).read_text(encoding="utf-8"))
        for name in MOTION_NAMES
    }
    idle_targets = {
        (curve["Target"], curve["Id"])
        for curve in motions["idle.motion3.json"].get("Curves", [])
    }

    report: dict[str, Any] = {}
    for name, motion in motions.items():
        meta = motion.get("Meta", {})
        curves = []
        for curve in motion.get("Curves", []):
            target = (curve["Target"], curve["Id"])
            curves.append(
                {
                    "target": curve["Target"],
                    "id": curve["Id"],
                    "first_value": curve.get("Segments", [None, None])[1],
                    "last_value": curve_endpoint(curve),
                    "fade_in_time": curve.get("FadeInTime"),
                    "fade_out_time": curve.get("FadeOutTime"),
                    "covered_by_idle": target in idle_targets,
                }
            )
        report[name] = {
            "duration": meta.get("Duration"),
            "loop": meta.get("Loop"),
            "fade_in_time": meta.get("FadeInTime"),
            "fade_out_time": meta.get("FadeOutTime"),
            "curve_count": len(curves),
            "total_segment_count": sum(
                segment_count(curve) for curve in motion.get("Curves", [])
            ),
            "curves": curves,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    output = json.dumps(analyze(args.directory), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
