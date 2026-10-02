#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""面向大模型的 TV 页面观察摘要与统一采集接口。"""

from __future__ import annotations

from typing import Any, Iterable, Optional


SCHEMA_VERSION = "tv-observation/v1"
DEFAULT_MAX_NODES = 80


def _walk(nodes: Iterable[dict], parent_path: tuple[int, ...] = ()):
    """按树顺序返回 ``(node, path, parent_path)``。"""
    for index, node in enumerate(nodes or []):
        path = parent_path + (index,)
        yield node, path, parent_path
        yield from _walk(node.get("children") or [], path)


def _path_text(path: tuple[int, ...]) -> str:
    return "/".join(str(part) for part in path) or "root"


def _labels(node: dict) -> list[str]:
    result = []
    for key in ("text", "content_desc", "hint"):
        value = node.get(key)
        if isinstance(value, str) and value.strip() and value not in result:
            result.append(value.strip())
    return result


def _is_true(node: dict, key: str) -> bool:
    return node.get(key) is True


def node_summary(node: dict, path: tuple[int, ...], *, include_children: bool = False) -> dict:
    """输出模型真正需要的节点字段，保留读数来源和坐标口径。"""
    result: dict[str, Any] = {
        "path": _path_text(path),
        "source": node.get("source"),
        "class": node.get("class"),
    }
    labels = _labels(node)
    if labels:
        result["labels"] = labels
    for key in ("resource_id", "package"):
        if node.get(key) is not None:
            result[key] = node[key]

    if node.get("bounds_screen") is not None:
        result["bounds"] = node["bounds_screen"]
        result["bounds_kind"] = "screen_reading"
    elif node.get("bounds_local") is not None:
        result["bounds"] = node["bounds_local"]
        result["bounds_kind"] = "local_reading"

    actions = []
    for key, label in (
        ("clickable", "click"),
        ("focusable", "focus"),
        ("long_clickable", "long_click"),
        ("scrollable", "scroll"),
        ("checkable", "check"),
    ):
        if _is_true(node, key):
            actions.append(label)
    if actions:
        result["actions"] = actions

    for key in ("focused", "selected", "checked", "enabled", "visible", "visible_to_user"):
        if key in node and (node[key] is True or key in ("focused", "selected", "checked")):
            result[key] = bool(node[key])

    children = node.get("children") or []
    if children:
        result["children_count"] = len(children)
    if include_children:
        result["children"] = [
            node_summary(child, path + (index,), include_children=False)
            for index, child in enumerate(children)
        ]
    return result


def _meaningful(node: dict) -> bool:
    """是否值得放进默认的页面摘要。"""
    return bool(
        _labels(node)
        or node.get("resource_id")
        or any(_is_true(node, key) for key in (
            "focused", "focusable", "clickable", "selected", "checkable", "scrollable",
        ))
    )


def _focus_context(items: list[tuple[dict, tuple[int, ...], tuple[int, ...]]],
                   focus_path: tuple[int, ...]) -> dict:
    by_path = {path: (node, path, parent) for node, path, parent in items}
    focus_item = by_path.get(focus_path)
    if focus_item is None:
        return {"ancestors": [], "siblings": [], "children": []}

    node, path, parent = focus_item
    ancestors = []
    for end in range(1, len(path)):
        ancestor_path = path[:end]
        ancestor = by_path.get(ancestor_path)
        if ancestor:
            ancestors.append(node_summary(ancestor[0], ancestor_path))

    siblings = []
    for sibling, sibling_path, sibling_parent in items:
        if sibling_parent == parent and sibling_path != path and _meaningful(sibling):
            siblings.append(node_summary(sibling, sibling_path))

    children = [
        node_summary(child, path + (index,))
        for index, child in enumerate(node.get("children") or [])
        if _meaningful(child) or _is_true(child, "focused")
    ]
    return {"ancestors": ancestors, "siblings": siblings, "children": children}


def _warnings(full_json: dict, parse_anomalies: Optional[list] = None) -> list[str]:
    warnings = []
    consistency = full_json.get("source_consistency") or {}
    if consistency.get("drift"):
        warnings.append(consistency.get("detail") or "两次 dumpsys 之间 View 层次发生变化")
    stats = full_json.get("align_stats") or {}
    for key in ("align_skipped", "window_note"):
        if stats.get(key):
            warnings.append(str(stats[key]))
    if full_json.get("segment_match_note"):
        warnings.append(str(full_json["segment_match_note"]))
    for item in parse_anomalies or []:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            warnings.append(f"第 {item[0]} 行解析告警：{item[2]}")
    return list(dict.fromkeys(warnings))


def summarize_full_json(full_json: dict, *, max_nodes: int = DEFAULT_MAX_NODES,
                        parse_anomalies: Optional[list] = None) -> dict:
    """把一份 full JSON 转成模型默认观察结果。

    ``max_nodes`` 只限制页面摘要，不影响焦点上下文或证据统计。
    """
    if not isinstance(full_json, dict) or not isinstance(full_json.get("tree"), list):
        raise ValueError("输入不是本工具生成的 full JSON：缺少 tree")
    max_nodes = max(1, int(max_nodes))
    items = list(_walk(full_json.get("tree") or []))
    focused = [(node, path, parent) for node, path, parent in items if _is_true(node, "focused")]
    top_focus = full_json.get("focus") or []
    candidate_count = max(len(focused), len(top_focus))

    if candidate_count == 1:
        focus_status = "found"
    elif candidate_count > 1:
        focus_status = "ambiguous"
    else:
        focus_status = "missing"

    candidates = []
    for node, path, _parent in focused:
        candidates.append(node_summary(node, path, include_children=False))
    if not candidates and candidate_count:
        for index, item in enumerate(top_focus):
            if isinstance(item, dict):
                candidate = dict(item)
                candidate["candidate_index"] = index
                candidates.append(candidate)

    focus: dict[str, Any] = {
        "status": focus_status,
        "candidate_count": candidate_count,
        "candidates": candidates,
    }
    if focus_status == "found" and focused:
        focus["node"] = candidates[0]
        focus["context"] = _focus_context(items, focused[0][1])
    elif focus_status == "ambiguous":
        focus["reason"] = "a11y 树中存在多个 focused 节点，工具不选择其中一个"
    else:
        focus["reason"] = "当前 a11y 树没有 focused 节点"

    page_nodes = []
    included_paths = set()
    for node, path, _parent in items:
        if _meaningful(node) and path not in included_paths:
            page_nodes.append(node_summary(node, path))
            included_paths.add(path)
        if len(page_nodes) >= max_nodes:
            break
    if not page_nodes and items:
        node, path, _parent = items[0]
        page_nodes.append(node_summary(node, path))

    stats = full_json.get("align_stats") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "observe",
        "captured_at": full_json.get("captured_at"),
        "device": full_json.get("device") or {},
        "screen": full_json.get("screen") or {},
        "window": full_json.get("window") or {},
        "page": {
            "package": full_json.get("segment"),
            "node_count": len(items),
            "summary_node_count": len(page_nodes),
            "summary_truncated": len(page_nodes) < sum(1 for node, _path, _parent in items if _meaningful(node)),
            "nodes": page_nodes,
        },
        "focus": focus,
        "evidence": {
            "align_rules": full_json.get("align_rules") or {},
            "align_stats": stats,
            "source_consistency": full_json.get("source_consistency") or {},
            "segment_match_note": full_json.get("segment_match_note"),
        },
        "warnings": _warnings(full_json, parse_anomalies),
        "full_tree_available": True,
    }


def error_observation(error: BaseException | str) -> dict:
    """将实时采集异常转成 MCP 可返回的结构化结果。"""
    message = str(error)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "observe",
        "focus": {
            "status": "error",
            "candidate_count": 0,
            "candidates": [],
            "reason": message,
        },
        "page": {"package": None, "node_count": 0, "summary_node_count": 0,
                 "summary_truncated": False, "nodes": []},
        "warnings": [message],
        "full_tree_available": False,
    }
