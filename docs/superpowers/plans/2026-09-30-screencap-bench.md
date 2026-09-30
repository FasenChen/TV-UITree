# adb 截图耗时压测脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `scripts/bench_screencap.py`，输入设备 IP 和压测次数，对每台设备连续截图，打印每次耗时和汇总统计（min / mean / p50 / p90 / p99 / max），并把同样内容加逐次记录写成一份 txt 报告。

**Architecture:** 脚本复用现有 `Adb`（连接、自动重连）和 `image.capture`（`screencap -p` + PNG 校验），自身不写 `screencap` 命令，保持“截图只在 `infrastructure/image.py` 实现”的规则。纯函数（地址拼接、分位数、汇总、报告格式）与压测循环 `run_bench` 通过注入 `capture` / `clock` / 假设备离线测试。离线测试放进 `tests/selftest_tree.py` 新增的第 10 节，用 `importlib` 按路径加载脚本。txt 报告由纯函数 `format_text_report` 生成，`main` 在所有设备跑完（或中断）后一次写盘。

**Tech Stack:** Python 3.10+ 标准库（`argparse`、`math`、`time`、`datetime`、`dataclasses`、`pathlib`、`importlib.util`）；现有 `tvuitree.infrastructure.adb` / `image`；离线自检 `tests/selftest_tree.py`（普通脚本，不是 pytest）。不新增依赖。

**Spec:** 没有单独的 spec 文件。需求来自 2026-09-30 的对话：“写一个脚本，用于压测 adb 截图获取时间，参数是 devices ip、压测次数”；追加要求“输出一个 txt 的报告”。

## Global Constraints

- 参数：位置参数 `IP`（一个或多个，`ip` 或 `ip:port`），必填 `-n/--count`（正整数）；可选 `--port`（默认 `5555`，1–65535）、`--adb`。
- 计时范围：单次 `image.capture(device)` 调用，即 `adb exec-out screencap -p` 从发起到 PNG 字节全部取回并通过校验。不含连接时间。
- `screencap` 字样只允许出现在 `tvuitree/infrastructure/image.py`（AGENTS.md 规则）；脚本通过 `image.capture` 截图，注释里也不写这个词。
- 退出码：`0` 全部成功；`1` 有截图失败；`2` 用法错误或连接失败；`130` 被 Ctrl+C 中断。多台设备取最大值（中断直接返回 130）。
- 进度与报告写 stdout，连接/参数诊断写 stderr。
- txt 报告：可选 `--report PATH`；不传时写到 `_temp/bench_screencap/bench_screencap_<YYYYmmdd_HHMMSS>.txt`（`_temp/` 已被 .gitignore 忽略），目录不存在时自动创建，UTF-8 编码。
- txt 报告内容：标题、开始时间、设备列表、每台次数；每台设备的汇总（与 stdout 报告相同）加逐次记录；有连接失败时列出“连接失败”一节。
- 只要参数合法就写报告，包括有失败、有设备连不上、Ctrl+C 中断的情况；写完在 stdout 打印“报告已写入 <路径>”。
- 报告写入失败（`OSError`）：stderr 说明原因，退出码至少为 `2`（中断仍返回 `130`），stdout 上已打印的结果不受影响。
- 不把真实设备地址、截图文件、txt 报告写入提交；脚本不落盘 PNG。
- Python 3.10+、四空格缩进、UTF-8、新代码带类型注解，注释风格与仓库一致（中文）。

## Review Focus

- 压测跑一半按 Ctrl+C：期望 stdout 打印已完成部分并标“已中断”，txt 报告照样写出且含“已中断”，不再测后续设备，退出码 130（Task 1、Task 3 测试）。
- IP 写错或设备不在线：期望 stderr 一行“无法连接 <target>”，其余设备照常压测，txt 报告的“连接失败”一节列出它，退出码 2（Task 2、Task 3 测试）。
- 压测中途单次失败（device offline、返回非 PNG）：期望记为失败、打印 `FAIL <原因>`、继续后续轮次，统计只用成功样本，txt 逐次记录里也有这一行，退出码 1（Task 1、Task 2 测试）。
- `--report` 指向不存在的目录或不可写位置：不存在的目录自动创建；真的写不进去时 stderr 报原因、退出码 2，不抛 traceback（Task 3 测试）。
- 全部失败：期望报告写“没有成功的截图，无法统计耗时”，不出现除零异常（Task 1 测试）。

---

## File Structure

- Create: `scripts/bench_screencap.py`：压测脚本。纯函数 + `run_bench` 循环 + `main` 命令行入口，单一职责。
- Modify: `tests/selftest_tree.py`：顶部加 `import importlib.util`；在“收尾”前新增 `t.group("10. 截图耗时压测脚本")`。
- Modify: `README.md`：“其他命令”一节加用法和一段说明（Task 3 再补 txt 报告说明）。

离线测试一律通过 `--report` 或 `report_root` 把报告写到自检临时目录 `TD`，不在仓库 `_temp/` 里留文件。

注意：自检第 7 节只检查 `tvuitree/` 下指定文件里的 `screencap`，不扫描 `scripts/`；但文件名 `bench_screencap.py` 本身不在任何源码文本断言范围内，不冲突。

---

### Task 1: 统计函数与压测循环

**Files:**
- Create: `scripts/bench_screencap.py`
- Modify: `tests/selftest_tree.py`（顶部 import；“收尾”注释 `# ================================================================== 收尾` 之前插入第 10 节）

**Interfaces:**
- Consumes: `tvuitree.infrastructure.image.capture(adb) -> bytes`（内部调用 `adb.exec_out([...], timeout=60)`，返回非 PNG 抛 `ValueError`）；`tvuitree.infrastructure.adb.AdbError`。
- Produces（Task 2 使用）：
  - `DEFAULT_PORT: int = 5555`
  - `BenchResult(target: str, count: int, durations_ms: list[float], sizes: list[int], failures: list[tuple[int, str]], rounds: list[str], interrupted: bool)`；`rounds` 按顺序保存每轮打印的那一行，供 Task 3 写 txt 逐次记录
  - `positive_int(text: str) -> int`（非法抛 `argparse.ArgumentTypeError`）
  - `device_target(address: str, port: int) -> str`（空串抛 `ValueError`）
  - `percentile(sorted_values: list[float], pct: float) -> float`
  - `summarize(durations_ms: list[float]) -> Optional[dict[str, float]]`，键顺序 `min, mean, p50, p90, p99, max`
  - `run_bench(device, count: int, *, capture=image.capture, clock=time.perf_counter, out: Optional[TextIO] = None) -> BenchResult`
  - `format_report(result: BenchResult) -> str`

- [ ] **Step 1: 写失败的测试**

在 `tests/selftest_tree.py` 顶部 import 区（`import contextlib` 之后）加：

```python
import importlib.util
```

在 `# ================================================================== 收尾` 之前插入：

```python
# ================================================================== 10. 截图耗时压测脚本
t.group("10. 截图耗时压测脚本")

_bench_spec = importlib.util.spec_from_file_location(
    "bench_screencap", os.path.join(HERE, "scripts", "bench_screencap.py"))
bench = importlib.util.module_from_spec(_bench_spec)
_bench_spec.loader.exec_module(bench)

_BENCH_PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 8   # 16 字节，能通过 image.capture 的 PNG 头校验


class _BenchDevice:
    """假设备：exec_out 依次吐出预置结果；异常（含 KeyboardInterrupt）就地抛出。"""

    def __init__(self, serial: str, outcomes=(), connected: bool = True) -> None:
        self.serial = serial
        self._outcomes = iter(outcomes)
        self._connected = connected

    def connect(self, quiet: bool = False) -> bool:
        return self._connected

    def exec_out(self, args: list, timeout: float = 60.0) -> bytes:
        item = next(self._outcomes)
        if isinstance(item, BaseException):
            raise item
        return item


def _ticks(*values: float):
    it = iter(values)
    return lambda: next(it)


t.eq(bench.device_target("192.0.2.10", 5555), "192.0.2.10:5555", "只写 IP 时补默认端口")
t.eq(bench.device_target("192.0.2.10:5556", 5555), "192.0.2.10:5556",
     "已带端口的地址原样使用，不重复拼端口")
t.eq(bench.device_target(" 192.0.2.10 ", 5555), "192.0.2.10:5555", "IP 两端空白被去掉")
try:
    bench.device_target("  ", 5555)
    _empty_rejected = False
except ValueError:
    _empty_rejected = True
t.ok(_empty_rejected, "空 IP 报 ValueError")

t.eq(bench.positive_int("3"), 3, "正整数次数原样接受")
for _bad in ("0", "-1", "abc"):
    try:
        bench.positive_int(_bad)
        _rejected = False
    except bench.argparse.ArgumentTypeError:
        _rejected = True
    t.ok(_rejected, f"次数 {_bad!r} 被拒绝")

t.eq(bench.percentile([1.0, 2.0, 3.0, 4.0], 50), 2.0, "p50 取最近秩，不插值")
t.eq(bench.percentile([1.0, 2.0, 3.0, 4.0], 99), 4.0, "p99 落在最大样本")
t.eq(bench.percentile([7.0], 90), 7.0, "单个样本时各分位都是它本身")
t.eq(bench.summarize([]), None, "没有成功样本时不统计，不除零")
t.eq(bench.summarize([30.0, 10.0, 20.0]),
     {"min": 10.0, "mean": 20.0, "p50": 20.0, "p90": 30.0, "p99": 30.0, "max": 30.0},
     "汇总统计不依赖输入顺序")

# 成功 / adb 掉线 / 非 PNG / 成功：失败记下原因并继续，统计只用成功样本。
# clock 只在成功轮次读两次（开始、结束），失败轮次只读开始那一次。
_bench_out = io.StringIO()
_bench_result = bench.run_bench(
    _BenchDevice("192.0.2.10:5555",
                 [_BENCH_PNG, adb.AdbError("device offline"), b"not png", _BENCH_PNG]),
    4, clock=_ticks(0.0, 0.25, 1.0, 2.0, 3.0, 3.5), out=_bench_out)
t.eq(_bench_result.target, "192.0.2.10:5555", "结果记下设备地址")
t.eq(_bench_result.durations_ms, [250.0, 500.0], "只记成功那几次的耗时（毫秒）")
t.eq(_bench_result.sizes, [16, 16], "记下每次 PNG 字节数")
t.eq([index for index, _ in _bench_result.failures], [2, 3], "失败轮次按序记录，不中止压测")
t.eq(_bench_result.failures[0][1], "device offline", "失败原因保留 adb 报错原文")
t.ok(not _bench_result.interrupted, "正常跑完不标中断")
_bench_lines = _bench_out.getvalue().splitlines()
t.eq(_bench_lines[0], "[1/4] 250.0ms 16B", "每轮打印耗时和大小")
t.eq(_bench_lines[1], "[2/4] FAIL device offline", "失败轮次打印 FAIL 和原因")
t.eq(len(_bench_lines), 4, "每轮恰好一行进度")
t.eq(_bench_result.rounds, _bench_lines, "逐次记录与打印的进度行一致，供 txt 报告使用")

_bench_report = bench.format_report(_bench_result)
t.ok("计划 4 次，执行 4 次，成功 2，失败 2" in _bench_report, "报告写明成功与失败次数", _bench_report)
t.ok("min=250.0" in _bench_report and "p50=250.0" in _bench_report
     and "mean=375.0" in _bench_report and "max=500.0" in _bench_report,
     "报告给出分位统计", _bench_report)
t.ok("PNG 平均 16B" in _bench_report, "报告给出平均 PNG 大小", _bench_report)

_all_fail = bench.run_bench(
    _BenchDevice("192.0.2.10:5555", [adb.AdbError("device offline")] * 2),
    2, clock=_ticks(0.0, 1.0), out=io.StringIO())
t.ok("没有成功的截图，无法统计耗时" in bench.format_report(_all_fail),
     "全部失败时报告不统计、不崩溃")

# Ctrl+C：停在当前轮，保留已完成的样本
_interrupted = bench.run_bench(
    _BenchDevice("192.0.2.10:5555", [_BENCH_PNG, KeyboardInterrupt()]),
    5, clock=_ticks(0.0, 0.5, 1.0), out=io.StringIO())
t.ok(_interrupted.interrupted, "Ctrl+C 标记为中断")
t.eq(_interrupted.durations_ms, [500.0], "中断前的样本保留")
_interrupted_report = bench.format_report(_interrupted)
t.ok("执行 1 次" in _interrupted_report and "已中断" in _interrupted_report,
     "中断报告只统计已执行轮次", _interrupted_report)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 10 节加载脚本时报 `FileNotFoundError`（`scripts/bench_screencap.py` 不存在），脚本以非零退出。

- [ ] **Step 3: 写实现**

Create `scripts/bench_screencap.py`：

```python
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tvuitree.infrastructure import image
from tvuitree.infrastructure.adb import AdbError

DEFAULT_PORT = 5555


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
            except (AdbError, ValueError) as error:
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run:
```powershell
.\.venv\Scripts\python.exe -m py_compile scripts/bench_screencap.py
.\.venv\Scripts\python.exe -m pyflakes scripts/bench_screencap.py tests/selftest_tree.py
.\.venv\Scripts\python.exe tests/selftest_tree.py
```
Expected: 无编译 / pyflakes 输出；自检最后一行 `自检通过：N 条断言全部成立`，第 10 节无 FAIL。

- [ ] **Step 5: 提交（仅在用户要求提交时）**

```bash
git add scripts/bench_screencap.py tests/selftest_tree.py
git commit -m "Add screencap latency benchmark core"
```

---

### Task 2: 命令行入口、文档与实机验证

**Files:**
- Modify: `scripts/bench_screencap.py`（import 区补两行；末尾追加 `default_adb`、`parse_args`、`main` 和 `__main__` 入口）
- Modify: `tests/selftest_tree.py`（第 10 节末尾追加 `main` 的测试）
- Modify: `README.md`（“其他命令”一节）

**Interfaces:**
- Consumes: Task 1 的 `DEFAULT_PORT`、`positive_int`、`device_target`、`run_bench`、`format_report`；`Adb(adb_path, serial)`、`Adb.connect(quiet=True) -> bool`、`resolve_adb(explicit) -> str`、`load_device_config() -> dict`（缺失或损坏抛 `ValueError`）。
- Produces: `main(argv: Optional[list[str]] = None, *, make_device: Optional[Callable[[str], object]] = None) -> int`。`make_device(target)` 返回带 `serial`、`connect(quiet=...)`、`exec_out(args, timeout=...)` 的设备对象，测试用它注入假设备。

- [ ] **Step 1: 写失败的测试**

在第 10 节末尾（Task 1 测试之后）追加：

```python
def _bench_main(argv, devices):
    """用假设备跑 main，返回 (退出码, stdout, stderr, 实际创建过的地址)。"""
    created = []

    def _make(target):
        created.append(target)
        return devices[target]

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = bench.main(argv, make_device=_make)
        except SystemExit as exit_:
            code = exit_.code
    return code, out.getvalue(), err.getvalue(), created


_code, _, _, _ = _bench_main(["192.0.2.10", "--count", "0"], {})
t.eq(_code, 2, "次数为 0 是用法错误，退出码 2")
_code, _, _, _ = _bench_main(["192.0.2.10", "-n", "1", "--port", "70000"], {})
t.eq(_code, 2, "端口越界是用法错误，退出码 2")

_code, _out, _, _ = _bench_main(
    ["192.0.2.10", "-n", "2"],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", [_BENCH_PNG, _BENCH_PNG])})
t.eq(_code, 0, "全部截图成功退出码 0")
t.ok("== 192.0.2.10:5555 ==" in _out and "成功 2，失败 0" in _out, "stdout 输出报告", _out)

_code, _, _, _ = _bench_main(
    ["192.0.2.10", "-n", "2"],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555",
                                     [_BENCH_PNG, adb.AdbError("device offline")])})
t.eq(_code, 1, "有截图失败退出码 1")

_code, _out, _err, _created = _bench_main(
    ["192.0.2.99", "192.0.2.10:5556", "-n", "1"],
    {"192.0.2.99:5555": _BenchDevice("192.0.2.99:5555", connected=False),
     "192.0.2.10:5556": _BenchDevice("192.0.2.10:5556", [_BENCH_PNG])})
t.eq(_code, 2, "有设备连不上退出码 2")
t.ok("无法连接 192.0.2.99:5555" in _err, "连不上的设备在 stderr 说明", _err)
t.ok("== 192.0.2.10:5556 ==" in _out, "一台连不上不影响其余设备压测", _out)
t.eq(_created, ["192.0.2.99:5555", "192.0.2.10:5556"], "带端口的地址原样传给设备")

_code, _out, _, _created = _bench_main(
    ["192.0.2.10", "192.0.2.11", "-n", "3"],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", [_BENCH_PNG, KeyboardInterrupt()]),
     "192.0.2.11:5555": _BenchDevice("192.0.2.11:5555", [_BENCH_PNG] * 3)})
t.eq(_code, 130, "Ctrl+C 退出码 130")
t.ok("已中断" in _out, "中断时仍打印已完成部分的报告", _out)
t.eq(_created, ["192.0.2.10:5555"], "中断后不再压测后续设备")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 10 节报 `AttributeError: module 'bench_screencap' has no attribute 'main'`，脚本非零退出。

- [ ] **Step 3: 写实现**

`scripts/bench_screencap.py` 的 import 区改为：

```python
from tvuitree.infrastructure import image
from tvuitree.infrastructure.adb import Adb, AdbError, resolve_adb
from tvuitree.infrastructure.device_config import load_device_config
```

在文件末尾追加：

```python
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


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="压测 adb 截图耗时")
    parser.add_argument("devices", nargs="+", metavar="IP",
                        help="设备 IP，可写 ip 或 ip:port，多台用空格分隔")
    parser.add_argument("-n", "--count", type=positive_int, required=True,
                        help="每台设备的截图次数")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"IP 未带端口时使用的端口，默认 {DEFAULT_PORT}")
    parser.add_argument("--adb", help="adb 路径；默认取 config.json 的 adb")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须是 1 到 65535 的整数")
    return args


def main(argv: Optional[list[str]] = None, *,
         make_device: Optional[Callable[[str], object]] = None) -> int:
    args = parse_args(argv)
    if make_device is None:
        adb_path = default_adb(args.adb)

        def make_device(target: str) -> Adb:
            return Adb(adb_path, target)

    exit_code = 0
    for address in args.devices:
        try:
            target = device_target(address, args.port)
            device = make_device(target)
            connected = device.connect(quiet=True)
        except (ValueError, AdbError) as error:
            print(f"[bench] {address}: {error}", file=sys.stderr)
            exit_code = 2
            continue
        if not connected:
            print(f"[bench] 无法连接 {target}", file=sys.stderr)
            exit_code = 2
            continue
        result = run_bench(device, args.count)
        print(format_report(result))
        if result.interrupted:
            return 130
        if result.failures:
            exit_code = max(exit_code, 1)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
```

`README.md` 的“其他命令”代码块里，在 `python main.py shot ...` 之后加一行：

```powershell
python scripts/bench_screencap.py 192.168.1.148 --count 50
```

并在该代码块后第一段说明之后加一段：

```markdown
`scripts/bench_screencap.py` 压测截图耗时：参数是一个或多个设备 IP（`ip` 或 `ip:port`，未带端口时用 `--port`，默认 `5555`）和 `-n/--count` 次数。每次计时覆盖一次完整截图（发起到 PNG 全部取回并校验），不含连接；逐次打印耗时和 PNG 大小，最后给出 min / mean / p50 / p90 / p99 / max。单次失败会记下原因并继续，Ctrl+C 会打印已完成部分的统计。退出码：`0` 全部成功，`1` 有截图失败，`2` 参数或连接错误，`130` 被中断。
```

- [ ] **Step 4: 运行全部检查**

Run（仓库根目录）：
```powershell
$pythonFiles = @('main.py', 'scripts/bench_screencap.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile $pythonFiles
.\.venv\Scripts\python.exe -m pyflakes $pythonFiles
.\.venv\Scripts\python.exe tests/selftest_tree.py
.\.venv\Scripts\python.exe scripts/bench_screencap.py --help
.\.venv\Scripts\python.exe main.py --help
git diff --check
```
Expected: 编译和 pyflakes 无输出；自检 `自检通过`；`--help` 列出 `IP`、`-n/--count`、`--port`、`--adb`；`git diff --check` 无输出。

- [ ] **Step 5: 实机验证（有可用 TV 时）**

Run（IP 取自 `config.json` 的 `TV_IP_Address`，不要写进提交）：
```powershell
.\.venv\Scripts\python.exe scripts/bench_screencap.py <TV_IP> -n 10
.\.venv\Scripts\python.exe scripts/bench_screencap.py 192.0.2.1 -n 1
```
Expected: 第一条打印 10 行 `[ i/10] xxx.xms NNNNNNB` 和汇总，退出码 0；第二条 stderr 出现“无法连接 192.0.2.1:5555”，退出码 2。没有可用设备时在交付说明里写明跳过。

- [ ] **Step 6: 提交（仅在用户要求提交时）**

```bash
git add scripts/bench_screencap.py tests/selftest_tree.py README.md
git commit -m "Add screencap benchmark command line"
```

---

### Task 3: txt 报告

**Files:**
- Modify: `scripts/bench_screencap.py`（import 区加 `from datetime import datetime`；新增 `REPORT_DIR`、`default_report_path`、`format_text_report`、`write_text_report`；`parse_args` 加 `--report`；整体替换 `main`）
- Modify: `tests/selftest_tree.py`（替换第 10 节的 `_bench_main` 辅助函数；第 10 节末尾追加 txt 报告测试）
- Modify: `README.md`（Task 2 加的那段说明末尾补一句）

**Interfaces:**
- Consumes: Task 1 的 `BenchResult`（含 `rounds`）、`format_report`、`run_bench`、`device_target`；Task 2 的 `parse_args`、`default_adb`、`main` 的退出码规则。
- Produces:
  - `REPORT_DIR: Path`（仓库根下 `_temp/bench_screencap`）
  - `default_report_path(root: Path, started: datetime) -> Path`，文件名 `bench_screencap_<YYYYmmdd_HHMMSS>.txt`
  - `format_text_report(results: list[BenchResult], connect_failures: list[tuple[str, str]], *, count: int, devices: list[str], started: datetime) -> str`
  - `write_text_report(path: Path, text: str) -> None`（自动建目录，UTF-8；失败抛 `OSError`）
  - `main(argv: Optional[list[str]] = None, *, make_device: Optional[Callable[[str], object]] = None, report_root: Optional[Path] = None, now: Callable[[], datetime] = datetime.now) -> int`

- [ ] **Step 1: 写失败的测试**

把第 10 节里 Task 2 写的 `_bench_main` 整个替换成下面的版本。新版把 `report_root` 默认指向自检临时目录 `TD`，Task 2 的调用不用改，也不会往仓库 `_temp/` 写文件：

```python
def _bench_main(argv, devices, **kwargs):
    """用假设备跑 main，返回 (退出码, stdout, stderr, 实际创建过的地址)。"""
    created = []

    def _make(target):
        created.append(target)
        return devices[target]

    kwargs.setdefault("report_root", Path(TD) / "bench_default")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = bench.main(argv, make_device=_make, **kwargs)
        except SystemExit as exit_:
            code = exit_.code
    return code, out.getvalue(), err.getvalue(), created
```

在第 10 节末尾追加：

```python
# txt 报告：默认路径按开始时间命名，目录自动创建
_bench_started = bench.datetime(2026, 9, 30, 8, 1, 2)
t.eq(bench.default_report_path(Path("r"), _bench_started),
     Path("r") / "bench_screencap_20260930_080102.txt", "默认报告文件名带开始时间")

_report_root = Path(TD) / "bench_reports"
_code, _out, _, _ = _bench_main(
    ["192.0.2.99", "192.0.2.10", "-n", "2"],
    {"192.0.2.99:5555": _BenchDevice("192.0.2.99:5555", connected=False),
     "192.0.2.10:5555": _BenchDevice("192.0.2.10:5555",
                                     [_BENCH_PNG, adb.AdbError("device offline")])},
    report_root=_report_root, now=lambda: _bench_started)
_report_file = _report_root / "bench_screencap_20260930_080102.txt"
t.eq(_code, 2, "写报告不改变退出码（有连接失败仍是 2）")
t.ok(_report_file.is_file(), "不传 --report 时写到默认目录，目录自动创建", str(_report_file))
t.ok(f"报告已写入 {_report_file}" in _out, "stdout 告知报告路径", _out)
_report_text = _report_file.read_text(encoding="utf-8") if _report_file.is_file() else ""
t.ok(_report_text.startswith("adb 截图耗时压测报告\n"), "报告有标题", _report_text)
t.ok("开始时间：2026-09-30 08:01:02" in _report_text, "报告写明开始时间", _report_text)
t.ok("设备：192.0.2.99 192.0.2.10" in _report_text and "每台次数：2" in _report_text,
     "报告写明设备和次数", _report_text)
t.ok("== 192.0.2.10:5555 ==" in _report_text and "成功 1，失败 1" in _report_text,
     "报告含每台设备的汇总", _report_text)
t.ok("逐次记录：\n  [1/2] " in _report_text and "  [2/2] FAIL device offline" in _report_text,
     "报告含逐次记录，失败行也在", _report_text)
t.ok("连接失败：\n  192.0.2.99:5555：无法连接" in _report_text, "报告列出连不上的设备", _report_text)

_explicit_report = Path(TD) / "nested" / "dir" / "bench.txt"
_code, _, _, _ = _bench_main(
    ["192.0.2.10", "-n", "1", "--report", str(_explicit_report)],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", [_BENCH_PNG])})
t.eq(_code, 0, "指定 --report 且全部成功，退出码 0")
t.ok(_explicit_report.is_file(), "--report 指定的路径被写入，缺失的上级目录自动创建")

_interrupted_path = Path(TD) / "interrupted.txt"
_code, _, _, _ = _bench_main(
    ["192.0.2.10", "192.0.2.11", "-n", "3", "--report", str(_interrupted_path)],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", [_BENCH_PNG, KeyboardInterrupt()]),
     "192.0.2.11:5555": _BenchDevice("192.0.2.11:5555", [_BENCH_PNG] * 3)})
_interrupted_text = (_interrupted_path.read_text(encoding="utf-8")
                     if _interrupted_path.is_file() else "")
t.eq(_code, 130, "中断时写完报告仍返回 130")
t.ok("已中断" in _interrupted_text, "中断时 txt 报告照样写出并标明中断", _interrupted_text)
t.ok("== 192.0.2.11:5555 ==" not in _interrupted_text, "中断后未测的设备不出现在报告汇总里",
     _interrupted_text)

# 报告写不进去：上级路径是个普通文件
_blocker = Path(TD) / "blocker.txt"
_blocker.write_text("x", encoding="utf-8")
_code, _out, _err, _ = _bench_main(
    ["192.0.2.10", "-n", "1", "--report", str(_blocker / "bench.txt")],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", [_BENCH_PNG])})
t.eq(_code, 2, "报告写入失败退出码 2")
t.ok("报告写入失败" in _err, "报告写入失败在 stderr 说明", _err)
t.ok("== 192.0.2.10:5555 ==" in _out, "报告写入失败不影响 stdout 上的结果", _out)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 10 节报 `TypeError: main() got an unexpected keyword argument 'report_root'`，脚本非零退出。

- [ ] **Step 3: 写实现**

`scripts/bench_screencap.py` 的 import 区，在 `from dataclasses import dataclass, field` 之前加：

```python
from datetime import datetime
```

在 `DEFAULT_PORT = 5555` 之后加：

```python
REPORT_DIR = Path(__file__).resolve().parents[1] / "_temp" / "bench_screencap"
```

在 `format_report` 之后加：

```python
def default_report_path(root: Path, started: datetime) -> Path:
    return root / f"bench_screencap_{started:%Y%m%d_%H%M%S}.txt"


def format_text_report(results: list[BenchResult], connect_failures: list[tuple[str, str]], *,
                       count: int, devices: list[str], started: datetime) -> str:
    """txt 报告：与 stdout 汇总同一套数字，外加逐次记录和连接失败。"""
    lines = [
        "adb 截图耗时压测报告",
        f"开始时间：{started:%Y-%m-%d %H:%M:%S}",
        f"设备：{' '.join(devices)}",
        f"每台次数：{count}",
    ]
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
```

`parse_args` 里，在 `parser.add_argument("--adb", ...)` 之后加：

```python
    parser.add_argument("--report", help="txt 报告路径；默认写到 _temp/bench_screencap/ 下按时间命名")
```

把 `main` 整个替换为：

```python
def main(argv: Optional[list[str]] = None, *,
         make_device: Optional[Callable[[str], object]] = None,
         report_root: Optional[Path] = None,
         now: Callable[[], datetime] = datetime.now) -> int:
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
    for address in args.devices:
        try:
            target = device_target(address, args.port)
            device = make_device(target)
            connected = device.connect(quiet=True)
        except (ValueError, AdbError) as error:
            print(f"[bench] {address}: {error}", file=sys.stderr)
            connect_failures.append((address, str(error)))
            exit_code = 2
            continue
        if not connected:
            print(f"[bench] 无法连接 {target}", file=sys.stderr)
            connect_failures.append((target, "无法连接"))
            exit_code = 2
            continue
        result = run_bench(device, args.count)
        results.append(result)
        print(format_report(result))
        if result.interrupted:
            interrupted = True
            break
        if result.failures:
            exit_code = max(exit_code, 1)

    # 报告在所有设备跑完（或中断）后一次写出，写不进去也不影响已打印的结果
    text = format_text_report(results, connect_failures, count=args.count,
                              devices=args.devices, started=started)
    try:
        write_text_report(report_path, text)
        print(f"报告已写入 {report_path}")
    except OSError as error:
        print(f"[bench] 报告写入失败 {report_path}：{error}", file=sys.stderr)
        exit_code = 2
    return 130 if interrupted else exit_code
```

`README.md` 里 Task 2 加的那段说明末尾追加：

```markdown
每次运行都会写一份 UTF-8 txt 报告（汇总、逐次记录、连接失败），默认在 `_temp/bench_screencap/bench_screencap_<时间>.txt`，可用 `--report <路径>` 指定；中断时也会写出已完成部分。报告写入失败时退出码为 `2`。
```

- [ ] **Step 4: 运行全部检查**

Run（仓库根目录）：
```powershell
$pythonFiles = @('main.py', 'scripts/bench_screencap.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile $pythonFiles
.\.venv\Scripts\python.exe -m pyflakes $pythonFiles
.\.venv\Scripts\python.exe tests/selftest_tree.py
.\.venv\Scripts\python.exe scripts/bench_screencap.py --help
git status --short
git diff --check
```
Expected: 编译和 pyflakes 无输出；自检 `自检通过`；`--help` 多出 `--report`；`git status` 里没有 `_temp/` 下的新文件（离线测试只写 `TD`）；`git diff --check` 无输出。

- [ ] **Step 5: 实机验证（有可用 TV 时）**

Run：
```powershell
.\.venv\Scripts\python.exe scripts/bench_screencap.py <TV_IP> -n 10
```
Expected: stdout 末行 `报告已写入 ...\_temp\bench_screencap\bench_screencap_<时间>.txt`；打开该文件能看到标题、开始时间、汇总和 10 行逐次记录。没有可用设备时在交付说明里写明跳过。

- [ ] **Step 6: 提交（仅在用户要求提交时）**

```bash
git add scripts/bench_screencap.py tests/selftest_tree.py README.md
git commit -m "Write screencap benchmark txt report"
```
