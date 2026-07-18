"""Project boundary helpers for raw visual input sent by the upstream UI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


RAW_VISUAL_INPUT_NOTICE = (
    "[System context: The companion model did not receive the camera image. "
    "Do not claim that you can see the user. If the user asks about vision, "
    "briefly explain that no visual analysis result is available for this turn.]"
)


def discard_raw_companion_images(
    images: Optional[List[Dict[str, Any]]],
    metadata: Optional[Dict[str, Any]],
) -> Tuple[None, Optional[Dict[str, Any]], int]:
    """Discard raw images and mark the turn for a safe text-only fallback."""
    if not images:
        return None, metadata, 0

    safe_metadata = dict(metadata or {})
    safe_metadata["raw_images_discarded"] = True
    return None, safe_metadata, len(images)


def add_visual_unavailable_context(
    input_text: str,
    metadata: Optional[Dict[str, Any]],
) -> str:
    """Add a non-user-visible guardrail after ASR and before the agent call."""
    if not metadata or not metadata.get("raw_images_discarded"):
        return input_text
    return f"{input_text}\n\n{RAW_VISUAL_INPUT_NOTICE}"
