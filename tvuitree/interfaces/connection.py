"""CLI argument parsing and connection diagnostics."""

from __future__ import annotations

import argparse
import sys

from tvuitree.application.connection import ConnectionOptions, connect_device, connection_options
from .terminal import C, c


def add_conn_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--serial", default=None,
                        help="USB 设备序列号（adb devices 中的 serial；默认读取 config.json 的 serial）")
    parser.add_argument("--TV_IP_Address", default=None,
                        help="电视 IP 或主机名（默认读取 config.json 的 TV_IP_Address）")
    parser.add_argument("--port", type=int, default=None,
                        help="adb TCP 端口（默认读取 config.json 的 port）")
    parser.add_argument("--adb", default=None, help="adb 可执行文件路径（默认读取 config.json 的 adb）")
    parser.add_argument("--no-connect", action="store_true", help="不自动执行 adb connect")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    parser.add_argument("-q", "--quiet", action="store_true", help="不打印诊断信息")


def options_from_args(args: argparse.Namespace) -> ConnectionOptions:
    return connection_options(TV_IP_Address=args.TV_IP_Address, port=args.port,
                              adb=args.adb, no_connect=args.no_connect, serial=args.serial)


def connect_for_cli(args: argparse.Namespace):
    try:
        options = options_from_args(args)
    except ValueError as error:
        print(c(str(error), C.RED), file=sys.stderr)
        return None
    device = connect_device(options, quiet=args.quiet)
    if device is None:
        print(c(f"无法连接 {options.target}", C.RED), file=sys.stderr)
        if options.serial is not None:
            print(c("  1) 使用支持调试的 USB 接口和数据线，检查电脑驱动。", C.YEL), file=sys.stderr)
            print(c("  2) 开启电视 USB 调试，并在电视上允许本电脑调试。", C.YEL), file=sys.stderr)
            print(c(f"  3) adb devices 中 {options.target} 的状态必须为 device。", C.YEL), file=sys.stderr)
        else:
            print(c(f"  1) 电视与电脑在同一网段？  ping {options.TV_IP_Address}", C.YEL),
                  file=sys.stderr)
            print(c("  2) 电视已开启 ADB 调试 / 网络调试？", C.YEL), file=sys.stderr)
            print(c(f"  3) 端口对不对？  adb connect {options.target}", C.YEL), file=sys.stderr)
        print(c("  4) adb 路径对不对？  --adb <路径>", C.YEL), file=sys.stderr)
    return device
