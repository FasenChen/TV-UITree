#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压测 adb 截图耗时：对一台或多台 TV 连续截图，统计每次取回 PNG 的时间。

计时范围是单次 image.capture：从发起 exec-out 截图到 PNG 字节全部取回并通过校验，
不含连接时间。截图命令本身只在 infrastructure/image.py 里实现，这里只调用它。

用法：
  python scripts/bench_screencap.py 192.168.1.148 --count 50
  python scripts/bench_screencap.py 192.168.1.148 192.168.1.149:5556 -n 20
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvuitree.infrastructure import image
from tvuitree.infrastructure.adb import Adb, AdbError, resolve_adb
from tvuitree.infrastructure.device_config import load_device_config
from tvuitree.interfaces.terminal import setup_console

DEFAULT_PORT = 5555
REPORT_DIR = Path(__file__).resolve().parents[1] / "_temp" / "bench_screencap"


@dataclass
class BenchResult:
    target: str
    count: int
    durations_ms: list[float] = field(default_factory=list)
    sizes: list[int] = field(default_factory=list)
    failures: list[tuple[int, str]] = field(default_factory=list)
    rounds: list[str] = field(default_factory=list)
    interrupted: bool = False


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是正整数：{text!r}")
    if value < 1:
        raise argparse.ArgumentTypeError(f"必须是正整数：{text!r}")
    return value


def device_target(address: str, port: int) -> str:
    """只写 IP 时补端口；已带端口的 ip:port 原样使用。"""
    address = address.strip()
    if not address:
        raise ValueError("设备 IP 不能为空")
    return address if ":" in address else f"{address}:{port}"


def percentile(sorted_values: list[float], pct: float) -> float:
    """最近秩法：不插值，结果一定是某次实测值。"""
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def summarize(durations_ms: list[float]) -> Optional[dict[str, float]]:
    if not durations_ms:
        return None
    values = sorted(durations_ms)
    return {
        "min": values[0],
        "mean": sum(values) / len(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p99": percentile(values, 99),
        "max": values[-1],
    }


def run_bench(device, count: int, *, capture: Callable = image.capture,
              clock: Callable[[], float] = time.perf_counter,
              out: Optional[TextIO] = None) -> BenchResult:
    """连续截图 count 次；单次失败记下原因继续，Ctrl+C 停下并保留已完成的样本。"""
    out = out or sys.stdout
    result = BenchResult(target=device.serial, count=count)
    width = len(str(count))
    try:
        for index in range(1, count + 1):
            start = clock()
            try:
                png = capture(device)
            except (AdbError, ValueError, OSError) as error:
                result.failures.append((index, str(error)))
                line = f"[{index:>{width}}/{count}] FAIL {error}"
            else:
                elapsed = (clock() - start) * 1000
                result.durations_ms.append(elapsed)
                result.sizes.append(len(png))
                line = f"[{index:>{width}}/{count}] {elapsed:.1f}ms {len(png)}B"
            result.rounds.append(line)
            print(line, file=out, flush=True)
    except KeyboardInterrupt:
        result.interrupted = True
    return result


def format_report(result: BenchResult) -> str:
    done = len(result.durations_ms) + len(result.failures)
    head = (f"计划 {result.count} 次，执行 {done} 次，"
            f"成功 {len(result.durations_ms)}，失败 {len(result.failures)}")
    if result.interrupted:
        head += "（已中断）"
    lines = [f"== {result.target} ==", head]
    stats = summarize(result.durations_ms)
    if stats is None:
        lines.append("没有成功的截图，无法统计耗时")
    else:
        lines.append("耗时(ms) " + " ".join(f"{key}={value:.1f}" for key, value in stats.items()))
        lines.append(f"PNG 平均 {sum(result.sizes) // len(result.sizes)}B")
    return "\n".join(lines)


def default_report_path(root: Path, started: datetime) -> Path:
    return root / f"bench_screencap_{started:%Y%m%d_%H%M%S}.txt"


def format_text_report(results: list[BenchResult], connect_failures: list[tuple[str, str]], *,
                       count: int, devices: list[str], started: datetime,
                       interrupted: bool = False) -> str:
    """txt 报告：与 stdout 汇总同一套数字，外加逐次记录和连接失败。"""
    lines = [
        "adb 截图耗时压测报告",
        f"开始时间：{started:%Y-%m-%d %H:%M:%S}",
        f"设备：{' '.join(devices)}",
        f"每台次数：{count}",
    ]
    if interrupted:
        lines.append("状态：已中断，之后的设备未压测")
    for result in results:
        lines += ["", format_report(result), "逐次记录："]
        lines += [f"  {line}" for line in result.rounds]
    if connect_failures:
        lines += ["", "连接失败："]
        lines += [f"  {target}：{reason}" for target, reason in connect_failures]
    return "\n".join(lines) + "\n"


def write_text_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def default_adb(explicit: Optional[str]) -> str:
    """--adb 优先；否则取 config.json 的 adb；都没有再按 PATH 与常见位置查找。"""
    if explicit:
        return resolve_adb(explicit)
    try:
        configured = load_device_config().get("adb")
    except ValueError:
        configured = None
    if not isinstance(configured, str) or not configured.strip():
        configured = None
    return resolve_adb(configured)


def device_state(device) -> str:
    """adb devices 里列出的也可能是 unauthorized / offline，只有 device 状态能截图。"""
    rc, out, err = device.shell_raw("echo ok", timeout=15)
    if rc == 0 and out.strip() == "ok":
        return "device"
    return (err or out).strip() or f"shell 返回 {rc}"


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="压测 adb 截图耗时")
    parser.add_argument("devices", nargs="+", metavar="IP",
                        help="设备 IP，可写 ip 或 ip:port，多台用空格分隔")
    parser.add_argument("-n", "--count", type=positive_int, required=True,
                        help="每台设备的截图次数")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"IP 未带端口时使用的端口，默认 {DEFAULT_PORT}")
    parser.add_argument("--adb", help="adb 路径；默认取 config.json 的 adb")
    parser.add_argument("--report", help="txt 报告路径；默认写到 _temp/bench_screencap/ 下按时间命名")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须是 1 到 65535 的整数")
    return args


def main(argv: Optional[list[str]] = None, *,
         make_device: Optional[Callable[[str], object]] = None,
         report_root: Optional[Path] = None,
         now: Callable[[], datetime] = datetime.now) -> int:
    setup_console()
    args = parse_args(argv)
    started = now()
    report_path = (Path(args.report) if args.report
                   else default_report_path(report_root or REPORT_DIR, started))
    if make_device is None:
        adb_path = default_adb(args.adb)

        def make_device(target: str) -> Adb:
            return Adb(adb_path, target)

    results: list[BenchResult] = []
    connect_failures: list[tuple[str, str]] = []
    exit_code = 0
    interrupted = False
    try:
        for address in args.devices:
            target = address
            try:
                target = device_target(address, args.port)
                device = make_device(target)
                state = device_state(device) if device.connect(quiet=True) else "未在 adb devices 中"
            except (ValueError, AdbError, OSError) as error:
                state = str(error)
            if state != "device":
                print(f"[bench] 无法连接 {target}：{state}", file=sys.stderr)
                connect_failures.append((target, f"无法连接：{state}"))
                exit_code = 2
                continue
            # 压测期间不自动重连：掉线要记成一次失败，而不是把重连时间算进一次成功
            device.auto_connect = False
            result = run_bench(device, args.count)
            results.append(result)
            print(format_report(result))
            if result.interrupted:
                interrupted = True
                break
            if result.failures:
                exit_code = max(exit_code, 1)
    except KeyboardInterrupt:
        # 连接阶段的 Ctrl+C（adb connect 可能卡十几秒）也要保住已完成设备的报告
        interrupted = True

    # 报告在所有设备跑完（或中断）后一次写出，写不进去也不影响已打印的结果
    text = format_text_report(results, connect_failures, count=args.count,
                              devices=args.devices, started=started,
                              interrupted=interrupted)
    try:
        write_text_report(report_path, text)
        print(f"报告已写入 {report_path}")
    except OSError as error:
        print(f"[bench] 报告写入失败 {report_path}：{error}", file=sys.stderr)
        exit_code = 2
    return 130 if interrupted else exit_code


if __name__ == "__main__":
    sys.exit(main())
