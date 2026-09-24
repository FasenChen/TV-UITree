#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tv-uitree 的只读 MCP 服务。

宿主通过 stdio 启动本文件。服务只暴露观察和完整树读取，不发送按键、不截图，
与 CLI 共用应用层采集与观察摘要。
"""

from __future__ import annotations

from typing import Optional

from tvuitree.application.connection import connection_options, connect_device
from tvuitree.application.observation import collect_full_json, collect_observation
from tvuitree.domain.observation import error_observation

try:
    from mcp.server.fastmcp import FastMCP
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
