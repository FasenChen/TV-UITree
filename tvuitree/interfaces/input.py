"""Remote-control command presentation."""

from __future__ import annotations

import argparse
import sys

from tvuitree.infrastructure.adb import AdbError

from .connection import connect_for_cli
from .terminal import C, c


def run_input(args: argparse.Namespace) -> int:
    from tvuitree.application.input import KEY_ALIASES, normalize_keycode, send_sequence
    if args.list or not args.keys:
        print("可用短名（等价于同名 KEYCODE_* 键）：")
        groups = {}
        for short, full in KEY_ALIASES.items():
            groups.setdefault(full, []).append(short)
        for full in sorted(groups):
            print(f"  {full:<20} {', '.join(sorted(groups[full]))}")
        print("\n也可以直接写 KEYCODE_* 全名，或直接写数字键码。")
        return 0 if args.list else 2
    keys = [item.strip() for item in args.keys.split(",") if item.strip()]
    if not keys:
        print(c("没有可发送的按键。", C.RED), file=sys.stderr)
        return 2
    try:
        keys = [normalize_keycode(key) for key in keys]
    except ValueError as error:
        print(c(str(error), C.RED), file=sys.stderr)
        return 2
    device = connect_for_cli(args)
    if device is None:
        return 2
    if not args.quiet:
        print(c(f"[dev] {device.serial}", C.GRY), file=sys.stderr)
    failures = 0
    try:
        for keycode, error in send_sequence(device, keys, delay=args.delay, repeat=args.repeat):
            if error:
                failures += 1
                print(c(f"  {keycode:<20} 发送失败：{error}", C.RED), file=sys.stderr)
            elif not args.quiet:
                print(f"  {keycode}")
    except (AdbError, OSError) as error:
        print(c(f"发送失败：{type(error).__name__}: {error}", C.RED), file=sys.stderr)
        return 1
    return 1 if failures else 0
