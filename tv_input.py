#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tv_input.py — 遥控器按键发送（测试辅助脚本，**不属于本项目的核心功能**）

它只干一件事：往设备发按键。
主脚本 tv_tree.py 与按键完全无关 —— 取树不需要按任何键，本脚本的存在只是为了
手工测试时能「按一下 → 再取一次树」地对照。

实测踩过的坑（所以这个脚本不能更简）
------------------------------------
`input keyevent DOWN` 是**非法**的：必须带 `KEYCODE_` 前缀或直接给数字，
否则 input 命令会以 "Unknown key code" 静默失败 —— 焦点不动，但命令返回成功，
排查起来非常费劲。本脚本统一归一化成 `KEYCODE_xxx`，并显式检查返回码与报错文本。

用法
----
  python tv_input.py DOWN
  python tv_input.py DOWN,DOWN,RIGHT,OK --delay 0.6
  python tv_input.py --list                # 看可用短名
  python tv_input.py BACK --repeat 3
"""

from __future__ import annotations

import argparse
import sys
import time

from tv_adb import C, add_conn_args, c, connect_device, setup_console

# 遥控器按键别名（短名 → KEYCODE）
KEY_ALIASES = {
    "UP": "DPAD_UP", "DOWN": "DPAD_DOWN", "LEFT": "DPAD_LEFT", "RIGHT": "DPAD_RIGHT",
    "OK": "DPAD_CENTER", "ENTER": "ENTER", "CENTER": "DPAD_CENTER", "SELECT": "DPAD_CENTER",
    "BACK": "BACK", "HOME": "HOME", "MENU": "MENU", "SETTINGS": "SETTINGS",
    "PLAY": "MEDIA_PLAY_PAUSE", "PLAYPAUSE": "MEDIA_PLAY_PAUSE",
    "NEXT": "MEDIA_NEXT", "PREV": "MEDIA_PREVIOUS",
    "VOLUP": "VOLUME_UP", "VOLDOWN": "VOLUME_DOWN", "MUTE": "VOLUME_MUTE",
    "POWER": "POWER", "TAB": "TAB", "DEL": "DEL",
}


def normalize_keycode(name: str) -> str:
    """'DOWN' / 'dpad_down' / '20' → 'KEYCODE_DPAD_DOWN' / '20'"""
    k = name.strip()
    if k.isdigit():
        return k
    k = k.upper()
    k = KEY_ALIASES.get(k, k)
    if k.startswith("KEYCODE_"):
        return k
    return "KEYCODE_" + k


def send_key(adb, name: str) -> str | None:
    """发送按键。成功返回 None，失败返回错误说明。"""
    kc = normalize_keycode(name)
    rc, out, err = adb.shell_raw(f"input keyevent {kc}", timeout=20)
    blob = (out + err).strip()
    if rc != 0 or "Error" in blob or "Exception" in blob or "Unknown" in blob:
        return blob or f"exit={rc}"
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tv_input.py",
        description="遥控器按键发送（测试辅助）。取控件树请用 tv_tree.py。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  python tv_input.py DOWN
  python tv_input.py DOWN,DOWN,RIGHT,OK --delay 0.6
  python tv_input.py BACK --repeat 3
  python tv_input.py --list
""")
    add_conn_args(p)
    p.add_argument("keys", nargs="?", default=None, metavar="KEYS",
                   help="逗号分隔的按键序列，如 DOWN,DOWN,RIGHT,OK；短名见 --list")
    p.add_argument("--delay", type=float, default=0.5,
                   help="每个按键之间的间隔秒数（默认 0.5）")
    p.add_argument("--repeat", type=int, default=1,
                   help="整个序列重复几遍（默认 1）")
    p.add_argument("--list", action="store_true", help="列出可用短名后退出")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    setup_console(args.no_color)

    if args.list or not args.keys:
        print("可用短名（等价于同名 KEYCODE_* 键）：")
        groups = {}
        for short, full in KEY_ALIASES.items():
            groups.setdefault(full, []).append(short)
        for full in sorted(groups):
            print(f"  {full:<20} {', '.join(sorted(groups[full]))}")
        print("\n也可以直接写 KEYCODE_* 全名，或直接写数字键码。")
        return 0 if args.list else 2

    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    if not keys:
        print(c("没有可发送的按键。", C.RED), file=sys.stderr)
        return 2

    adb = connect_device(args)
    if adb is None:
        return 2

    if not args.quiet:
        print(c(f"[dev] {adb.serial}", C.GRY), file=sys.stderr)

    failed = 0
    for rep in range(max(1, args.repeat)):
        for i, k in enumerate(keys):
            err = send_key(adb, k)
            kc = normalize_keycode(k)
            if err:
                failed += 1
                print(c(f"  {kc:<20} 发送失败：{err}", C.RED), file=sys.stderr)
            elif not args.quiet:
                print(f"  {kc}")
            # 最后一个键之后不用等
            if args.delay > 0 and not (rep == args.repeat - 1 and i == len(keys) - 1):
                time.sleep(args.delay)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
