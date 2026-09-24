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


@mcp.tool()
def get_current_focus(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = True,
) -> dict:
    """只返回当前 TV 的焦点状态、节点及候选信息；默认只读 a11y。"""
    try:
        device, target = _connect(
            TV_IP_Address=TV_IP_Address, port=port, adb=adb,
            no_connect=no_connect,
        )
        if device is None:
            return error_observation(f"无法连接 TV：{target}")["focus"]
        return collect_observation(
            adb=device, serial=device.serial, quiet=True,
            use_dumpsys=not no_dumpsys,
        )["focus"]
    except Exception as exc:
        return error_observation(exc)["focus"]


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
            "focus": observation["focus"],
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
