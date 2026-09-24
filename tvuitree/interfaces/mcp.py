#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tv-uitree 的只读 MCP 服务。

宿主通过 stdio 启动本文件。服务只读取 TV 状态、完整树和截图，不发送按键，
与 CLI 共用应用层采集、观察摘要和截图绘制。
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from tvuitree.application.connection import connection_options, connect_device
from tvuitree.application.observation import collect_full_json, collect_observation
from tvuitree.application.screenshot import render_focus_png
from tvuitree.domain.observation import error_observation
from tvuitree.infrastructure.image import capture

try:
    from mcp.server.fastmcp import FastMCP, Image
except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
    raise SystemExit(
        "缺少 MCP 依赖，请在仓库环境执行：python -m pip install 'mcp>=1.28,<2'"
    ) from exc


mcp = FastMCP("tv-uitree")


def _connect(*, TV_IP_Address: Optional[str], port: Optional[int],
             adb: Optional[str], no_connect: bool):
    options = connection_options(
        TV_IP_Address=TV_IP_Address, port=port, adb=adb, no_connect=no_connect,
    )
    return connect_device(options, quiet=True), options.target


def _raw_node(full_json: Optional[dict], node: dict) -> Optional[dict]:
    """Resolve an observation path back into the captured full tree."""
    if not isinstance(full_json, dict) or not isinstance(node.get("path"), str):
        return None
    try:
        indices = [int(part) for part in node["path"].split("/")]
        current = full_json.get("tree") or []
        raw = current[indices[0]]
        for index in indices[1:]:
            current = raw.get("children") or []
            raw = current[index]
        return raw if isinstance(raw, dict) else None
    except (IndexError, TypeError, ValueError):
        return None


def _focus_labels(raw: Optional[dict], summary_node: Optional[dict] = None) -> dict:
    """Pick a short title and optional subtitle from the focused control subtree."""
    if not isinstance(raw, dict):
        labels = summary_node.get("labels") if isinstance(summary_node, dict) else None
        return {"label": labels[0]} if labels else {}
    entries = []

    def walk(current: dict) -> None:
        if current.get("visible") is False or current.get("visible_to_user") is False:
            return
        resource_id = str(current.get("resource_id") or "").rsplit("/", 1)[-1].lower()
        for key in ("text", "content_desc", "hint"):
            value = current.get(key)
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                if normalized not in [entry[0] for entry in entries]:
                    entries.append((normalized, resource_id))
        for child in current.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(raw)
    if not entries:
        return {}
    title_index = next(
        (i for i, (_value, rid) in enumerate(entries)
         if rid in ("title", "label", "text1")),
        0,
    )
    label = entries[title_index][0]
    summary_index = next(
        (i for i, (_value, rid) in enumerate(entries)
         if rid in ("summary", "subtitle", "description") and i != title_index),
        None,
    )
    result = {"label": label}
    if summary_index is not None:
        result["summary"] = entries[summary_index][0]
    other_text = [value for i, (value, _rid) in enumerate(entries)
                  if i != title_index and i != summary_index]
    if other_text:
        result["related_text"] = other_text[:3]
    return result


def _focus_info(focus: dict, full_json: Optional[dict] = None) -> dict:
    """Return the focused node and its visible semantic label, without tree context."""
    status = focus.get("status", "error")
    if status == "found":
        node = focus.get("node")
        if not isinstance(node, dict):
            candidates = focus.get("candidates") or []
            node = candidates[0] if candidates else {}
        fields = (
            "class", "resource_id", "package", "bounds",
            "bounds_kind", "source",
        )
        compact_node = {key: node[key] for key in fields if key in node}
        compact_node.update(_focus_labels(_raw_node(full_json, node), node))
        return {
            "status": status,
            "node": compact_node,
        }
    if status == "ambiguous":
        fields = (
            "class", "resource_id", "package", "bounds",
            "bounds_kind", "source",
        )
        candidates = [
            {
                **{key: node[key] for key in fields if key in node},
                **_focus_labels(_raw_node(full_json, node), node),
            }
            for node in focus.get("candidates", []) if isinstance(node, dict)
        ]
        return {
            "status": status,
            "candidate_count": focus.get("candidate_count", len(candidates)),
            "candidates": candidates,
            "reason": focus.get("reason"),
        }
    return {"status": status, "reason": focus.get("reason")}


@mcp.tool()
def get_current_focus(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = True,
) -> dict:
    """返回精简的当前焦点节点信息，不返回祖先、同级节点或子节点。"""
    try:
        device, target = _connect(
            TV_IP_Address=TV_IP_Address, port=port, adb=adb,
            no_connect=no_connect,
        )
        if device is None:
            return _focus_info(error_observation(f"无法连接 TV：{target}")["focus"])
        full = collect_full_json(
            adb=device, serial=device.serial, quiet=True,
            use_dumpsys=not no_dumpsys,
        )
        focus = collect_observation(full_json=full)["focus"]
        return _focus_info(focus, full)
    except Exception as exc:
        return _focus_info(error_observation(exc)["focus"])


@mcp.tool(structured_output=False)
def get_focus_screenshot(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = True,
) -> list:
    """返回当前 TV 截图的 PNG 图像，并用红框标出 a11y 焦点读数。"""
    try:
        device, target = _connect(
            TV_IP_Address=TV_IP_Address, port=port, adb=adb,
            no_connect=no_connect,
        )
        if device is None:
            return [{"error": f"无法连接 TV：{target}"}]
        full = collect_full_json(
            adb=device, serial=device.serial, quiet=True,
            use_dumpsys=not no_dumpsys,
        )
        observation = collect_observation(full_json=full)
        png = capture(device)
        screenshot_at = dt.datetime.now().isoformat(timespec="seconds")
        annotated_png, result = render_focus_png(full, png)
        if result["boxes"] and not result["drawn"]:
            return [{"error": "焦点框未能画到截图上", "notes": result["notes"]}]
        metadata = {
            "focus": _focus_info(observation["focus"], full),
            "captured_at": full.get("captured_at"),
            "screenshot_at": screenshot_at,
            "drawn": result["drawn"],
            "skipped": result["skipped"],
            "warnings": observation["warnings"],
            "notes": result["notes"],
        }
        if not result["boxes"]:
            metadata["notes"].append("当前 a11y 树没有可绘制的焦点屏幕坐标；截图未加框")
        return [metadata, Image(data=annotated_png, format="png")]
    except Exception as exc:
        return [{"error": str(exc), "error_type": type(exc).__name__}]


@mcp.tool()
def observe_tv(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = False,
    max_nodes: int = 80,
) -> dict:
    """读取当前 TV 焦点、精简页面节点和 R0–R3 证据。"""
    try:
        device, target = _connect(
            TV_IP_Address=TV_IP_Address, port=port, adb=adb,
            no_connect=no_connect,
        )
        if device is None:
            return error_observation(f"无法连接 TV：{target}")
        return collect_observation(
            adb=device, serial=device.serial, quiet=True,
            use_dumpsys=not no_dumpsys, max_nodes=max_nodes,
        )
    except Exception as exc:  # MCP 工具返回结构化错误，避免宿主丢失上下文
        return error_observation(exc)


@mcp.tool()
def get_full_tree(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = False,
) -> dict:
    """读取当前 TV 的完整控件树；需要详细诊断时使用。"""
    try:
        device, _target = _connect(
            TV_IP_Address=TV_IP_Address, port=port, adb=adb,
            no_connect=no_connect,
        )
        if device is None:
            return {"error": "无法连接 TV", "mode": "full"}
        full = collect_full_json(
            adb=device, serial=device.serial, quiet=True,
            use_dumpsys=not no_dumpsys,
        )
        full.pop("_parse_anomalies", None)
        return full
    except Exception as exc:  # MCP 工具返回可读错误，不向宿主泄漏 traceback
        return {"error": str(exc), "error_type": type(exc).__name__, "mode": "full"}
