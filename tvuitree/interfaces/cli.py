"""Single command line interface for TV observation and diagnostics."""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from tvuitree.domain.observation import DEFAULT_MAX_NODES

from .connection import add_conn_args
from .terminal import setup_console
from .tree import run_tree
from .observe import run_observe
from .visible import run_visible
from .input import run_input
from .shot import run_shot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Android TV UI 观察工具")
    commands = parser.add_subparsers(dest="command")

    observe = commands.add_parser("observe", help="焦点、页面摘要和匹配证据")
    add_conn_args(observe)
    observe.add_argument("--from-json", metavar="FILE", help="从已有 full JSON 离线观察")
    observe.add_argument("--out", metavar="FILE", help="将观察 JSON 写入文件")
    observe.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES, metavar="N",
                         help=f"页面摘要节点上限（默认 {DEFAULT_MAX_NODES}）")
    observe.add_argument("--no-dumpsys", action="store_true", help="只采集 a11y 树")
    observe.add_argument("--save-raw", metavar="DIR", help="保存采集原文")

    tree = commands.add_parser("tree", help="完整或裁剪后的控件树")
    add_conn_args(tree)
    tree.add_argument("--mode", choices=["full", "slim"], default="full")
    tree.add_argument("--from-json", metavar="FILE", help="从已有 full JSON 离线裁剪，仅 slim")
    tree.add_argument("--keep", metavar="LIST", help="slim 模式下保留指定剪枝类型")
    tree.add_argument("--prune-list", action="store_true", help="列出剪枝开关")
    tree.add_argument("--out", metavar="FILE", help="将 JSON 写入文件")
    tree.add_argument("--no-dumpsys", action="store_true", help="只采集 a11y 树")
    tree.add_argument("--save-raw", metavar="DIR", help="保存采集原文")

    visible = commands.add_parser("visible", help="当前屏幕的可见控件摘要和焦点")
    add_conn_args(visible)
    visible.add_argument("--from-json", metavar="FILE", help="从已有 full JSON 离线筛选")
    visible.add_argument("--out", metavar="FILE", help="将可见摘要 JSON 写入文件")
    visible.add_argument("--save-raw", metavar="DIR", help="保存采集原文")

    remote = commands.add_parser("input", help="发送遥控器按键")
    add_conn_args(remote)
    remote.add_argument("keys", nargs="?", metavar="KEYS", help="例如 DOWN,RIGHT,OK")
    remote.add_argument("--delay", type=float, default=0.5, help="按键间隔秒数")
    remote.add_argument("--repeat", type=int, default=1, help="重复整个序列的次数")
    remote.add_argument("--list", action="store_true", help="列出可用按键短名")

    shot = commands.add_parser("shot", help="截图并按树 JSON 画框")
    add_conn_args(shot)
    shot.add_argument("--json", dest="json_path", required=True, metavar="FILE")
    shot.add_argument("--out", default="shot.png", metavar="FILE")
    shot.add_argument("--image", metavar="FILE", help="使用已有 PNG 离线画框")
    shot.add_argument("--source", choices=["a11y", "dumpsys", "both"], default="a11y")
    shot.add_argument("--draw", choices=["focus", "actionable", "all"], default="focus")
    shot.add_argument("--width", type=int, default=1, metavar="N")

    commands.add_parser("mcp", help="启动 stdio MCP 服务（界面读取与默认设备配置）")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "mcp":
        from .mcp import mcp
        mcp.run(transport="stdio")
        return 0
    setup_console(args.no_color)
    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    return {
        "observe": run_observe,
        "tree": run_tree,
        "visible": run_visible,
        "input": run_input,
        "shot": run_shot,
    }[args.command](args)
