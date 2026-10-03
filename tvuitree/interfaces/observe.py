"""Model observation command presentation."""

from __future__ import annotations

import argparse
import sys

from tvuitree.application.observation import collect_observation
from tvuitree.infrastructure.adb import AdbError
from .connection import connect_for_cli
from .json_io import emit_json_checked, load_full_json
from .terminal import C, c


def run_observe(args: argparse.Namespace) -> int:
    if args.from_json:
        try:
            result = collect_observation(full_json=load_full_json(args.from_json),
                                         max_nodes=args.max_nodes)
        except (OSError, ValueError, TypeError) as error:
            print(c(f"读不了 {args.from_json}：{type(error).__name__}: {error}", C.RED),
                  file=sys.stderr)
            return 2
    else:
        device = connect_for_cli(args)
        if device is None:
            return 2
        try:
            result = collect_observation(
                adb=device, serial=device.serial, save_raw=args.save_raw,
                quiet=args.quiet, use_dumpsys=not args.no_dumpsys,
                max_nodes=args.max_nodes,
            )
        except AdbError as error:
            print(c(str(error), C.RED), file=sys.stderr)
            return 3
        except Exception as error:
            print(c(f"采集失败：{type(error).__name__}: {error}", C.RED), file=sys.stderr)
            return 3
    failed = emit_json_checked(result, args.out)
    if failed is not None:
        return failed
    print(c("[observe] 已生成模型观察 JSON", C.GRY), file=sys.stderr)
    return 0
