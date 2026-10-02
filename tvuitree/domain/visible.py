"""Compact observation of controls currently represented on screen."""

from __future__ import annotations

from tvuitree.domain.observation import node_summary


SCHEMA_VERSION = "tv-visible/v1"


def _intersects_screen(bounds: object, width: int, height: int) -> bool:
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return False
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in bounds):
        return False
    left, top, right, bottom = bounds
    return (right > left and bottom > top and right > 0 and bottom > 0
            and left < width and top < height)


def _path_text(path: tuple[int, ...]) -> str:
    return "/".join(str(part) for part in path)


def _truncated_prefix(text: str) -> str | None:
    if text.endswith("..."):
        return text[:-3].rstrip()
    if text.endswith("…"):
        return text[:-1].rstrip()
    return None


def _visible_labels(node: dict) -> list[str]:
    value = node.get("text")
    return [value.strip()] if isinstance(value, str) and value.strip() else []


def select_visible(full_json: dict) -> dict:
    """Summarize visible a11y controls while retaining focus and actions.

    Paths refer to the original full tree; only a11y screen readings establish
    visibility, and dumpsys geometry never becomes a claimed screen reading.
    """
    if not isinstance(full_json, dict) or not isinstance(full_json.get("tree"), list):
        raise ValueError("输入不是本工具生成的 full JSON：缺少 tree")
    screen = full_json.get("screen") or {}
    width, height = screen.get("width"), screen.get("height")
    if (not isinstance(width, int) or isinstance(width, bool) or width <= 0
            or not isinstance(height, int) or isinstance(height, bool) or height <= 0):
        raise ValueError("full JSON 缺少有效的 screen.width 和 screen.height")

    entries: list[tuple[tuple[int, ...], dict]] = []

    def walk(nodes: list, parent: tuple[int, ...] = ()) -> None:
        for index, node in enumerate(nodes):
            if (node.get("visible_to_user") is False or node.get("visible") is False
                    or node.get("gone") is True):
                continue
            path = parent + (index,)
            if (node.get("source") == "a11y"
                    and _intersects_screen(node.get("bounds_screen"), width, height)):
                entries.append((path, node))
            walk(node.get("children") or [], path)

    walk(full_json["tree"])
    by_path = dict(entries)
    order = {path: index for index, (path, _node) in enumerate(entries)}

    def group_candidate(path: tuple[int, ...], node: dict) -> bool:
        if any(node.get(key) is True for key in
               ("clickable", "long_clickable", "checkable", "focused")):
            return True
        if node.get("focusable") is not True:
            return False
        # Small focusable detail panels form one item; large scroll containers
        # holding many independent rows do not.
        labels = sum(1 for other_path, other in entries
                     if other_path[:len(path)] == path and _visible_labels(other))
        return 1 <= labels <= 3

    groups = {path for path, node in entries if group_candidate(path, node)}
    labels_by_path: dict[tuple[int, ...], list[str]] = {}
    descriptions_by_path: dict[tuple[int, ...], list[str]] = {}
    for path, node in entries:
        labels = _visible_labels(node)
        owner = next((path[:end] for end in range(len(path), 0, -1)
                      if path[:end] in groups), path)
        if labels:
            target = labels_by_path.setdefault(owner, [])
            for label in labels:
                if label not in target:
                    target.append(label)
        elif owner in groups:
            description = node.get("content_desc")
            if isinstance(description, str) and description.strip():
                target = descriptions_by_path.setdefault(owner, [])
                if description.strip() not in target:
                    target.append(description.strip())

    focused_paths = [path for path, node in entries if node.get("focused") is True]
    targets = set(labels_by_path) | set(descriptions_by_path) | set(focused_paths)
    complete = [label for labels in labels_by_path.values() for label in labels
                if _truncated_prefix(label) is None]
    page_nodes = []
    for path in sorted(targets, key=order.__getitem__):
        raw = node_summary(by_path[path], path)
        summary = {key: raw[key] for key in
                   ("path", "source", "class", "resource_id", "bounds", "bounds_kind",
                    "actions", "focused", "selected", "checked", "enabled")
                   if key in raw and (key not in ("focused", "selected", "checked")
                                      or raw[key] is True)
                   and (key != "enabled" or raw[key] is False)}
        labels = [label for label in labels_by_path.get(path, [])
                  if not (prefix := _truncated_prefix(label))
                  or not any(text.startswith(prefix) and text != label for text in complete)]
        if labels:
            summary["labels"] = labels
        elif descriptions_by_path.get(path):
            summary["accessibility_labels"] = descriptions_by_path[path]
        if labels or path in focused_paths or "accessibility_labels" in summary:
            page_nodes.append(summary)

    if len(focused_paths) == 1:
        focus = {"status": "found", "path": _path_text(focused_paths[0])}
    elif focused_paths:
        focus = {"status": "ambiguous",
                 "paths": [_path_text(path) for path in focused_paths]}
    else:
        focus = {"status": "missing"}
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "visible",
        "captured_at": full_json.get("captured_at"),
        "screen": {"width": width, "height": height},
        "focus": focus,
        "page": {"nodes": page_nodes},
    }
