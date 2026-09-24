"""Coordinate screenshot selection and rendering without CLI concerns."""

from __future__ import annotations

from tvuitree.domain.screenshot import collect, compare_focus
from tvuitree.infrastructure.image import draw_boxes


def render(obj: dict, png: bytes, out_path: str, *, draw: str = "focus",
           source: str = "a11y", width: int = 1) -> dict:
    boxes, warnings = collect(obj, draw, source)
    drawn, skipped, notes = draw_boxes(png, boxes, out_path, obj.get("screen") or {}, width)
    return {
        "boxes": boxes, "warnings": warnings, "drawn": drawn,
        "skipped": skipped, "notes": notes,
        "focus_lines": compare_focus(obj) if draw == "focus" else [],
    }
