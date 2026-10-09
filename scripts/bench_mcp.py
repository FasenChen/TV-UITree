#!/usr/bin/env python3
"""Benchmark MCP reads against direct PNG capture."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from scripts.bench_screencap import positive_int, summarize
from tvuitree.application.connection import connection_options, connect_device
from tvuitree.application.observation import collect_observation
from tvuitree.infrastructure.image import capture
from tvuitree.interfaces.timing import tool_timing

CASES = (
    ("get_full_tree", "get_full_tree", {}),
    ("get_full_tree_a11y", "get_full_tree", {"no_dumpsys": True}),
    ("get_screen_summary", "get_screen_summary", {}),
    ("get_screen_summary_a11y", "get_screen_summary", {"no_dumpsys": True}),
    ("get_visible_controls", "get_visible_controls", {}),
    ("get_current_focus", "get_current_focus", {}),
    ("get_focus_screenshot", "get_focus_screenshot", {}),
    ("direct_screenshot", "direct_screenshot", {}),
)


def parse_timing(text: str, tool: str) -> dict:
    """解析本次调用唯一的计时块。"""
    text = "\n".join(text.splitlines())
    headers = list(re.finditer(
        r"^\[tv-uitree\] \d{2}:\d{2}:\d{2}\.\d{3} (\w+)  total (\d+(?:\.\d+)?) ms(?:  failed at (\w+))?$",
        text, re.M))
    if len(headers) != 1 or headers[0][1] != tool:
        raise ValueError(f"{tool} 的计时块缺失、重复或工具名错配")
    header = headers[0]
    stages = {}
    for line in text[header.end():].splitlines():
        if not line.strip():
            continue
        if not line.startswith("  "):
            break
        stage = re.fullmatch(r"  (\w+)\s+(\d+(?:\.\d+)?) ms\s+\d+(?:\.\d+)?%", line)
        if stage is None or stage[1] in stages:
            raise ValueError(f"{tool} 的阶段行损坏或重复")
        stages[stage[1]] = float(stage[2])
    if not stages:
        raise ValueError(f"{tool} 没有阶段计时")
    return {"server_ms": float(header[2]), "stages_ms": stages, "failed_stage": header[3]}


def summarize_samples(samples: list[dict], cases: list[str]) -> dict:
    """排除预热和失败，按成功的同轮截图比较。"""
    measured = [s for s in samples if not s["warmup"]]
    direct = {s["round"]: s for s in measured if s["case"] == "direct_screenshot" and s["ok"]}
    result = {}
    for case in cases:
        selected = [s for s in measured if s["case"] == case]
        good = [s for s in selected if s["ok"]]
        pairs = [(s["client_ms"], direct[s["round"]]["client_ms"]) for s in good if s["round"] in direct]
        names = sorted({name for s in good for name in s["stages_ms"]})
        result[case] = {
            "success": len(good), "failed": len(selected) - len(good),
            "success_rate": len(good) / len(selected) if selected else None,
            "client_ms": summarize([s["client_ms"] for s in good]),
            "server_ms": summarize([s["server_ms"] for s in good]),
            "extra_ms": summarize([s["client_ms"] - s["server_ms"] for s in good]),
            "stages_ms": {name: summarize([s["stages_ms"][name] for s in good if name in s["stages_ms"]]) for name in names},
            "comparison": {"pairs": len(pairs),
                           "mean_delta_ms": sum(a - b for a, b in pairs) / len(pairs),
                           "ratio_of_means": sum(a for a, _ in pairs) / sum(b for _, b in pairs)} if pairs and sum(b for _, b in pairs) > 0 else None,
        }
    return result


def scene_fingerprint(arguments: dict) -> dict:
    """在计时外记录画面像素与焦点，不保存树和图片内容。"""
    device = connect_device(connection_options(**arguments), quiet=True)
    if device is None:
        raise RuntimeError("无法连接 TV")
    observation = collect_observation(adb=device, serial=device.serial, quiet=True, use_dumpsys=False)
    png = capture(device)
    with Image.open(io.BytesIO(png)) as image:
        pixels = image.convert("RGB")
        return {"window": observation["window"], "focus": observation["focus"],
                "png_size": list(pixels.size), "pixels_sha256": hashlib.sha256(pixels.tobytes()).hexdigest()}


def check_result(result, tool: str) -> None:
    """协议成功也可能包含业务错误，错误返回不算成功样本。"""
    if result.isError:
        raise ValueError("MCP 返回协议错误，详见 stderr 日志")
    data = result.structuredContent
    if data is None:
        data = json.loads(next(c.text for c in result.content if c.type == "text"))
    if isinstance(data, list):
        data = data[0]
    if not isinstance(data, dict) or data.get("error") or data.get("status") == "error":
        raise ValueError("工具返回业务错误")
    if isinstance(data.get("focus"), dict) and data["focus"].get("status") == "error":
        raise ValueError("观察返回采集错误")
    if tool == "get_focus_screenshot" and not all(data.get(k) for k in ("focus_found", "screenshot_captured", "focus_marked")):
        raise ValueError("焦点截图未完整成功")


async def measure(session: ClientSession, case: tuple, arguments: dict,
                  log: TextIO, log_path: Path, round_number: int, warmup: bool) -> dict:
    """每次响应结束后按日志字节偏移关联唯一计时块。"""
    label, tool, overrides = case
    log.flush()
    offset = log_path.stat().st_size
    sample = {"case": label, "tool": tool, "round": round_number, "warmup": warmup,
              "ok": False, "transport_error": False, "error": None}
    started = time.perf_counter()
    result = None
    try:
        if tool == "direct_screenshot":
            with contextlib.redirect_stderr(log), tool_timing(tool) as timer:
                with timer.stage("connect"):
                    device = connect_device(connection_options(**arguments), quiet=True)
                    if device is None:
                        raise RuntimeError("无法连接 TV")
                with timer.stage("screenshot"):
                    png = capture(device)
            sample["png_bytes"] = len(png)
        else:
            result = await session.call_tool(tool, {**arguments, **overrides})
    except Exception as error:
        sample["error"] = f"{type(error).__name__}: {error}"
        sample["transport_error"] = tool != "direct_screenshot"
    finally:
        sample["client_ms"] = (time.perf_counter() - started) * 1000
    log.flush()
    sample["log_start_byte"] = offset
    sample["log_end_byte"] = log_path.stat().st_size
    try:
        sample.update(parse_timing(log_path.read_bytes()[offset:sample["log_end_byte"]].decode("utf-8", errors="replace"), tool))
        if sample["failed_stage"]:
            raise ValueError(f"阶段 {sample['failed_stage']} 失败")
        if result is not None:
            check_result(result, tool)
        sample["ok"] = sample["error"] is None
    except Exception as error:
        sample["error"] = sample["error"] or f"{type(error).__name__}: {error}"
    return sample


async def run(args: argparse.Namespace, arguments: dict, output: Path, report: dict) -> None:
    """只启动一个服务，预热后轮换顺序串行测试。"""
    report["scene_before"] = scene_fingerprint(arguments)
    server = StdioServerParameters(command=sys.executable, args=[str(ROOT / "main.py"), "mcp"],
                                   cwd=str(ROOT), env={**os.environ, "PYTHONUTF8": "1"})
    started = time.perf_counter()
    with (output / "stderr.log").open("w", encoding="utf-8") as log:
        async with stdio_client(server, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=args.timeout)) as session:
                await session.initialize()
                report["startup_ms"] = (time.perf_counter() - started) * 1000
                available = {tool.name for tool in (await session.list_tools()).tools}
                if not {tool for _, tool, _ in CASES if tool != "direct_screenshot"} <= available:
                    raise RuntimeError("MCP 缺少待测工具")
                with (output / "samples.jsonl").open("w", encoding="utf-8") as records:
                    for index in range(args.warmup + args.count):
                        warmup = index < args.warmup
                        round_number = index + 1 if warmup else index - args.warmup + 1
                        shift = index % len(CASES)
                        for case in CASES[shift:] + CASES[:shift]:
                            sample = await measure(session, case, arguments, log, output / "stderr.log", round_number, warmup)
                            report["samples"].append(sample)
                            records.write(json.dumps(sample, ensure_ascii=False) + "\n")
                            records.flush()
                            print(f"{'预热' if warmup else '正式'} {round_number}/{args.warmup if warmup else args.count} {case[0]} "
                                  f"{'OK' if sample['ok'] else 'FAIL'} {sample['client_ms']:.1f} ms", flush=True)
                            if sample["transport_error"]:
                                raise RuntimeError("MCP 传输异常，停止后续调用以避免计时串位")
    report["scene_after"] = scene_fingerprint(arguments)
    report["scene_unchanged"] = report["scene_before"] == report["scene_after"]


def format_report(report: dict) -> str:
    """输出总量、阶段、同轮比较和逐次结果，单位统一为毫秒。"""
    lines = ["MCP 与直接截图耗时比较", f"开始时间：{report['started_at']}",
             f"每项正式 {report['count']} 次，预热 {report['warmup']} 次；串行、轮换顺序。",
             f"服务启动/初始化(ms)：{report.get('startup_ms', '未完成')}",
             f"前后场景一致：{report.get('scene_unchanged', '未完成，不能确认条件一致')}",
             f"配置字节不变：{report['config_unchanged']}", f"状态：{report['status']}",
             "client=调用至完整响应返回；server=日志工具体；extra=二者差额，包含协议/序列化/调度等，不是纯网络时间。",
             "直接截图也计入 connect；screenshot 阶段单列，不含连接。预热与失败不进入成功统计。",
             "服务阶段沿用现有埋点；capture_tree 是采集聚合阶段，没有虚构内部耗时。",
             "p50/p90/p99 使用最近秩法；小样本的尾部分位数仅供参考。"]
    if report.get("error"):
        lines.append("运行错误：" + report["error"])
    if not report.get("scene_unchanged"):
        lines.append("比较条件未确认一致，以下差值/倍数只能作为诊断数据，不能作为同场景结论。")
    for case, item in report["summary"].items():
        lines += ["", f"== {case} == 成功 {item['success']}，失败 {item['failed']}"]
        if item["success_rate"] is not None:
            lines.append(f"正式成功率：{item['success_rate']:.1%}")
        for metric in ("client_ms", "server_ms", "extra_ms"):
            if item[metric] is not None:
                lines.append(metric + " " + " ".join(f"{k}={v:.1f}" for k, v in item[metric].items()))
        for stage, stats in item["stages_ms"].items():
            lines.append(f"阶段 {stage} " + " ".join(f"{k}={v:.1f}" for k, v in stats.items()))
        pair = item["comparison"]
        if pair:
            lines.append(f"同轮直接截图比较：{pair['pairs']} 对，平均差 {pair['mean_delta_ms']:.1f} ms，均值比 {pair['ratio_of_means']:.2f}x")
    lines += ["", "逐次记录（阶段值为 ms）："]
    for sample in report["samples"]:
        lines.append(json.dumps(sample, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def main() -> int:
    """校验参数、执行并保存中断或失败时已有样本。"""
    parser = argparse.ArgumentParser(description="同场景比较 MCP 工具与直接截图，记录现有分阶段日志。")
    parser.add_argument("address", nargs="?", help="TV IP/主机名；不填读取 config.json，不含端口")
    parser.add_argument("--port", type=positive_int, help="ADB 端口；不填读取配置")
    parser.add_argument("--serial", help="USB 设备序列号；不能与网络地址或端口同时指定")
    parser.add_argument("--adb", help="ADB 路径；不填读取配置")
    parser.add_argument("-n", "--count", type=positive_int, default=10, help="每项正式次数，默认 10")
    parser.add_argument("--warmup", type=int, default=1, help="每项预热次数，默认 1，可为 0")
    parser.add_argument("--timeout", type=positive_int, default=120, help="MCP 单次响应超时秒数，默认 120")
    parser.add_argument("--output", type=Path, help="新的报告目录；默认 _temp/bench_mcp/<时间>")
    args = parser.parse_args()
    if args.warmup < 0:
        parser.error("warmup 不能为负数")
    try:
        options = connection_options(TV_IP_Address=args.address, port=args.port, adb=args.adb,
                                     serial=args.serial)
        arguments = ({"serial": options.serial, "adb": options.adb} if options.serial is not None else
                     {"TV_IP_Address": options.TV_IP_Address, "port": options.port, "adb": options.adb})
        output = (args.output or ROOT / "_temp" / "bench_mcp" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")).resolve()
        output.mkdir(parents=True, exist_ok=False)
        config_before = (ROOT / "config.json").read_bytes()
    except (ValueError, OSError) as error:
        print(f"参数、配置或输出目录错误：{error}", file=sys.stderr)
        return 2
    report = {"started_at": datetime.now().isoformat(timespec="seconds"), "count": args.count,
              "warmup": args.warmup, "target": options.target, "timeout_seconds": args.timeout,
              "environment": {"python": sys.version, "mcp": importlib.metadata.version("mcp"),
                              "uiautomator2": importlib.metadata.version("uiautomator2"), "adb": options.adb},
              "cases": [{"case": label, "tool": tool, "arguments": {**arguments, **overrides}} for label, tool, overrides in CASES],
              "samples": [], "status": "运行中"}
    exit_code = 0
    try:
        asyncio.run(run(args, arguments, output, report))
        if not report["scene_unchanged"] or any(not s["ok"] for s in report["samples"]):
            exit_code = 1
        report["status"] = "完成" if exit_code == 0 else "完成但存在失败或场景变化"
    except KeyboardInterrupt:
        exit_code = 130
        report["status"] = "已中断"
    except Exception as error:
        exit_code = 2
        report.update(status="运行错误", error=f"{type(error).__name__}: {error}")
    finally:
        try:
            report["config_unchanged"] = (ROOT / "config.json").read_bytes() == config_before
            if not report["config_unchanged"] and exit_code == 0:
                exit_code = 1
            report["summary"] = summarize_samples(report["samples"], [label for label, _, _ in CASES])
            report["exit_code"] = exit_code
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "report.txt").write_text(format_report(report), encoding="utf-8")
            print(f"报告：{output / 'report.txt'}")
        except OSError as error:
            print(f"报告写入失败：{error}；已有逐次数据见 {output}", file=sys.stderr)
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
