"""Adapt Xiaohudie's VTube Studio toggle motions for one-shot web playback."""

from __future__ import annotations

import json
from pathlib import Path


MOTIONS_DIRECTORY = Path(
    "third_party/Open-LLM-VTuber/live2d-models/xiaohudie/runtime/motions"
)
MOTION_NAMES = (
    "greeting.motion3.json",
    "catch_butterfly.motion3.json",
    "hold_bear.motion3.json",
)


def make_one_shot(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.setdefault("Meta", {})
    if meta.get("Loop") is False:
        return False
    meta["Loop"] = False
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    return True


def main() -> None:
    for motion_name in MOTION_NAMES:
        path = MOTIONS_DIRECTORY / motion_name
        if not path.is_file():
            raise FileNotFoundError(f"Motion file not found: {path}")
        changed = make_one_shot(path)
        print(f"{motion_name}: {'updated' if changed else 'already one-shot'}")


if __name__ == "__main__":
    main()
