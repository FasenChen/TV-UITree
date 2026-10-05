"""Tree command presentation and pruning diagnostics."""

from __future__ import annotations

import argparse
import sys

from tvuitree.application.observation import collect_full_json
from tvuitree.domain.tree.pruning import (
    OWNER_PRIORITY, PRUNE_SWITCHES, apply_prune, default_switches, parse_switch_spec,
)
from tvuitree.infrastructure.adb import AdbError
from .connection import connect_for_cli
from .json_io import emit_json_checked, load_full_json
from .terminal import C, c


def print_prune_list() -> None:
    print("剪枝开关（--mode slim 默认全部执行；--keep <名> 可关掉某个开关）\n")
    print("每个节点只由一个开关认领，按此优先序先命中先认领："
          + " → ".join(OWNER_PRIORITY) + "\n"
          "所以 --keep <名> 的语义是确定的：关掉它，这一类节点整类保留，"
          "不会被后面的开关顺手剪掉。\n")
    for name, (scope, on, desc) in PRUNE_SWITCHES.items():
        flag = "剪掉" if on else "保留"
        print(f"  {name:<10} [{scope}]  默认: {flag}")
        for i in range(0, len(desc), 56):
            print(f"      {desc[i:i + 56]}")
        print()


def _summary(obj: dict) -> None:
    """把「这次输出里有什么、可信度如何」打到 stderr。"""
    st = obj.get("align_stats") or {}
    nodes = _tree_size(obj.get("tree") or [])
    line = f"[tree] 节点 {nodes}"
    if st:
        line += (f" | a11y {st.get('a11y_nodes')} / dumpsys {st.get('view_nodes')}"
                 f" | 配对 {st.get('paired')} {st.get('by_reason')}"
                 f" | 几何 exact={st.get('geom_exact')} clip={st.get('geom_clip')}"
                 f" drift={st.get('geom_drift')} na={st.get('geom_na')}"
                 f" | 补入 {st.get('dumpsys_only_inserted')}"
                 f" | 未配对 dumpsys {st.get('view_unpaired')}")
    print(c(line, C.GRY), file=sys.stderr)
    if obj.get("slim"):
        s = obj["slim"]
        print(c(f"[slim] {s['nodes']['full']} → {s['nodes']['slim']} 节点；"
                f"剪枝明细 {s['pruned_nodes']}", C.GRY), file=sys.stderr)
    sc = obj.get("source_consistency") or {}
    if sc.get("drift"):
        print(c(f"[警告] 画面在动，配对结果可信度下降：{sc.get('detail')}", C.YEL),
              file=sys.stderr)
    if st.get("align_skipped"):
        print(c(f"[警告] {st['align_skipped']}", C.YEL), file=sys.stderr)


def _tree_size(nodes: list) -> int:
    """整棵树的节点数（含后代）。"""
    return sum(1 + _tree_size(n.get("children") or []) for n in nodes)


def _report_anomalies(items: list) -> None:
    if not items:
        return
    print(c(f"[解析告警] {len(items)} 行未能按格式完整解析——"
            "即存在「没读出来」的数据：", C.YEL), file=sys.stderr)
    for line, raw, reason in items[:8]:
        print(c(f"  第 {line} 行：{reason}", C.YEL), file=sys.stderr)
        print(c(f"    {raw}", C.GRY), file=sys.stderr)


def run_tree(args: argparse.Namespace) -> int:
    if args.prune_list:
        print_prune_list()
        return 0
    try:
        keep = parse_switch_spec(args.keep, list(PRUNE_SWITCHES))
    except ValueError as error:
        print(c(str(error), C.RED), file=sys.stderr)
        return 2
    if keep and args.mode != "slim":
        print(c("--keep 只在 --mode slim 下有意义；全量 JSON 本来就没有剪枝。", C.RED),
              file=sys.stderr)
        return 2
    if args.from_json and args.mode != "slim":
        print(c("从 JSON 再输出全量没有意义；请使用 --mode slim。", C.RED),
              file=sys.stderr)
        return 2
    switches = default_switches()
    for name in keep:
        switches[name] = False
    if args.from_json:
        try:
            result = load_full_json(args.from_json)
        except (OSError, ValueError, TypeError) as error:
            print(c(f"读不了 {args.from_json}：{type(error).__name__}: {error}", C.RED),
                  file=sys.stderr)
            return 2
    else:
        device = connect_for_cli(args)
        if device is None:
            return 2
        try:
            result = collect_full_json(
                adb=device, serial=device.serial, save_raw=args.save_raw,
                quiet=args.quiet, use_dumpsys=not args.no_dumpsys,
            )
        except AdbError as error:
            print(c(str(error), C.RED), file=sys.stderr)
            return 3
        except Exception as error:
            print(c(f"配对失败：{type(error).__name__}: {error}", C.RED), file=sys.stderr)
            return 3
        _report_anomalies(result.pop("_parse_anomalies", []))
    if args.mode == "slim":
        apply_prune(result, switches)
    failed = emit_json_checked(result, args.out)
    if failed is not None:
        return failed
    _summary(result)
    return 0
