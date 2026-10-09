"""Check timing attribution and benchmark comparison offline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp.types import CallToolResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bench_mcp import (
    check_result, format_report, parse_timing, percentile, positive_int, summarize, summarize_samples,
)


def main() -> None:
    """验证真实日志形状、错误边界和成功同轮比较。"""
    assert positive_int("3") == 3
    for invalid in ("0", "-1", "abc"):
        try:
            positive_int(invalid)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError("次数必须是正整数")
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 99) == 4.0
    assert percentile([7.0], 90) == 7.0
    assert summarize([]) is None
    assert summarize([30.0, 10.0, 20.0]) == {
        "min": 10.0, "mean": 20.0, "p50": 20.0, "p90": 30.0, "p99": 30.0, "max": 30.0,
    }
    block = "noise\n[tv-uitree] 12:34:56.123 get_screen_summary  total 100.0 ms\n  connect 10.0 ms 10.0%\n  capture_tree 90.0 ms 90.0%\n"
    parsed = parse_timing(block, "get_screen_summary")
    assert parsed == {"server_ms": 100.0, "stages_ms": {"connect": 10.0, "capture_tree": 90.0}, "failed_stage": None}
    assert parse_timing(block.replace("\n", "\r\n"), "get_screen_summary") == parsed
    failed = parse_timing(block.replace("total 100.0 ms", "total 100.0 ms  failed at capture_tree"), "get_screen_summary")
    assert failed["failed_stage"] == "capture_tree"
    for invalid, tool in ((block, "get_visible_controls"), ("", "get_screen_summary"), (block + block, "get_screen_summary"),
                          (block.replace("90.0 ms 90.0%", "bad ms 90.0%"), "get_screen_summary")):
        try:
            parse_timing(invalid, tool)
        except ValueError:
            pass
        else:
            raise AssertionError("缺失、错配、重复或损坏日志必须拒绝")
    samples = [
        {"case": "direct_screenshot", "round": 1, "warmup": False, "ok": True, "client_ms": 10.0, "server_ms": 9.0, "stages_ms": {"screenshot": 8.0}},
        {"case": "get_screen_summary", "round": 1, "warmup": False, "ok": True, "client_ms": 30.0, "server_ms": 28.0, "stages_ms": {"capture_tree": 20.0}},
        {"case": "get_screen_summary", "round": 2, "warmup": False, "ok": True, "client_ms": 50.0, "server_ms": 48.0, "stages_ms": {"capture_tree": 40.0}},
        {"case": "direct_screenshot", "round": 2, "warmup": False, "ok": False, "client_ms": 1000.0},
        {"case": "get_screen_summary", "round": 0, "warmup": True, "ok": True, "client_ms": 9999.0},
        {"case": "get_screen_summary", "round": 3, "warmup": False, "ok": False, "client_ms": 9999.0},
    ]
    summary = summarize_samples(samples, ["direct_screenshot", "get_screen_summary", "get_visible_controls"])
    assert summary["get_screen_summary"]["success"] == 2 and summary["get_screen_summary"]["failed"] == 1
    assert summary["get_screen_summary"]["success_rate"] == 2 / 3
    assert summary["get_screen_summary"]["client_ms"]["mean"] == 40.0
    assert summary["get_screen_summary"]["server_ms"]["mean"] == 38.0
    assert summary["get_screen_summary"]["stages_ms"]["capture_tree"]["mean"] == 30.0
    assert summary["get_screen_summary"]["comparison"] == {"pairs": 1, "mean_delta_ms": 20.0, "ratio_of_means": 3.0}
    assert summary["get_visible_controls"]["client_ms"] is None and summary["get_visible_controls"]["comparison"] is None
    check_result(CallToolResult(content=[], structuredContent={"mode": "full"}), "get_full_tree")
    for data in ({"error": "capture failed"}, {"focus": {"status": "error"}}, {"status": "error"}):
        try:
            check_result(CallToolResult(content=[], structuredContent=data), "get_screen_summary")
        except ValueError:
            pass
        else:
            raise AssertionError("isError=false 的业务错误不能计入成功统计")
    text = format_report({"started_at": "offline", "count": 2, "warmup": 1,
                          "config_unchanged": True, "status": "已中断", "samples": samples,
                          "summary": summary})
    assert "不能作为同场景结论" in text and "阶段 capture_tree" in text
    print("压测离线自检通过：参数校验、最近秩统计、日志归属、失败阶段、预热/失败排除、同轮比较与空样本")


if __name__ == "__main__":
    main()
