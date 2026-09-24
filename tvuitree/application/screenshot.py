"""Coordinate screenshot selection and rendering without CLI concerns."""

from __future__ import annotations

from tvuitree.domain.screenshot import collect, compare_focus
from tvuitree.infrastructure.image import draw_boxes, draw_boxes_png, focus_border_width


def render(obj: dict, png: bytes, out_path: str, *, draw: str = "focus",
           source: str = "a11y", width: int = 1,
           show_details: bool = True) -> dict:
    boxes, warnings = collect(obj, draw, source)
    drawn, skipped, notes = draw_boxes(
        png, boxes, out_path, obj.get("screen") or {}, width,
        show_details=show_details,
    )
    return {
        "boxes": boxes, "warnings": warnings, "drawn": drawn,
        "skipped": skipped, "notes": notes,
        "focus_lines": compare_focus(obj) if draw == "focus" else [],
    }


def render_focus_png(obj: dict, png: bytes) -> tuple[bytes, dict]:
    """Draw one red a11y focus border, or return the original PNG if ambiguous."""
    boxes, warnings = collect(obj, "focus", "a11y")
    if len(boxes) != 1:
        return png, {
            "boxes": boxes, "warnings": warnings, "drawn": 0,
            "skipped": len(boxes), "notes": [],
        }
    image, drawn, skipped, notes = draw_boxes_png(
        png, boxes, obj.get("screen") or {},
        width=focus_border_width(png), show_details=False,
    )
    return image, {
        "boxes": boxes, "warnings": warnings, "drawn": drawn,
        "skipped": skipped, "notes": notes,
    }
