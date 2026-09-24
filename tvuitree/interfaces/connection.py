"""CLI argument parsing and connection diagnostics."""

from __future__ import annotations

import argparse
import sys

from tvuitree.application.connection import ConnectionOptions, connect_device
from tvuitree.infrastructure.adb import DEFAULT_HOST, DEFAULT_PORT
from .terminal import C, c


def add_conn_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"电视 IP（默认 {DEFAULT_HOST}）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"adb TCP 端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--serial", default=None, help="直接指定 adb serial")
    parser.add_argument("--address", default=None, help="直接指定 host:port")
    parser.add_argument("--adb", default=None, help="adb 可执行文件路径")
    parser.add_argument("--no-connect", action="store_true", help="不自动执行 adb connect")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    parser.add_argument("-q", "--quiet", action="store_true", help="不打印诊断信息")


def options_from_args(args: argparse.Namespace) -> ConnectionOptions:
    return ConnectionOptions(host=args.host, port=args.port, serial=args.serial,
                             address=args.address, adb=args.adb,
                             no_connect=args.no_connect)


def connect_for_cli(args: argparse.Namespace):
    options = options_from_args(args)
    device = connect_device(options, quiet=args.quiet)
    if device is None:
        print(c(f"无法连接 {options.target}", C.RED), file=sys.stderr)
        print(c(f"  1) 电视与电脑在同一网段？  ping {options.host}", C.YEL), file=sys.stderr)
        print(c("  2) 电视已开启 ADB 调试 / 网络调试？", C.YEL), file=sys.stderr)
        print(c(f"  3) 端口对不对？  adb connect {options.host}:{options.port}", C.YEL), file=sys.stderr)
        print(c("  4) adb 路径对不对？  --adb <路径>", C.YEL), file=sys.stderr)
    return device
