#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_tree.py — 离线自检：不连设备、不联网、不需要 pytest

它锁什么
--------
本工具最容易坏的地方不是「跑不起来」，而是「跑起来了但结果悄悄变了」：
配对规则被放宽一格、剪枝开关的认领顺序被调换、树里凭空多出/漏掉节点……
这些都不会报错，只会让输出越来越不可信。所以自检用**离线夹具**把下面
几类行为钉死：

  1. dumpsys 解析   —— 缩进、字段宽度、res-id 写法、「有数据没读出来」要告警
  2. 坐标与谓词     —— 读数与派生值分离、res-id 归一化、类名谓词
  3. R0–R3 配对     —— 每条规则的命中数、几何四档（exact/clip/drift/na）、
                       类名替换计数，以及「view 节点一个不多一个不少」的守恒
  4. 全量 JSON      —— 字段口径、对齐统计、焦点、--no-dumpsys 不假装有数据
  5. 剪枝开关       —— 8 个开关各自剪掉什么、`--keep` 的语义确定性，
                       含一条**回归**（见下）
  6. 命令行         —— 离线重剪的各个分支与错误退出码、漂移判定
  7. 辅助脚本       —— 键码归一化、画框取坐标、祖先链溢出告警

夹具全部按**真机格式**手写（见 A11Y_SPEC / _dumpsys），不是「能跑就行」的
简化版 —— 简化过的夹具锁不住真实格式的坑。夹具的每一处形状都对应一条
已知的真机现象，代码注释里逐条写明。

回归锁在哪
----------
真机上 GONE 的 View 几乎都是零面积（`G.E...... 0,0-0,0` 这种）。若树级剪枝
开关不按固定优先序「一个节点只由一个开关认领」，`--keep gone` 把 GONE 节点
放过之后会立刻被 zeroarea 认领剪掉 —— 节点数一个不变，开关表里写着
「可保留」的选项实际不起作用，而这一点从输出上完全看不出来。
本自检用「`--keep gone` 必须得到 7 个节点而不是 6」把它钉死。

用法
----
  python tests/selftest_tree.py      # 全部通过 → 退出码 0；有失败 → 退出码 1
"""

from __future__ import annotations

import contextlib
import importlib.util
import asyncio
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from tvuitree.domain import component, observation as domain_observation, screenshot, visible as domain_visible
from tvuitree.domain.tree import models, parsing, matching, capture, output as tree_output, pruning
from tvuitree.application import input as remote_input, observation as application_observation
from tvuitree.infrastructure import adb, image
from tvuitree.interfaces import (cli, connection, terminal, timing, observe as observe_interface,
                                tree as tree_interface, visible as visible_interface)


# ================================================================== 断言收集器


class T:
    """极简断言收集：不中断，跑完所有组再汇总。"""

    def __init__(self) -> None:
        self.n = 0
        self.fail: list = []
        self._group = ""

    def group(self, name: str) -> None:
        self._group = name
        print(f"\n== {name} ==")

    def _bad(self, what: str, detail: str) -> None:
        self.fail.append(f"[{self._group}] {what} —— {detail}")
        print(f"  FAIL  {what}\n        {detail}")

    def eq(self, got, want, what: str) -> None:
        self.n += 1
        if got != want:
            self._bad(what, f"期望 {want!r}，实际 {got!r}")

    def ok(self, cond, what: str, detail: str = "") -> None:
        self.n += 1
        if not cond:
            self._bad(what, detail or "条件不成立")

    def has(self, container, key, what: str) -> None:
        self.n += 1
        if key not in container:
            self._bad(what, f"{key!r} 不在 {type(container).__name__} 里")

    def not_has(self, container, key, what: str) -> None:
        self.n += 1
        if key in container:
            self._bad(what, f"{key!r} 不该出现，实际值 {container[key]!r}")

    def summary(self) -> int:
        print("\n" + "=" * 62)
        if self.fail:
            print(f"自检失败：{len(self.fail)} 项不通过 / 共 {self.n} 条断言")
            for f in self.fail:
                print(f"  - {f}")
            return 1
        print(f"自检通过：{self.n} 条断言全部成立")
        return 0


t = T()


# ================================================================== 离线夹具


def _a11y_xml(spec, indent: int = 2) -> str:
    """把嵌套 spec 渲染成 uiautomator2 的 XML（属性名与顺序照真机）。"""
    order = ("index", "text", "resource-id", "class", "package", "content-desc",
             "checkable", "checked", "clickable", "enabled", "focusable", "focused",
             "scrollable", "long-clickable", "password", "selected",
             "visible-to-user", "bounds", "drawing-order", "hint", "display-id")
    pad = " " * indent
    out = []
    for i, s in enumerate(spec):
        at = {"index": str(i), "text": s.get("text", ""), "resource-id": s.get("rid", ""),
              "class": s["cls"], "package": "com.demo", "content-desc": s.get("desc", ""),
              "checkable": "false", "checked": "false", "clickable": "false",
              "enabled": "true", "focusable": "false", "focused": "false",
              "scrollable": "false", "long-clickable": "false", "password": "false",
              "selected": "false", "visible-to-user": "true", "bounds": s["bounds"],
              "drawing-order": str(i), "hint": s.get("hint", ""), "display-id": "0"}
        at.update(s.get("attrs") or {})
        attrs = " ".join(f'{k}="{at[k]}"' for k in order)
        kids = s.get("children") or []
        if kids:
            out.append(f"{pad}<node {attrs}>")
            out.append(_a11y_xml(kids, indent + 2))
            out.append(f"{pad}</node>")
        else:
            out.append(f"{pad}<node {attrs} />")
    return "\n".join(out)


# a11y 侧（主源）。**屏幕绝对坐标**，21 个属性。
#
# 形状与真机一一对应：
#   * 根节点是 FrameLayout[0,0][1920,1080] —— 它其实就是 DecorView
#     （DecorView extends FrameLayout，a11y 就报 FrameLayout）。
#     dumpsys 侧同一位置写的是 `DecorView@hash[Name]`，R0 把它们配起来。
#   * RecyclerView 的 a11y 类名是 androidx.*，而 view 侧是应用自己的子类
#     `com.demo.MyRecycler` —— 真机上自定义类名会被 a11y 换成框架类名。
#   * alpha / beta 的矩形与布局矩形**都不等**（真机：焦点项有 1.05 倍缩放动效）：
#       beta 靠 R2 焦点配对，alpha 只能靠 R3 子序列顺序配对，两者几何都是 drift 档。
#   * Gamma 的布局矩形比父容器高（0,700-1920,1300 超出 MyGrid 的 1080），
#     a11y 报的是**裁剪后**的 [0,700][1920,1080] → clip 档，同时它也是
#     tv_shot「祖先链溢出容器」告警的样本。
#   * 最后一个无 id / 无文字 / 无任何布尔标志的 FrameLayout 是 empty 开关的样本。
A11Y_SPEC = [
    {"cls": "android.widget.FrameLayout", "bounds": "[0,0][1920,1080]", "children": [
        {"cls": "com.demo.MyGrid", "bounds": "[0,0][1920,1080]", "children": [
            {"cls": "androidx.recyclerview.widget.RecyclerView", "rid": "com.demo:id/grid",
             "bounds": "[0,0][1920,800]", "attrs": {"scrollable": "true"}, "children": [
                 {"cls": "android.widget.TextView", "rid": "com.demo:id/alpha",
                  "text": "Alpha", "bounds": "[20,10][460,190]"},
                 {"cls": "android.widget.TextView", "rid": "com.demo:id/beta",
                  "text": "Beta", "bounds": "[468,-5][972,205]",
                  "attrs": {"focused": "true", "focusable": "true"}},
             ]},
            {"cls": "com.demo.Gamma", "rid": "com.demo:id/gamma",
             "bounds": "[0,700][1920,1080]"},
            {"cls": "android.widget.FrameLayout", "bounds": "[0,900][100,1000]"},
        ]},
    ]},
]

A11Y = ('<?xml version=\'1.0\' encoding=\'UTF-8\' standalone=\'yes\' ?>\n\n'
        '<hierarchy rotation="0">\n' + _a11y_xml(A11Y_SPEC) + "\n</hierarchy>\n")


def _dumpsys(alpha_bounds: str = "0,0-480,200", clock: str = "1 (1 ms ago)") -> str:
    """dumpsys activity top（补充源）。缩进每层 2 空格，起点 6。

    形状与真机一一对应：
      * `DecorView@hash[Name]` 这一行**没有 flags、也没有 bounds** ——
        dumper 对根就是这么写的。所以根节点配对上之后几何只能记 na。
      * flags1 恒 9 位、flags2 恒 8 位。beta 的 flags2 第 2 位是 'F' = 持有焦点。
      * `app:id/x` 是 ViewDebug 对应用自身资源 id 的固定写法，要归一化后
        才能和 a11y 的 `com.demo:id/x` 比。
      * `{}` 里的实例 hash 是**十六进制**（真机如 8d2f90b）。这里照写十六进制：
        写成 `ggg` 之类非十六进制字符会让整行匹配失败、树从那里断掉 ——
        这个坑自检自己踩过一次，所以夹具必须保持真实形状。
      * hidden：GONE **且** bounds 是 0,0-0,0（真机实测 GONE 节点全都是零面积，
        这正是剪枝认领顺序那条回归的来源）。
      * off：2000,0-2400,200 完全在 1920 宽的屏幕外。
      * zero：0,300-0,500 宽度为 0（可见但零面积，与 GONE 不同）。
      * lll：与 a11y 那个空 FrameLayout 对应的零信息节点（它是可见的，
        用来证明 empty 开关剪的是「信息」，不是「可见性」）。
    """
    return "\n".join([
        "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0 uid=10100 "
        "displayId=0(type=INTERNAL)",
        "    Local Activity 1234 State:",
        f"      mResumed=true mLastFrameTime={clock}",
        "    View Hierarchy:",
        "      DecorView@6e60694[MainActivity]",
        "        com.demo.MyGrid{8d2f90b V.E...... ......ID 0,0-1920,1080}",
        "          com.demo.MyRecycler{b2ada01 V.E...... ......ID 0,0-1920,800 app:id/grid}",
        "            android.widget.TextView{f4a126d V.E...... ......ID "
        f"{alpha_bounds} app:id/alpha}}",
        "            android.widget.TextView{de6fd27 VFE...... .F....ID 480,0-960,200 "
        "app:id/beta}",
        "            android.widget.TextView{abf7e83 G.E...... ......I. 0,0-0,0 app:id/hidden}",
        "            android.widget.TextView{6cd2698 V.E...... ......ID 2000,0-2400,200 "
        "app:id/off}",
        "            android.widget.FrameLayout{866f800 V.E...... ......ID 0,300-0,500 "
        "app:id/zero}",
        "          com.demo.Gamma{33793e8 V.E...... ......ID 0,700-1920,1300 app:id/gamma}",
        "          android.widget.FrameLayout{367c839 V.E...... ......ID 0,900-100,1000}",
        "",
    ])


DUMPSYS = _dumpsys()
SCREEN = {"width": 1920, "height": 1080, "density": 320}
WIN = {"component": "com.demo/.MainActivity", "focus": "com.demo/.MainActivity"}
PKG = "com.demo"
SCR = (0, 0, 1920, 1080)

# 夹具形状的期望值（多组断言共用；改夹具必须同步改这里）
EXP_A11Y_NODES = 7      # 根 / MyGrid / RV / alpha / beta / Gamma / 空 FrameLayout
EXP_VIEW_NODES = 10     # DecorView MyGrid MyRecycler alpha beta hidden off zero Gamma lll
EXP_PAIRED = 7
EXP_INSERTED = 3        # hidden off zero：位次由 view 子序列唯一确定 → 并入主树
EXP_TREE_NODES = EXP_PAIRED + EXP_INSERTED     # 统一树节点数 = 10


def build_fixture() -> dict:
    """离线跑一遍「解析 → 配对 → 全量 JSON」，产出后续所有断言用的样本。"""
    blocks = parsing.parse_dumpsys_top(DUMPSYS)
    u2_roots = parsing.parse_u2_xml(A11Y)
    view_roots = blocks[0].roots
    st = matching.align(u2_roots, view_roots, PKG, SCR)
    obj = tree_output.build_full_json(
        u2_roots, view_roots,
        {"version": "3.7.0", "info": {"displayWidth": 1920, "displayHeight": 1080}},
        {"model": "SELFTEST", "release": "14", "sdk": "34"},
        SCREEN, WIN, st, PKG,
        {"drift": False, "drift_detail": None, "pick_note": None}, True)
    return {"blocks": blocks, "u2_roots": u2_roots, "view_roots": view_roots,
            "st": st, "obj": obj}


FX = build_fixture()
OBJ = FX["obj"]
ST = FX["st"]


def count(nodes: list) -> int:
    """节点数（含后代）。"""
    return sum(1 + count(n.get("children") or []) for n in nodes)


def flat(nodes: list) -> list:
    out = []
    for n in nodes:
        out.append(n)
        out.extend(flat(n.get("children") or []))
    return out


def find(nodes: list, **kv):
    """按顶层字段找第一个节点，找不到返回 None。"""
    for n in flat(nodes):
        if all(n.get(k) == v for k, v in kv.items()):
            return n
    return None


def clean(obj: dict) -> dict:
    """apply_prune 是原地改的 → 每次都要一份深拷贝。"""
    return json.loads(json.dumps(obj))


def run_cli(argv: list, out: str) -> tuple:
    """跑一次 main()，收走 stdout/stderr；返回 (退出码, 输出文件解析结果或 None)。"""
    o, e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        command = "observe" if "observe" in argv else "tree"
        migrated = list(argv)
        if command == "observe":
            index = migrated.index("--mode")
            del migrated[index:index + 2]
        rc = cli.main([command] + migrated)
    data = None
    if out and os.path.exists(out):
        with open(out, "r", encoding="utf-8") as f:
            data = json.load(f)
    return rc, data


TD = tempfile.mkdtemp(prefix="tvuitree_selftest_")
FULL_PATH = os.path.join(TD, "full.json")
with open(FULL_PATH, "w", encoding="utf-8") as _f:
    json.dump(OBJ, _f, ensure_ascii=False, indent=2)


# ================================================================== 0. 设备接入层

t.group("0. 统一入口的设备参数与连接选项")

for name in ("observe", "tree", "input", "shot"):
    command_parser = cli.build_parser()._subparsers._group_actions[0].choices[name]
    help_text = command_parser.format_help()
    for opt in ("--TV_IP_Address", "--port", "--adb", "--no-connect",
                "--no-color", "--quiet"):
        t.ok(opt in help_text, f"{name} 要有公共设备参数 {opt}")
    for removed in ("--host", "--serial", "--address"):
        t.ok(removed not in help_text, f"{name} 不再提供 {removed}")
t.eq(adb.resolve_adb("X:/adb.exe"), "X:/adb.exe", "显式指定的 adb 路径优先（不查文件系统）")
t.eq(component.normalize_component("com.demo/.MainActivity"),
     ("com.demo", "com.demo.MainActivity"), "`.Cls` 写法要补全包名")
t.eq(component.normalize_component("com.demo/.MainActivity"),
     component.normalize_component("com.demo/com.demo.MainActivity"),
     "同一个 component 的两种写法必须归一化成同一个值（否则段匹配会时不时失手）")
t.eq(component.normalize_component("没有斜杠"), None, "不合法输入返回 None（不猜）")
t.eq(component.normalize_component(None), None, "None 输入")
t.eq(component.component_from_activity_record(
    "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0"),
    "com.demo/.MainActivity", "从 ACTIVITY 行取 component")
t.eq(component.component_from_window(
    "  mFocusedWindow=Window{abc u0 com.demo/.MainActivity}"),
    "com.demo/.MainActivity", "从 window dump 取 component")
with open(os.path.join(os.path.dirname(__file__), "..", "config.json"), encoding="utf-8") as _f:
    _device_config = json.load(_f)
t.eq(connection.options_from_args(
    cli.build_parser().parse_args(["input"])
).target, f"{_device_config['TV_IP_Address']}:{_device_config['port']}",
     "设备默认目标由 config.json 读取")
t.eq(connection.options_from_args(cli.build_parser().parse_args(["input"])).adb,
     _device_config["adb"], "ADB 默认路径由 config.json 读取")
t.eq(connection.options_from_args(cli.build_parser().parse_args(
    ["input", "--adb", "X:/adb.exe"]
)).adb, "X:/adb.exe", "显式 ADB 路径覆盖配置")
t.eq(connection.options_from_args(
    cli.build_parser().parse_args(["input", "--TV_IP_Address", "1.2.3.4"])
).target, f"1.2.3.4:{_device_config['port']}", "显式 IP 覆盖配置，端口沿用配置")
t.eq(connection.options_from_args(
    cli.build_parser().parse_args(["input", "--port", "1234"])
).target, f"{_device_config['TV_IP_Address']}:1234", "显式端口覆盖配置，IP 沿用配置")
_CN = ("R", "B", "DIM", "RED", "GRN", "YEL", "BLU", "MAG", "CYA", "GRY")
_saved = {k: getattr(terminal.C, k) for k in _CN}
_saved_on = terminal.C._on
terminal.C.off()
t.eq(terminal.c("x", terminal.C.RED), "x", "关色后 c() 返回原文（重定向到文件时不带转义码）")
terminal.C._on = _saved_on
for _k, _v in _saved.items():
    setattr(terminal.C, _k, _v)


# ================================================================== 1. dumpsys 解析

t.group("1. dumpsys 解析")

blocks = FX["blocks"]
t.eq(len(blocks), 1, "应解析出 1 个 ACTIVITY 段")
blk = blocks[0]
t.eq(blk.component, "com.demo/.MainActivity", "段名")
t.eq(blk.pid, "100", "pid")
t.eq(len(blk.roots), 1, "段内应有 1 个根")
root = blk.roots[0]
t.eq(root.cls, "DecorView", "根类名不带包名（DecorView@hash[Name] 形式）")
t.eq(root.oname, "MainActivity", "根节点 [] 内的名字")
post_name = parsing.parse_node_line(
    "com.android.internal.policy.DecorView{e99bd3f I.ED..... R.....ID "
    "0,0-1920,1080 aid=0}[MainSettings]", 1, 6)
t.eq(post_name.oname if post_name else None, "MainSettings",
     "Android 16 的 DecorView{...}[Name] 后置名字格式")
t.eq(root.bounds, None, "根节点**没有** bounds —— dumper 就是这么写的")
t.eq(root.flags1, None, "根节点**没有** flags")
t.eq(len(blk.all_nodes), EXP_VIEW_NODES, "段内 view 节点总数")

grid = root.children[0]
t.eq(grid.cls, "com.demo.MyGrid", "根的唯一直系子节点")
t.ok(grid.parent is root, "父子指针要双向建立（绝对坐标靠它累加）")
t.eq(grid.children[0].cls, "com.demo.MyRecycler", "第三层")

beta = [n for n in blk.all_nodes if n.res_id == "app:id/beta"][0]
t.eq((beta.flags1, beta.flags2), ("VFE......", ".F....ID"), "flags1=9 位 / flags2=8 位")
t.eq(beta.bounds, (480, 0, 960, 200), "bounds 是相对父容器的布局矩形")
t.eq(beta.focused, True, "flags2 第 2 位 'F' = 持有焦点")
t.eq(beta.focusable, True, "flags1 第 2 位 'F' = 可聚焦")
t.eq(beta.visible, True, "flags1 首位 'V' = 可见")
t.eq(beta.res_id, "app:id/beta", "res-id 原样保留 app: 前缀（归一化是谓词的事）")

hidden = [n for n in blk.all_nodes if n.res_id == "app:id/hidden"][0]
t.eq(hidden.gone, True, "flags1 首位 'G' = GONE")
t.eq(hidden.visible, False, "GONE 不算可见")
t.eq(hidden.bounds, (0, 0, 0, 0), "GONE 节点零面积（真机实测如此，见剪枝回归）")

zero = [n for n in blk.all_nodes if n.res_id == "app:id/zero"][0]
t.eq(zero.gone, False, "zero 节点不是 GONE")
t.eq(zero.bounds, (0, 300, 0, 500), "zero 节点可见但宽度为 0")
t.eq(zero.scrollbar_v, False, "scrollbar_* 只表示滚动条是否启用，不是「可滚动」")

# 有字段却没读出来 → 必须告警，不能静默丢数据
BAD = "\n".join([
    "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0",
    "    View Hierarchy:",
    "      DecorView@a1[X]",
    "        android.widget.FrameLayout{aaa V.E...... ......ID}",
    "",
])
bad_blocks = parsing.parse_dumpsys_top(BAD)
anom = list(models.PARSE_ANOMALIES)
t.eq(len(bad_blocks), 1, "畸形 dump 仍能出段（不因个别行放弃整棵树）")
t.ok(any("bounds" in w for _, _, w in anom),
     "「有字段却没解析出 bounds」要记成解析告警", f"实际告警 {anom}")
BAD2 = "\n".join([
    "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0",
    "    View Hierarchy:",
    "      DecorView@a1[X]",
    "         com.demo.T{bbb V.E...... ......ID 0,0-10,10}",
    "",
])
parsing.parse_dumpsys_top(BAD2)
t.ok(any("整数倍" in w for _, _, w in models.PARSE_ANOMALIES),
     "缩进不是 2 的倍数要记成解析告警（层级可能错位，不能默默吞掉）",
     f"实际告警 {models.PARSE_ANOMALIES}")
parsing.parse_dumpsys_top(DUMPSYS)
t.eq(models.PARSE_ANOMALIES, [], "正常 dump 不该产生任何解析告警")


# ================================================================== 2. 坐标与谓词

t.group("2. 坐标换算与谓词（读数 / 派生值分离）")

gamma_v = [n for n in blk.all_nodes if n.res_id == "app:id/gamma"][0]
t.eq(matching.absolute_bounds(gamma_v), (0, 700, 1920, 1300),
     "absolute_bounds = 沿祖先链累加（**派生值**，dump 不含 scrollX/scrollY）")
t.eq(matching.clip_to_chain(gamma_v, None), (0, 700, 1920, 1080),
     "clip_to_chain = 再与各祖先求交 → 裁剪后的可见矩形")
t.eq(matching.pred_visible_rect(gamma_v, SCR), (0, 700, 1920, 1080),
     "pred_visible_rect = 再与屏幕求交")
t.eq(matching.absolute_bounds(root), None, "根节点没 bounds → 派生值也给不出（不猜）")

t.eq(matching.intersect((0, 0, 10, 10), (20, 20, 30, 30)), (20, 20, 20, 20),
     "无交集 → 退化成零面积矩形（判「屏幕外」就靠它）")
t.eq(matching.intersect(None, (1, 2, 3, 4)), (1, 2, 3, 4), "None 视作无约束")

t.eq(matching.norm_res_id("app:id/x", "com.demo"), "com.demo:id/x",
     "ViewDebug 的 app:id/ 要归一化成 <包名>:id/")
t.eq(matching.norm_res_id("android:id/content", "com.demo"), "android:id/content",
     "android: 前缀原样保留")
t.eq(matching.norm_res_id(None, "com.demo"), None, "None 仍是 None")
t.eq(matching.norm_res_id("app:id/x", None), "app:id/x", "不知道包名就不动它（不猜）")

t.eq(matching.is_framework_cls("android.widget.TextView"), True, "android.widget.* 是框架类")
t.eq(matching.is_framework_cls("androidx.recyclerview.widget.RecyclerView"), False,
     "androidx.* **不**算框架类 —— a11y 不替换它，也就不能拿它当配对硬条件")
t.eq(matching.is_framework_cls("com.demo.MyGrid"), False, "自定义类不是框架类")

u_all = matching.u2_all(FX["u2_roots"])
u_beta = [n for n in u_all if n.res_id == "com.demo:id/beta"][0]
u_grid = [n for n in u_all if n.cls == "com.demo.MyGrid"][0]
u_rec = [n for n in u_all if n.res_id == "com.demo:id/grid"][0]
my_rec = [n for n in blk.all_nodes if n.res_id == "app:id/grid"][0]

t.eq(matching.class_ok(beta, u_beta), (True, False), "框架类且同名 → 通过、无替换")
t.eq(matching.class_ok(grid, u_grid), (True, False), "自定义类同名 → 通过、无替换")
t.eq(matching.class_ok(my_rec, u_rec), (True, True),
     "自定义类名被 a11y 换成框架类名 → 通过、记一次「类名替换」")
t.eq(matching.class_ok(models.Node(cls="android.widget.TextView"), u_rec)[0], False,
     "框架类名不等 → **拒绝**配对（框架类不会被 a11y 替换，不等就是配错了）")

t.eq(matching.resid_ok(my_rec, u_rec, PKG), True, "res-id 归一化后相等")
t.eq(matching.resid_ok(beta, u_rec, PKG), False, "res-id 不等")
t.eq(matching.resid_ok(grid, u_grid, PKG), True, "两侧都是 None 也算相等（同为 None 不比）")


# ================================================================== 3. R0–R3 配对

t.group("3. R0–R3 配对")

t.eq(ST.a11y_nodes, EXP_A11Y_NODES, "a11y 节点数")
t.eq(ST.view_nodes, EXP_VIEW_NODES, "view 节点数")
t.eq(ST.paired, EXP_PAIRED, "配对成功数（= 配上的 a11y 节点数）")

# 每条规则各命中几个
t.eq(ST.by_reason, {"root": 1, "geom": 4, "focus": 1, "seq": 1},
     "各规则的命中数（root=根 / geom=矩形锚定 / focus=焦点锚定 / seq=子序列顺序）")

# 几何四档：判据是「未裁剪的累加布局矩形」vs「a11y 屏幕读数」
t.eq((ST.geom_exact, ST.geom_clip, ST.geom_drift, ST.geom_na), (3, 1, 2, 1),
     "几何档位 exact/clip/drift/na")
t.eq(ST.geom_exact + ST.geom_clip + ST.geom_drift + ST.geom_na, ST.paired,
     "四档之和必须等于配对总数（不允许有节点没被归过档）")
t.eq(ST.class_substituted, 2,
     "类名替换计数：MyRecycler → androidx.RecyclerView，以及 DecorView → FrameLayout"
     "（a11y 把 DecorView 报成它继承的框架类，所以根节点也算一次）")
t.eq(ST.a11y_unpaired, [], "本夹具里每个 a11y 节点都该配上")
t.eq(ST.view_unpaired, [], "本夹具里每个 view 节点都该有去处（配上或补入）")
t.eq(ST.seq_refused, [], "本夹具没有「歧义/无解」的子序列对齐")
t.eq(ST.unexplained, [], "不该出现「可见有面积却未被 a11y 收录」的节点")

# 守恒律：每个 view 节点恰好属于「配上 / 补入 / 未定位」三者之一。
# 这条一旦破了，说明统一树里凭空多出或漏掉了节点。
t.eq(ST.paired + len(ST.insert_pos) + len(ST.view_unpaired), ST.view_nodes,
     "view 节点守恒：配上 + 补入 + 未定位 == view 节点总数")
t.eq(len(ST.insert_pos), EXP_INSERTED, "补入主树的 dumpsys 节点数（GONE/屏外/零面积）")
t.eq(sorted(ST.insert_pos), sorted(id(n) for n in blk.all_nodes
                                   if n.res_id in ("app:id/hidden", "app:id/off",
                                                   "app:id/zero")),
     "补入的正是 hidden/off/zero 三个（位次由 view 子序列唯一确定）")

t.eq(sorted(u.match_reason for u in u_all),
     ["focus", "geom", "geom", "geom", "geom", "root", "seq"], "逐节点配对依据")

# 子序列对齐「宁缺毋滥」：多解（歧义）与无解都要被拒，并且**说明原因**，
# 不能随便挑一个解顶上 —— 挑错一个，整棵子树的层级就全错了。
def _amb_case(u_rids, v_rids):
    kids_u = [models.U2Node(raw={}, cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                             res_id=r) for r in u_rids]
    kids_v = [models.Node(cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                           res_id=r) for r in v_rids]
    pu = models.U2Node(raw={}, cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                        children=kids_u)
    pv = models.Node(cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                      children=kids_v)
    return matching.align([pu], [pv], PKG, None)


st_multi = _amb_case([None, None], [None, None, None])
t.eq(len(st_multi.seq_refused), 1, "2 个子节点注入 3 个候选 → 多解，必须拒绝配对")
t.ok("歧义" in st_multi.seq_refused[0][2], "多解的拒绝原因要写「歧义」",
     f"实际 {[w for _, _, w in st_multi.seq_refused]}")
t.eq(st_multi.paired, 1, "被拒的子序列只剩 R0 的根配对（宁缺毋滥）")
st_none = _amb_case(["com.demo:id/only"], ["app:id/other"])
t.eq(len(st_none.seq_refused), 1, "res-id 一个都对不上 → 无解，必须拒绝")
t.ok("无解" in st_none.seq_refused[0][2], "无解的拒绝原因要写「无解」",
     f"实际 {[w for _, _, w in st_none.seq_refused]}")
st_uni = _amb_case(["com.demo:id/only"], ["app:id/other", "app:id/only"])
t.eq((st_uni.paired, st_uni.seq_refused), (2, []),
     "位次唯一确定时才采用（只有 1 个子节点且在候选里只出现一次）")


# ================================================================== 4. 统一树与全量 JSON

t.group("4. 统一树与全量 JSON")

uni = matching.build_unified(FX["u2_roots"], FX["view_roots"], ST, SCR)
t.eq(len(uni), 1, "统一树只有 1 个根")
uni_flat: list = []


def _walk(ns):
    for n in ns:
        uni_flat.append(n)
        _walk(n.children)


_walk(uni)
t.eq(len(uni_flat), EXP_TREE_NODES, "统一树节点数（a11y 骨架 + 位次确定的 dumpsys 节点）")
t.eq(sum(1 for n in uni_flat if n.kind == "a11y"), EXP_A11Y_NODES, "统一树里的 a11y 节点数")
t.eq(sum(1 for n in uni_flat if n.kind == "dumpsys"), EXP_INSERTED,
     "统一树里的 dumpsys 节点数")

t.eq(OBJ["mode"], "full", "全量 JSON 的 mode")
t.eq(OBJ["primary_source"], "uiautomator2 (a11y)", "主源标注")
t.eq(OBJ["supplement_source"], "dumpsys activity top (View Hierarchy)", "补充源标注")
t.has(OBJ, "captured_at", "要有采集时刻（tv_shot 靠它判断截图与取树是否同时刻）")
t.eq(count(OBJ["tree"]), EXP_TREE_NODES, "全量树节点数")
t.eq(OBJ["dumpsys_only"], [], "本夹具没有「位置无法确定」的 dumpsys 节点")
t.eq(OBJ["segment"], PKG, "段包名")
t.eq(OBJ["source_consistency"]["drift"], False, "两次 dumpsys 一致的标注")

# a11y 侧坐标是**屏幕读数**，dumpsys 侧是**相对父容器的布局读数**，不能混
a_beta = find(OBJ["tree"], resource_id="com.demo:id/beta")
t.eq(a_beta["source"], "a11y", "主源节点 source=a11y")
t.eq(a_beta["bounds_screen"], [468, -5, 972, 205], "a11y 坐标原样输出（读数，不换算）")
t.eq(a_beta["dumpsys"]["bounds_local"], [480, 0, 960, 200],
     "配对上的 dumpsys 布局读数放在 dumpsys 子字典里")
t.eq(a_beta["dumpsys"]["bounds_abs_unclipped"], [480, 0, 960, 200], "派生累加值单独标注")
t.eq(a_beta["geom_check"], "drift", "焦点项 1.05 倍缩放 → drift 档")

# dumpsys 节点的资源 id **原样输出**（app:id/x），归一化值另放一个字段 ——
# 读数不加工，加工过的值必须让人一眼看出是哪一个。
d_hidden = find(OBJ["tree"], resource_id="app:id/hidden")
t.eq(d_hidden["source"], "dumpsys", "补入的节点 source=dumpsys")
t.eq(d_hidden["bounds_local"], [0, 0, 0, 0], "dumpsys 节点坐标是相对父容器的读数")
t.eq(d_hidden["resource_id"], "app:id/hidden", "dumpsys 侧 res-id 原样输出（读数不加工）")
t.eq(d_hidden["resource_id_normalized"], "com.demo:id/hidden",
     "归一化后的 res-id 单独放一个字段")
t.eq(d_hidden["gone"], True, "GONE 标志来自 flags1")
t.eq(d_hidden["why_not_in_a11y"], "GONE（a11y 不收录不可见节点）", "未收录原因逐条归因")
t.not_has(d_hidden, "text", "dumpsys 侧**没有**文字字段（ViewDebug 不调 getText()）")

t.eq(find(OBJ["tree"], resource_id="app:id/off")["why_not_in_a11y"],
     "裁剪后无可见部分（在屏幕外，或位于滚动容器可视区之外）", "屏外归因")
t.eq(find(OBJ["tree"], resource_id="app:id/zero")["why_not_in_a11y"],
     "零面积（自身布局矩形为空，不占布局）", "零面积归因")
t.eq(d_hidden["position_by"][:2], "R3", "补入节点的位次依据要写明是 R3（不是推测）")

cn = OBJ["coordinate_note"]
for k in ("bounds_screen", "bounds_local", "bounds_abs_unclipped", "pred_visible_rect"):
    t.has(cn, k, f"coordinate_note 必须解释 {k}")
t.ok("派生值" in cn["bounds_abs_unclipped"], "累加坐标要明确标注是派生值")

alc = OBJ["align_stats"]
t.eq(alc["paired"], EXP_PAIRED, "align_stats.paired")
t.eq(alc["dumpsys_only_inserted"], EXP_INSERTED, "align_stats.dumpsys_only_inserted")
t.eq(alc["view_unpaired"], 0, "align_stats.view_unpaired")
t.eq(alc["geom_exact"], 3, "align_stats.geom_exact")
t.eq(alc["geom_na"], 1, "align_stats.geom_na")
t.eq(alc["class_substituted"], 2, "align_stats.class_substituted")
t.ok(OBJ["align_rules"]["R3"].startswith("父已配对时"), "R3 规则要写清楚")

t.eq(len(OBJ["focus"]), 1, "焦点节点数")
t.eq(OBJ["focus"][0]["text"], "Beta", "焦点节点文字")
t.eq(OBJ["focus"][0]["bounds_screen"], [468, -5, 972, 205], "焦点坐标是 a11y 读数")
t.ok(OBJ["focus"][0]["path"].endswith("TextView"), "焦点路径按祖先链给出")

# 模型观察层：焦点状态、上下文、精简页面和证据必须来自同一份 full JSON
obs = application_observation.collect_observation(full_json=OBJ, max_nodes=4)
t.eq(obs["schema_version"], "tv-observation/v1", "观察结果 schema 版本")
t.eq(obs["mode"], "observe", "观察结果 mode")
t.eq(obs["focus"]["status"], "found", "唯一焦点 → found")
t.eq(obs["focus"]["candidate_count"], 1, "观察结果焦点候选数")
t.eq(obs["focus"]["node"]["labels"], ["Beta"], "观察焦点文字")
t.has(obs["focus"], "context", "观察结果包含焦点上下文")
t.eq(obs["page"]["summary_node_count"], 4, "观察页面摘要受 max_nodes 限制")
t.eq(obs["page"]["summary_truncated"], True, "页面摘要超出上限时显式标记")
t.has(obs["evidence"], "align_stats", "观察结果保留配对统计")
t.eq(obs["warnings"], [], "稳定夹具没有观察告警")

amb = clean(OBJ)
find(amb["tree"], resource_id="com.demo:id/alpha")["focused"] = True
amb["focus"] = []
amb_obs = application_observation.collect_observation(full_json=amb)
t.eq(amb_obs["focus"]["status"], "ambiguous", "多个焦点 → ambiguous")
t.eq(amb_obs["focus"]["candidate_count"], 2, "多个焦点候选全部保留")
missing = clean(OBJ)
for _node in flat(missing["tree"]):
    _node.pop("focused", None)
missing["focus"] = []
missing_obs = application_observation.collect_observation(full_json=missing)
t.eq(missing_obs["focus"]["status"], "missing", "无焦点 → missing")
t.eq(domain_observation.error_observation("采集失败")["focus"]["status"], "error", "采集异常 → error")

# 同一份输入跑两次，结果必须一致
t.eq(json.dumps(clean(OBJ)["tree"]), json.dumps(OBJ["tree"]), "同输入 → 同输出（树部分）")

# --no-dumpsys：只剩主源，且必须**不假装**有 dumpsys 信息
nd_roots = parsing.parse_u2_xml(A11Y)                      # 全新解析：不带任何配对结果
nd_st = matching.align(nd_roots, [], None, None)
t.eq(nd_st.paired, 0, "--no-dumpsys 时不做任何配对")
no_d = tree_output.build_full_json(nd_roots, [], {"version": "x", "info": {}},
                               {}, SCREEN, WIN, nd_st, None, None, show_dumpsys=False)
t.eq(no_d["supplement_source"], None, "--no-dumpsys 时补充源标注为 None")
t.eq(count(no_d["tree"]), EXP_A11Y_NODES, "--no-dumpsys 时树只剩 a11y 节点")
t.eq(no_d["dumpsys_only"], [], "--no-dumpsys 时不输出 dumpsys 章节")
t.ok(all("dumpsys" not in n for n in flat(no_d["tree"])),
     "--no-dumpsys 时节点上没有 dumpsys 子字典")
t.eq(no_d["align_stats"]["view_nodes"], 0, "--no-dumpsys 时 view 节点数为 0")

# 包名不一致：a11y 与所选 dumpsys 段不是同一个窗口（真机上前台是对话框/输入法、
# 段匹配回退时会出现）→ 不做任何配对，节点上也不能残留配对结果或补入节点
mm_snap = {"xml": A11Y, "block": parsing.parse_dumpsys_top(DUMPSYS, [])[0],
           "pkg": "com.other", "pick_note": "fixture note", "screen": SCREEN,
           "drift": False, "drift_detail": None}
mm_roots, mm_views, mm_st = capture.run_align(mm_snap, True)
mm = tree_output.build_full_json(mm_roots, mm_views, {"version": "x", "info": {}},
                                 {}, SCREEN, WIN, mm_st, mm_snap["pkg"], mm_snap)
t.ok(mm["align_stats"]["align_skipped"], "包名不一致时写明跳过配对")
t.eq(mm["align_stats"]["paired"], 0, "包名不一致时配对数为 0")
t.ok(all(u.view is None and u.match_reason is None for u in matching.u2_all(mm_roots)),
     "包名不一致时 a11y 节点上不残留配对结果")
t.eq(count(mm["tree"]), EXP_A11Y_NODES, "包名不一致时树只剩 a11y 节点")
t.ok(all(n["source"] == "a11y" and "dumpsys" not in n and n.get("geom_check") is None
         for n in flat(mm["tree"])),
     "包名不一致时树里没有另一个窗口的 dumpsys 证据")
t.eq(mm["align_stats"]["view_unpaired"], EXP_VIEW_NODES,
     "包名不一致时 view 节点全部未定位（守恒）")
t.eq(mm["align_stats"]["window_note"], "fixture note", "包名不一致时保留段匹配说明")

# dumpsys_only 是「未定位节点」组成的森林：每个未定位节点恰好输出一次，
# 已配对的后代只出现在主树里（否则同一个 View 会被列两次、画两个框）
t.eq(len(mm["dumpsys_only"]), 1, "全部未定位时 dumpsys_only 只有 DecorView 一棵子树")
t.eq(count(mm["dumpsys_only"]), EXP_VIEW_NODES, "嵌套的未定位节点在 dumpsys_only 里只出现一次")
nest_snap = {
    "xml": ("<hierarchy rotation='0'><node class='android.widget.TextView' "
            "package='com.demo' text='A' bounds='[0,0][480,200]'/></hierarchy>"),
    "pkg": PKG, "pick_note": None, "screen": SCREEN, "drift": False, "drift_detail": None,
    "block": parsing.parse_dumpsys_top("\n".join([
        "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0",
        "    View Hierarchy:",
        "      android.widget.FrameLayout{bbb0001 V.E...... ......ID 0,0-1920,1080}",
        "        android.widget.TextView{bbb0002 V.E...... ......ID 0,0-480,200}",
        "      android.widget.FrameLayout{bbb0003 V.E...... ......ID 0,0-10,10}",
        "",
    ]), [])[0],
}
nest_roots, nest_views, nest_st = capture.run_align(nest_snap, True)
nest = tree_output.build_full_json(nest_roots, nest_views, {"version": "x", "info": {}},
                                   {}, SCREEN, WIN, nest_st, PKG, nest_snap)
t.eq(nest_st.by_reason, {"geom": 1}, "两个 view 根时只有子节点靠 R1 配上")
t.eq(sorted(n["view_hash"] for n in flat(nest["dumpsys_only"])), ["bbb0001", "bbb0003"],
     "已配对的后代不在 dumpsys_only 里重复输出")
t.eq(count(nest["dumpsys_only"]), nest["align_stats"]["view_unpaired"],
     "dumpsys_only 节点数 == 未定位节点数")
t.eq(len(screenshot.collect(nest, "all", "dumpsys")[0]), 3,
     "每个 View 只画一个派生框（配对节点 1 个 + 未定位 2 个）")


# ================================================================== 5. 剪枝

t.group("5. 剪枝：开关语义与 --keep 增量")

SW = pruning.default_switches()
t.eq(sorted(SW), ["defaults", "derived", "empty", "gone", "instance", "meta",
                  "offscreen", "zeroarea"], "8 个开关")
t.ok(all(SW.values()), "默认状态下每个开关都执行剪枝")
t.eq(sorted(pruning.PRUNE_SWITCHES), sorted(SW), "开关表与默认值表必须同名同数")
t.eq(pruning.OWNER_PRIORITY, ("gone", "zeroarea", "offscreen", "empty"),
     "树级开关的认领优先序固定（改这个顺序会改变 --keep 的语义）")
t.ok(set(pruning.OWNER_PRIORITY) <= set(SW), "认领优先序里的名字都必须是真开关")
for name, (scope, on, desc) in pruning.PRUNE_SWITCHES.items():
    t.ok(scope in ("树", "字段"), f"开关 {name} 要标清作用域")
    t.ok(isinstance(on, bool), f"开关 {name} 的默认值要显式给")
    t.ok(len(desc) > 10, f"开关 {name} 要有文字说明（--prune-list 要读它）")

t.eq(pruning.parse_switch_spec(None, list(SW)), [], "空参数 → []")
t.eq(pruning.parse_switch_spec("gone，empty", list(SW)), ["gone", "empty"],
     "全角逗号也要能拆")
t.eq(len(pruning.parse_switch_spec("all", list(SW))), len(SW), "all = 全部")
t.eq(len(pruning.parse_switch_spec("*", list(SW))), len(SW), "* = 全部")
t.eq(pruning.parse_switch_spec("gone,gone", list(SW)), ["gone"], "重复的开关名去重")
try:
    pruning.parse_switch_spec("nope", list(SW))
    t.ok(False, "未知开关名必须报错", "它没报错")
except ValueError:
    t.ok(True, "未知开关名必须报错（不猜、不静默忽略）")

slim = pruning.apply_prune(clean(OBJ), pruning.default_switches())
t.eq(slim["mode"], "slim", "精简 JSON 的 mode")
t.eq(count(slim["tree"]), EXP_TREE_NODES - 4,
     "默认精简：10 → 6（剪掉 gone/zeroarea/offscreen/empty 各 1）")
t.eq(slim["slim"]["nodes"], {"full": EXP_TREE_NODES, "slim": EXP_TREE_NODES - 4},
     "节点计数：前 / 后")
t.eq(slim["slim"]["pruned_nodes"],
     {"gone": 1, "zeroarea": 1, "offscreen": 1, "empty": 1,
      "derived": 0, "defaults": 0, "meta": 0, "instance": 0}, "各开关剪掉的节点数")
t.ok("--keep" in slim["slim"]["note"], "slim 里要提示怎么把信息加回来")
t.eq(slim["slim"]["switches"]["gone"], True, "switches 记的是「是否执行剪枝」")
t.eq(sorted(slim["slim"]["switch_meaning"]), sorted(SW), "每个开关都要有文字说明")
t.has(slim["slim"], "field_defaults", "defaults 开关开着时要给出默认值表")
t.ok("认领" in slim["slim"]["ownership"], "要写明「一个节点只由一个开关认领」")

# 字段级剪枝：剪掉的是**派生量与元数据/实例标识**，留下的全是读数
a_alpha = find(slim["tree"], resource_id="com.demo:id/alpha")
t.not_has(a_alpha, "geom_check", "meta 开关剪掉 geom_check")
t.not_has(a_alpha, "drawing_order", "instance 开关剪掉 drawing_order")
t.not_has(a_alpha, "enabled", "defaults 开关剪掉取默认值的布尔字段")
t.not_has(a_alpha["dumpsys"], "bounds_abs_unclipped", "derived 开关剪掉派生量")
t.not_has(a_alpha["dumpsys"], "pred_visible_rect", "derived 开关剪掉派生量")
t.not_has(a_alpha["dumpsys"], "match_reason", "meta 开关剪掉配对依据")
t.not_has(a_alpha["dumpsys"], "view_hash", "instance 开关剪掉实例标识")
t.has(a_alpha, "bounds_screen", "读数必须留着")
t.has(a_alpha["dumpsys"], "bounds_local", "读数必须留着")
t.has(a_alpha, "text", "文字必须留着（这是主源的独有信息）")
for k in ("coordinate_note", "align_rules", "align_stats", "tree_note"):
    t.not_has(slim, k, f"meta 开关剪掉顶层 {k}")
t.ok(count(slim["tree"]) < count(OBJ["tree"]), "精简确实比全量小")

# --keep：把某个开关关掉 = 把那类信息**整类**加回来
for name in ("gone", "zeroarea", "offscreen", "empty"):
    sw = pruning.default_switches()
    sw[name] = False
    got = pruning.apply_prune(clean(OBJ), sw)
    t.eq(count(got["tree"]), 7, f"--keep {name} → 节点数（只放回这一类）")
    t.eq(got["slim"]["pruned_nodes"][name], 0, f"--keep {name} 之后该开关不再剪任何节点")
    t.not_has(got, "align_stats", f"--keep {name} 不影响 meta 开关的状态")

# 回归锁：GONE 节点在真机上**同时是零面积**。若树级开关不按固定优先序认领，
# `--keep gone` 把 GONE 放过之后会被 zeroarea 顺手剪掉 —— 节点数一个不变，
# 开关表里写着「可保留」的选项实际不起作用。这里必须看到 7 而不是 6。
sw = pruning.default_switches()
sw["gone"] = False
got = pruning.apply_prune(clean(OBJ), sw)
t.eq(count(got["tree"]), 7, "--keep gone 必须真的把 GONE 节点留下（认领顺序回归）")
t.ok(find(got["tree"], resource_id="app:id/hidden") is not None,
     "--keep gone 之后 GONE 节点要在树里")
t.eq(got["slim"]["pruned_nodes"]["zeroarea"], 1, "GONE 节点归 gone 管，不被 zeroarea 兼职认领")
t.eq(pruning._is_zeroarea(find(clean(OBJ)["tree"], resource_id="app:id/hidden")), True,
     "前提校验：那条 GONE 节点确实也是零面积（否则这条回归测不出东西）")

# 全关 = 全量：一个开关都不剪，树必须与全量**逐字节**一致
sw_all = {k: False for k in SW}
got = pruning.apply_prune(clean(OBJ), sw_all)
t.eq(count(got["tree"]), EXP_TREE_NODES, "--keep all → 节点数与全量相同")
t.eq(json.dumps(got["tree"]), json.dumps(OBJ["tree"]),
     "--keep all 时精简树与全量树逐字节一致")
t.eq(got["slim"]["pruned_nodes"], {k: 0 for k in SW}, "--keep all 时没有节点被剪")
t.eq(got["slim"]["field_defaults"], None, "--keep defaults 时不给默认值表（字段没被省略）")
t.eq(got["slim"]["nodes"], {"full": EXP_TREE_NODES, "slim": EXP_TREE_NODES}, "节点计数")

# 对已经剪过的结果再剪一次：幂等，不崩、也不把剪掉的节点变回来
again = pruning.apply_prune(clean(slim), pruning.default_switches())
t.eq(count(again["tree"]), count(slim["tree"]), "再剪一次是幂等的")

# 剪枝是**原地改**，但绝不能改动调用方传进来的那份（否则 full 会被 slim 污染）
t.eq(count(OBJ["tree"]), EXP_TREE_NODES, "全量 JSON 未被剪枝污染（节点数）")
t.has(OBJ, "align_stats", "全量 JSON 未被剪枝污染（align_stats 还在）")
t.eq(OBJ["mode"], "full", "全量 JSON 的 mode 未被改成 slim")


# ================================================================== 6. 命令行

t.group("6. 命令行（离线路径）")

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = cli.main(["tree", "--prune-list"])
t.eq(rc, 0, "--prune-list 退出码")
listing = buf.getvalue()
for name in SW:
    t.ok(name in listing, f"--prune-list 要列出开关 {name}")
t.ok("认领" in listing, "--prune-list 要说明节点只由一个开关认领")

out1 = os.path.join(TD, "slim_cli.json")
rc, data = run_cli(["--from-json", FULL_PATH, "--mode", "slim", "--out", out1], out1)
t.eq(rc, 0, "--from-json + --mode slim 退出码")
t.eq(data["mode"], "slim", "输出是精简版")
t.eq(count(data["tree"]), EXP_TREE_NODES - 4, "离线重剪的节点数")
t.eq(data["slim"]["nodes"]["full"], EXP_TREE_NODES, "报告里的「剪前」节点数来自输入 JSON")
t.ok(data["slim"]["derived_from"].startswith("全量 JSON"),
     "要写明精简版是从全量 JSON 剪出来的（不是第二条采集路径）")

observe_path = os.path.join(TD, "observe_cli.json")
rc, observed = run_cli(["--from-json", FULL_PATH, "--mode", "observe",
                        "--out", observe_path], observe_path)
t.eq(rc, 0, "--from-json + --mode observe 退出码")
t.eq(observed["mode"], "observe", "CLI observe 输出模式")
t.eq(observed["focus"]["status"], "found", "CLI observe 焦点状态")
t.eq(observed["focus"], application_observation.collect_observation(full_json=OBJ)["focus"],
     "CLI 与核心观察 API 输出一致")

for keep, want in (("gone", 7), ("zeroarea", 7), ("offscreen", 7), ("empty", 7),
                   ("all", EXP_TREE_NODES)):
    o = os.path.join(TD, f"k_{keep}.json")
    rc, d = run_cli(["--from-json", FULL_PATH, "--mode", "slim",
                     "--keep", keep, "--out", o], o)
    t.eq(rc, 0, f"--keep {keep} 退出码")
    t.eq(count(d["tree"]), want, f"--keep {keep} 的节点数")

o = os.path.join(TD, "k_multi.json")
rc, d = run_cli(["--from-json", FULL_PATH, "--mode", "slim",
                 "--keep", "gone,empty", "--out", o], o)
t.eq(count(d["tree"]), 8, "--keep gone,empty：两个开关一起关 → 10-2")
t.eq(d["slim"]["switches"]["gone"], False, "被 --keep 关掉的开关在输出里记 False")

# 用法错误必须给明确退出码，不能静默产出一份看着正常的结果
X = os.path.join(TD, "x.json")
t.eq(run_cli(["--from-json", FULL_PATH, "--out", X], X)[0], 2,
     "--from-json 不带 --mode slim → 退出码 2")
t.eq(run_cli(["--from-json", FULL_PATH, "--keep", "gone", "--out", X], X)[0], 2,
     "--keep 在全量模式下 → 退出码 2")
t.eq(run_cli(["--from-json", FULL_PATH, "--mode", "slim", "--keep", "nope",
              "--out", X], X)[0], 2, "未知开关名 → 退出码 2")
bad_json = os.path.join(TD, "bad.json")
with open(bad_json, "w", encoding="utf-8") as f:
    f.write('{"hello": 1}')
t.eq(run_cli(["--from-json", bad_json, "--mode", "slim", "--out", X], X)[0], 2,
     "不是本工具输出的 JSON → 退出码 2（不装作能剪）")
t.eq(run_cli(["--from-json", os.path.join(TD, "nope.json"), "--mode", "slim",
              "--out", X], X)[0], 2, "文件不存在 → 退出码 2")

# 两次 dumpsys 的一致性比较：单调时钟字段必须排除，否则**恒定误报**
d1 = _dumpsys(clock="1 (1 ms ago)")
d2 = _dumpsys(clock="9999 (9999 ms ago)")
t.eq(capture.hierarchy_drift(d1, d1), (False, None), "同一份 dump 不比出漂移")
t.eq(capture.hierarchy_drift(d1, d2), (False, None),
     "只有单调时钟字段不同 → **不算**漂移（拿整份文本比会恒定误报）")
drift, why = capture.hierarchy_drift(d1, _dumpsys(alpha_bounds="10,0-470,200"))
t.eq(drift, True, "布局矩形变了 → 判定漂移")
t.ok(why and "行不同" in why, "漂移说明要指出第一处不同在哪一行")
t.eq(capture.hierarchy_drift(d1, d1 + "\n  多出来的一行{x}")[0], True, "行数不同 → 判漂移")
t.eq(capture.hierarchy_drift("", "")[0], False, "两边都没有层次行 → 不判漂移")


# ================================================================== 7. 辅助脚本

t.group("7. 按键与截图坐标核对")

t.eq(remote_input.normalize_keycode("DOWN"), "KEYCODE_DPAD_DOWN", "短名 → KEYCODE_*")
t.eq(remote_input.normalize_keycode("down"), "KEYCODE_DPAD_DOWN", "大小写不敏感")
t.eq(remote_input.normalize_keycode("  dpad_down  "), "KEYCODE_DPAD_DOWN", "两侧空格要去掉")
t.eq(remote_input.normalize_keycode("OK"), "KEYCODE_DPAD_CENTER", "别名映射")
t.eq(remote_input.normalize_keycode("CENTER"), "KEYCODE_DPAD_CENTER", "多个短名指向同一键码")
t.eq(remote_input.normalize_keycode("KEYCODE_MENU"), "KEYCODE_MENU", "已是全名就不重复加前缀")
t.eq(remote_input.normalize_keycode("20"), "20", "数字键码原样传递（不能加成 KEYCODE_20）")
# 真机踩过的坑：`input keyevent DOWN` 静默失败 —— 焦点不动但命令返回成功
t.ok(remote_input.normalize_keycode("DOWN") != "DOWN",
     "裸名必须加 KEYCODE_ 前缀（input keyevent 不认裸名，且会**静默**失败）")
for short, full in remote_input.KEY_ALIASES.items():
    t.eq(remote_input.normalize_keycode(short), "KEYCODE_" + full,
         f"短名 {short} 与它的键码 {full} 必须一致")
t.not_has(remote_input.KEY_ALIASES, "KEYCODE_DPAD_DOWN", "别名表里只放不带前缀的键码名")

# tv_shot：从树 JSON 取两种坐标 + 祖先链溢出告警
sn = screenshot.flatten([screenshot.Node(n) for n in OBJ["tree"]])
t.eq(len(sn), EXP_TREE_NODES, "tv_shot 能把整棵树铺平成节点")
g = [n for n in sn if n["resource_id"] == "com.demo:id/gamma"][0]
a = [n for n in sn if n["resource_id"] == "com.demo:id/alpha"][0]
t.eq(g.rect_a11y(), (0, 700, 1920, 1080), "a11y 读数")
t.eq(g.rect_dumpsys(), (0, 700, 1920, 1300), "配对上的 dumpsys 派生坐标")
t.eq(g.rect_local(), (0, 700, 1920, 1300),
     "布局读数：a11y 节点要从嵌套的 dumpsys 子字典取（否则溢出告警形同虚设）")
t.ok(g.chain_overflow() is not None, "祖先链溢出（Gamma 1300 超出父容器 1080）必须告警")
t.ok("溢出" in (g.chain_overflow() or ""), "告警要说清是溢出")
t.eq(a.chain_overflow(), None, "矩形在父容器内的节点不该告警")

boxes_focus, warns_focus = screenshot.collect(OBJ, "focus", "both")
t.eq(len(boxes_focus), 2, "焦点节点 × both = 2 个框（a11y 红实线 + dumpsys 蓝虚线）")
t.eq([b[5] for b in boxes_focus], ["reading", "derived"], "框要标明来源是读数还是派生")
t.eq(warns_focus, [], "焦点节点的祖先链没有溢出 → 不该告警")
boxes_all, warns_all = screenshot.collect(OBJ, "all", "both")
t.eq(len(boxes_all), 1 + 2 * (EXP_A11Y_NODES - 1) + EXP_INSERTED,
     "all × both：配对上、有布局矩形的 a11y 节点各 2 个框（读数+派生），"
     "根节点只有读数框，dumpsys 节点各 1 个派生框")
t.eq(len(warns_all), 2, "只有溢出链上的派生框才告警（Gamma 与 off）")
t.ok(any("Gamma" in w for w in warns_all), "告警要指名道姓（Gamma）")
t.eq(len(screenshot.collect(OBJ, "all", "a11y")[0]), EXP_A11Y_NODES,
     "--source a11y 只画有屏幕读数的节点")
t.eq(len(screenshot.collect(OBJ, "actionable", "a11y")[0]), 1,
     "actionable = 可点击/可聚焦/持焦点的节点（本夹具只有 beta）")
lines = screenshot.compare_focus(OBJ)
t.ok(any("差值" in x for x in lines), "焦点对照要算出两个来源的差")
t.ok(any("drift" in x for x in lines), "焦点对照要带上 geom_check 档位")
t.ok(any("中心和(2 倍)" in x for x in lines),
     "对照要给出可直接复核的读数（中心和），不能只给结论")
t.ok(any("中心严格重合" in x and "比例严格相等" in x for x in lines),
     "夹具里的 beta 中心严格重合、两轴比例严格相等 → 判成与等比缩放一致")

# 判定必须**不留容差**：只把宽度改 1 像素，比例就不再严格相等，
# 不能被「差不多算缩放」蒙过去（旧实现有 0.9~1.2 / ±0.02 这类经验区间，
# 1 像素的差异必然被判成「缩放一致」—— 那正是「靠经验」的入口）。
near = clean(OBJ)
fb1 = find(near["tree"], resource_id="com.demo:id/beta")
fb1["dumpsys"]["bounds_abs_unclipped"] = [480, 0, 961, 200]
ln_near = screenshot.compare_focus(near)
t.ok(any("不是等比缩放" in x for x in ln_near),
     "比例只差 1 像素也要判成「不等比」——判定是整数等式，不留经验容差")
t.ok(any("两轴比例不等" in x for x in ln_near), "不等比要指名是哪一条不成立")

# 两个来源不等时**不能一律说成缩放**：真机两面板页上差值是 1008 像素的横向偏移，
# 说成「1.05 倍缩放」是误报成因。这里锁住「不同心」那条分支。
shift = clean(OBJ)
fb = find(shift["tree"], resource_id="com.demo:id/beta")
fb["dumpsys"]["bounds_abs_unclipped"] = [1000, 0, 1480, 200]
ln2 = screenshot.compare_focus(shift)
t.ok(any("不是等比缩放" in x for x in ln2),
     "平移型偏差不能说成缩放（否则滚动偏移会被误报成缩放动效）")
t.ok(any("中心不重合" in x for x in ln2), "不成等比时要指出是中心不重合")
t.ok(any("滚动偏移" in x for x in ln2), "不成等比时要指向可查的原因（溢出告警）")
t.ok(any("不改" in x and "补偿" in x for x in ln2),
     "说明里要写死「不改读数、不补偿」——这是本脚本的立场")
t.eq(image.load_tree(FULL_PATH)["mode"], "full", "load_tree 能读回自己写出的 JSON")

try:
    from PIL import Image
    has_pil = True
except ImportError:
    has_pil = False
if has_pil:
    red = image.COLOR_READING      # 后面所有像素级断言都要用
    src = os.path.join(TD, "src.png")
    Image.new("RGB", (1920, 1080), (40, 40, 40)).save(src)
    with open(src, "rb") as f:
        png = f.read()
    ok1, sk1, notes1 = image.draw_boxes(png, boxes_focus, os.path.join(TD, "d1.png"), SCREEN)
    t.eq((ok1, sk1), (2, 0), "同尺寸下两个框都画出、无跳过")
    # 夹具里 beta 的 a11y 读数是 [468,-5][972,205]：焦点缩放把上边顶出了屏幕上沿。
    # 「读数本身越界」必须被报出来（而旧实现只是默默裁掉，画面上看不出任何异常）。
    t.eq(len(notes1), 1, "读数部分越界 → 恰好 1 条裁切提示（不静默）")
    t.ok("468,-5" in notes1[0], "裁切提示要保留原始读数（-5 是读数越界，不是画框的毛病）")
    t.ok("实际画 [468,0-972,205]" in notes1[0], "还要给出裁到边界后实际画的坐标")

    Image.new("RGB", (960, 540), (40, 40, 40)).save(os.path.join(TD, "small.png"))
    with open(os.path.join(TD, "small.png"), "rb") as f:
        png2 = f.read()
    ok2, sk2, notes2 = image.draw_boxes(png2, boxes_focus, os.path.join(TD, "d2.png"), SCREEN)
    t.eq(ok2, 2, "尺寸不一致时仍要画（按比例换算）")
    t.ok(any("换算后绘制" in n for n in notes2), "尺寸不一致必须提示，不能默默缩放")
    t.ok(any("x×0.500000" in n and "y×0.500000" in n for n in notes2),
         "换算系数要逐轴报出（而不是只按宽度算一个）")

    # 宽高比不一致 → 不是相似变换，必须点明「对应关系不成立」，不许按单轴凑
    ok5, sk5, notes5 = image.draw_boxes(png, boxes_focus, os.path.join(TD, "d5.png"),
                                          {"width": 1920, "height": 960})
    t.ok(any("两轴换算系数不相等" in n for n in notes5),
         "宽高比不一致（x×1.0 ≠ y×1.125）必须点明「不是相似变换」")
    t.ok(any("不成立" in n for n in notes5), "且要说清画出的框与读数的对应关系不成立")

    # 三种「画不出来/画不全」必须分得开，不许混成一句「落在画面外」：
    #   零面积（读数自身没有面积）≠ 真越界（读数超出画面）≠ 压屏幕外沿（栅格约定）
    ok4, sk4, notes4 = image.draw_boxes(png, [(1900, 1000, 2000, 1100, "越界半", "reading")],
                                          os.path.join(TD, "d4.png"), SCREEN)
    t.eq((ok4, sk4), (1, 0), "部分越界的框仍要画（裁到边界）")
    t.ok(any("越出画面" in n and "2000" in n for n in notes4),
         "被裁掉多少必须报出来（读数没变，只是画不出）")

    okZ, skZ, notesZ = image.draw_boxes(png, [(500, 300, 500, 400, "零宽", "reading")],
                                          os.path.join(TD, "dZ.png"), SCREEN)
    t.eq((okZ, skZ), (0, 1), "零面积的框画不出来")
    t.ok(any("零面积" in n for n in notesZ),
         "零面积要说「零面积」，不能说成「落在画面外」（性质不同）")
    t.ok(not any("画面外" in n for n in notesZ), "零面积不得被说成越界")

    # 读数边界刚好等于屏幕宽/高（a11y 的半开区间写法）→ 只给总数，不逐条刷屏，
    # 但必须说清「画出的框在那两条边上比读数少 1 像素」这个栅格事实。
    okE, skE, notesE = image.draw_boxes(
        png, [(0, 0, 1920, 1080, "全屏", "reading"), (10, 10, 1910, 1070, "内框", "reading")],
        os.path.join(TD, "dE.png"), SCREEN)
    t.eq((okE, skE), (2, 0), "压屏幕外沿的框照画")
    t.eq(len(notesE), 1, "压外沿只给一条汇总，不逐条刷屏")
    t.ok("另有 1 个框" in notesE[0] and "半开区间" in notesE[0],
         "汇总里要写清这是栅格约定、不是读数越界")

    # 全屏框的四条边：0 与 1919/1079（不是 1920/1080）
    imE = Image.open(os.path.join(TD, "dE.png")).convert("RGB")
    t.eq(imE.getpixel((0, 540)), red, "全屏框左边像素 = 0")
    t.eq(imE.getpixel((1919, 540)), red, "全屏框右边像素 = 1919（读数是 1920，半开区间）")
    t.eq(imE.getpixel((960, 1079)), red, "全屏框下边像素 = 1079（读数是 1080）")

    ok3, sk3, notes3 = image.draw_boxes(png, [(5000, 5000, 5100, 5100, "越界框", "reading")],
                                          os.path.join(TD, "d3.png"), SCREEN)
    t.eq((ok3, sk3), (0, 1), "画面外的框不绘制")
    t.ok(any("完全落在画面外" in n for n in notes3), "画面外的框要说明")

    # ---- 核心：画框 = 读数，逐像素对齐（不许向外膨胀） ----
    # 坐标换算系数为 1，于是「读数像素」与「画出的像素」必须一一对应：
    # 框上四边的像素必须是画的颜色，再往外一格必须是干净的底色。
    # 旧实现把红框循环向外膨胀 3 像素（cl-w..cr+w），也就把「读数与实际的
    # 偏差」整整 3 像素用线宽盖掉了 —— 这条断言就是钉死它的。
    blank = io.BytesIO()
    Image.new("RGB", (400, 300), (0, 0, 0)).save(blank, format="PNG")
    canvas = {"width": 400, "height": 300}
    red = image.COLOR_READING
    okX, skX, notesX = image.draw_boxes(
        blank.getvalue(), [(100, 120, 200, 180, "", "reading")],
        os.path.join(TD, "exact.png"), canvas)
    t.eq((okX, skX, notesX), (1, 0, []), "同尺寸下画框无提示、无跳过")
    im = Image.open(os.path.join(TD, "exact.png")).convert("RGB")
    t.eq(im.getpixel((100, 150)), red, "左边界所在像素 = 读数的左边界")
    t.eq(im.getpixel((200, 150)), red, "右边界所在像素 = 读数的右边界")
    t.eq(im.getpixel((150, 120)), red, "上边界所在像素 = 读数的上边界")
    t.eq(im.getpixel((150, 180)), red, "下边界所在像素 = 读数的下边界")
    for pt, why in (((99, 150), "左"), ((201, 150), "右"),
                    ((150, 119), "上"), ((150, 181), "下")):
        t.eq(im.getpixel(pt), (0, 0, 0),
             f"{why}边界往外一像素必须干净：框不许向外偏移/膨胀")
    t.eq(im.getpixel((101, 121)), (0, 0, 0), "框内部不填充（只有边线与中心十字）")

    # 带标签文字时，框线仍必须停在读数上：文字位置不得影响几何
    blank2 = io.BytesIO()
    Image.new("RGB", (400, 300), (0, 0, 0)).save(blank2, format="PNG")
    image.draw_boxes(blank2.getvalue(), [(100, 120, 200, 180, "标签", "reading")],
                       os.path.join(TD, "label.png"), canvas)
    imL = Image.open(os.path.join(TD, "label.png")).convert("RGB")
    t.eq([imL.getpixel(p) for p in ((100, 150), (200, 150), (150, 120), (150, 180))],
         [red] * 4, "有标签文字时框线几何不变（文字只为可读，不参与坐标）")

    # 加宽：线带以读数为中线**对称**展开，中线不得离开读数
    blank3 = io.BytesIO()
    Image.new("RGB", (400, 300), (0, 0, 0)).save(blank3, format="PNG")
    okW, skW, notesW = image.draw_boxes(
        blank3.getvalue(), [(100, 120, 200, 180, "", "reading")],
        os.path.join(TD, "w3.png"), canvas, width=3)
    im3 = Image.open(os.path.join(TD, "w3.png")).convert("RGB")
    t.eq((im3.getpixel((99, 150)), im3.getpixel((101, 150))), (red, red),
         "线宽 3：读数两侧各 1 像素（对称展开，中线仍是读数）")
    t.eq((im3.getpixel((98, 150)), im3.getpixel((102, 150))), ((0, 0, 0), (0, 0, 0)),
         "线宽 3：再往外就干净了（宽度是 3 而不是 5，说明没单边外扩）")
    t.ok(any("中线" in n for n in notesW), "加宽时要说清中线仍在读数上")
else:
    print("  （跳过画框测试：未安装 Pillow）")

# 职责边界：主脚本不截图、不按键；那两个动作各自只出现在自己的脚本里
tree_src = open(os.path.join(HERE, "tvuitree", "application", "observation.py"), "r", encoding="utf-8").read()
core_paths = [
    os.path.join(HERE, "tvuitree", "domain", "tree", name)
    for name in ("models.py", "parsing.py", "matching.py", "capture.py",
                 "output.py", "pruning.py")
]
core_src = "\n".join(open(path, "r", encoding="utf-8").read() for path in core_paths)
observe_src = open(os.path.join(HERE, "tvuitree", "domain", "observation.py"), "r", encoding="utf-8").read()
cli_src = open(os.path.join(HERE, "tvuitree", "interfaces", "observe.py"), "r", encoding="utf-8").read()
shot_src = open(os.path.join(HERE, "tvuitree", "infrastructure", "image.py"), "r", encoding="utf-8").read()
input_src = open(os.path.join(HERE, "tvuitree", "application", "input.py"), "r", encoding="utf-8").read()
t.ok("screencap" not in tree_src and "screencap" not in core_src,
     "树采集实现绝不截图（截图是 tv_shot.py 的事）")
t.ok("input keyevent" not in tree_src and "input keyevent" not in core_src,
     "树采集实现绝不发按键（按键是 tv_input.py 的事）")
t.ok("import tv_tree" not in observe_src and "from tv_tree" not in observe_src,
     "观察实现直接依赖内部包，不反向导入兼容入口")
t.ok("from tvuitree.application.observation import" in cli_src,
     "CLI 与 MCP 共享内部观察 API")
t.ok("screencap" in shot_src, "截图要在 infrastructure/image.py 里实现")
t.ok("input keyevent" in input_src, "发按键要在 application/input.py 里实现")
t.ok("fetch_u2" not in shot_src and "parse_dumpsys_top" not in shot_src,
     "tv_shot.py 不自己取树（它只读 JSON）")

# 画框的立场必须写在代码里，并挡住「靠经验修偏差」的两种典型写法复发
t.ok("逐像素对齐" in shot_src and "不加偏移" in shot_src,
     "几何约定要写在 infrastructure/image.py 里：框 = 读数，逐像素对齐、不加偏移")
t.ok("abs(sx - 1.0) > 0.01" not in shot_src,
     "不许再用「差不到 1% 就当没差」的换算阈值")
t.ok("0.9 <= kx" not in shot_src and "<= 1.2" not in shot_src,
     "不许再用「比例落在某区间就算缩放」的经验区间（会把滚动偏移误报成缩放）")
t.ok("cl - w" not in shot_src and "ct - w" not in shot_src,
     "不许再把框向外膨胀几像素（那会把要验证的差值盖掉）")
t.ok("build_full_json" not in input_src, "tv_input.py 与取树无关")

# README 是「首页说明书」：开关名与脚本名必须与代码同步
readme = os.path.join(HERE, "README.md")
if os.path.exists(readme):
    md = open(readme, "r", encoding="utf-8").read()
    for name in SW:
        t.ok(name in md, f"README 要写到剪枝开关 {name}（文档与代码同步）")
    for f in ("main.py", "tvuitree/", "domain/", "application/", "infrastructure/", "interfaces/", "tests/"):
        t.ok(f in md, f"README 要提到 {f}")
    for phrase in ("画框约定", "--width", "不加偏移", "逐像素", "不补偿"):
        t.ok(phrase in md,
             f"README 要写明画框约定中的「{phrase}」（框 = 读数，偏差要原样暴露）")
else:
    print("  （跳过 README 同步检查：文件不存在）")



# ================================================================== 8. CLI 与 MCP 共享采集

t.group("8. CLI 与 MCP 使用同一观察和完整树结果")

from types import SimpleNamespace
from tvuitree.infrastructure import snapshot as snapshot_adapter
from tvuitree.interfaces import mcp as mcp_interface

_original_snapshot = snapshot_adapter.snapshot
_original_observe_connect = observe_interface.connect_for_cli
_original_tree_connect = tree_interface.connect_for_cli
_original_visible_connect = visible_interface.connect_for_cli
_original_mcp_connect = mcp_interface._connect
_original_mcp_capture = mcp_interface.capture
_original_focus_dir = mcp_interface.FOCUS_SCREENSHOT_DIR
_original_save_focus = mcp_interface._save_focus_screenshot
_original_collect_observation = mcp_interface.collect_observation
_original_render_focus_png = mcp_interface.render_focus_png
_original_log_stream = timing.LOG_STREAM
_fake_device = SimpleNamespace(serial="fixture")


def _fixture_snapshot(adb, serial, save_raw, quiet, use_dumpsys=True, anomalies=None):
    blocks = parsing.parse_dumpsys_top(DUMPSYS, anomalies)
    return {
        "dev": {"model": "SELFTEST", "release": "14", "sdk": "34"},
        "screen": SCREEN, "win": WIN, "xml": A11Y,
        "u2_meta": {"version": "3.7.0", "info": {"displayWidth": 1920, "displayHeight": 1080}},
        "blocks": blocks, "block": blocks[0] if use_dumpsys else None,
        "pkg": PKG if use_dumpsys else None,
        "pick_note": None, "drift": False, "drift_detail": None,
    }


def _without_capture_time(value: dict) -> dict:
    result = clean(value)
    result.pop("captured_at", None)
    return result


def _timing_calls() -> list:
    """取出并清空本节的耗时日志，返回 (工具名, 阶段名列表, failed) 列表。"""
    lines = timing.LOG_STREAM.getvalue().splitlines()
    timing.LOG_STREAM.seek(0)
    timing.LOG_STREAM.truncate(0)
    calls = []
    for line in lines:
        parts = line.split(" ")
        fields = parts[4:]
        stages = [part.split("=", 1)[0] for part in fields if part.endswith("ms")]
        failed = next((part.split("=", 1)[1] for part in fields
                       if part.startswith("failed=")), None)
        calls.append((parts[2], stages, failed))
    return calls


try:
    timing.LOG_STREAM = io.StringIO()
    snapshot_adapter.snapshot = _fixture_snapshot
    observe_interface.connect_for_cli = lambda args: _fake_device
    tree_interface.connect_for_cli = lambda args: _fake_device
    visible_interface.connect_for_cli = lambda args: _fake_device
    mcp_interface._connect = lambda **kwargs: (_fake_device, "fixture")
    mcp_interface.FOCUS_SCREENSHOT_DIR = Path(TD) / "focus_screenshots"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        cli_observe_rc = cli.main(["observe", "--out", os.path.join(TD, "shared_observe.json")])
    with open(os.path.join(TD, "shared_observe.json"), encoding="utf-8") as source:
        cli_observation = json.load(source)
    mcp_observation = mcp_interface.observe_tv()
    t.eq(cli_observe_rc, 0, "CLI 实时观察退出码")
    t.eq(_without_capture_time(cli_observation), _without_capture_time(mcp_observation),
         "CLI 与 MCP 对同一快照返回相同观察 JSON")
    t.eq(_timing_calls(), [("observe_tv", ["connect", "capture_tree", "summarize"], None)],
         "observe_tv 每次调用写一行耗时，分连接、采集、摘要")

    mcp_focus = mcp_interface.get_current_focus()
    t.eq(mcp_focus["status"], cli_observation["focus"]["status"],
         "独立 MCP 焦点工具返回同一焦点状态")
    t.eq(mcp_focus["node"]["bounds"], cli_observation["focus"]["node"]["bounds"],
         "独立 MCP 焦点工具保留焦点节点坐标")
    t.eq(set(mcp_focus), {"status", "node"},
         "独立 MCP 焦点工具不返回上下文或重复候选")
    t.eq(mcp_focus["status"], "found", "独立焦点工具报告唯一焦点")
    t.eq(_timing_calls(),
         [("get_current_focus", ["connect", "capture_tree", "summarize"], None)],
         "get_current_focus 写一行耗时")
    mcp_schemas = {
        tool.name: tool.inputSchema for tool in asyncio.run(mcp_interface.mcp.list_tools())
    }
    for name in ("get_current_focus", "get_focus_screenshot"):
        t.eq(set(mcp_schemas[name]["properties"]), {"TV_IP_Address", "port", "adb"},
             f"{name} 只公开设备连接参数")
    t.eq(set(mcp_schemas["set_default_device"]["properties"]), {"TV_IP_Address", "port"},
         "set_default_device 只公开地址和端口")
    t.eq(mcp_schemas["set_default_device"].get("required"), ["TV_IP_Address"],
         "set_default_device 必须给出地址")
    t.eq(set(mcp_schemas["get_visible"]["properties"]),
         {"TV_IP_Address", "port", "adb", "no_connect"},
         "get_visible 只公开设备连接参数，不采集无关的 dumpsys")

    if has_pil:
        mcp_interface.capture = lambda device: png
        shot_content = asyncio.run(mcp_interface.mcp.call_tool("get_focus_screenshot", {}))
        t.eq([item.type for item in shot_content], ["text", "image"],
             "MCP 截图工具返回精简状态和原生 image 内容")
        t.eq(_timing_calls(), [("get_focus_screenshot",
                                ["connect", "capture_tree", "summarize", "screenshot",
                                 "mark", "encode", "save"], None)],
             "截图工具按连接、采集、摘要、截图、标注、编码、保存分段计时")
        shot_meta = json.loads(shot_content[0].text)
        expected_keys = {"focus_found", "screenshot_captured", "focus_marked",
                         "image_path", "image_base64"}
        t.eq(set(shot_meta), expected_keys, "截图状态不重复焦点节点或绘制细节")
        t.eq([shot_meta[key] for key in ("focus_found", "screenshot_captured", "focus_marked")],
             [True, True, True], "唯一焦点、截图和红框均成功")
        shot_path = Path(shot_meta["image_path"])
        t.ok(shot_path.is_absolute() and shot_path.is_file(), "标注截图保存到本地绝对路径")
        t.eq(shot_content[1].mimeType, "image/png", "MCP 图像格式是 PNG")
        import base64
        returned_png = base64.b64decode(shot_content[1].data)
        t.eq(shot_path.read_bytes(), returned_png, "本地文件与 MCP 图片是同一张标注图")
        t.eq(shot_meta["image_base64"], shot_content[1].data,
             "状态 JSON 的 Base64 与 MCP 图片内容一致")
        marked = Image.open(io.BytesIO(returned_png)).convert("RGB")
        t.eq(image.focus_border_width(png), 6, "1080p 焦点红框宽 6 像素")
        t.eq(image.focus_border_width(png2), 3, "540p 焦点红框按高度缩为 3 像素")
        t.eq([marked.getpixel((x, 100)) for x in range(466, 472)],
             [image.COLOR_READING] * 6, "焦点左边界有连续 6 像素红线")
        t.eq(marked.getpixel((465, 100)), (40, 40, 40), "加粗边框外侧保持原图")
        t.eq(marked.getpixel((500, 100)), (40, 40, 40),
             "MCP 截图只画边框，不画中心十字")

        next_shot = mcp_interface.get_focus_screenshot()
        t.ok(next_shot[0]["image_path"] != str(shot_path), "每次截图保存到独立文件")
        t.ok(Path(next_shot[0]["image_path"]).is_file(), "第二次截图文件存在")

        for focus_status in ("not_found", "ambiguous"):
            mcp_interface.collect_observation = (
                lambda **kwargs: {"focus": {"status": focus_status}}
            )
            unmarked = mcp_interface.get_focus_screenshot()
            t.eq(_timing_calls()[-1][1],
                 ["connect", "capture_tree", "summarize", "screenshot", "encode", "save"],
                 f"{focus_status} 时不标注，也不记 mark 阶段")
            t.eq([unmarked[0][key] for key in
                  ("focus_found", "screenshot_captured", "focus_marked")],
                 [False, True, False], f"{focus_status} 时截图仍成功但不标注")
            t.eq(Path(unmarked[0]["image_path"]).read_bytes(), png,
                 f"{focus_status} 时保存未标注的原始截图")
            t.eq(base64.b64decode(unmarked[0]["image_base64"]), png,
                 f"{focus_status} 时 Base64 返回未标注的原始截图")
        mcp_interface.collect_observation = _original_collect_observation

        def _capture_failure(device):
            raise ValueError("fixture screenshot failed")

        _timing_calls()
        mcp_interface.capture = _capture_failure
        capture_failure = mcp_interface.get_focus_screenshot()[0]
        t.eq([capture_failure[key] for key in
              ("focus_found", "screenshot_captured", "focus_marked", "image_path",
               "image_base64")],
             [True, False, False, None, None], "截图失败时状态字段仍齐全")
        t.ok("截图失败" in capture_failure["error"], "截图失败返回简短错误")
        t.eq(_timing_calls(), [("get_focus_screenshot",
                                ["connect", "capture_tree", "summarize", "screenshot"],
                                "screenshot")],
             "截图失败时日志停在 screenshot 并标出 failed")
        mcp_interface.capture = lambda device: png

        def _save_failure(data):
            raise OSError("fixture disk full")

        mcp_interface._save_focus_screenshot = _save_failure
        save_failure_content = asyncio.run(mcp_interface.mcp.call_tool(
            "get_focus_screenshot", {}))
        save_failure = json.loads(save_failure_content[0].text)
        t.eq([save_failure[key] for key in
              ("focus_found", "screenshot_captured", "focus_marked", "image_path")],
             [True, True, True, None], "保存失败不抹掉已取得的焦点和截图状态")
        t.eq(save_failure["image_base64"], save_failure_content[1].data,
             "保存失败仍在状态 JSON 中返回截图 Base64")
        t.ok("截图保存失败" in save_failure["error"], "保存失败返回简短错误")
        t.eq([item.type for item in save_failure_content], ["text", "image"],
             "保存失败仍返回 MCP 图片")
        mcp_interface._save_focus_screenshot = _original_save_focus

        mcp_interface.render_focus_png = (
            lambda obj, source: (source, {"boxes": ["focus"], "drawn": 0})
        )
        mark_failure = mcp_interface.get_focus_screenshot()[0]
        t.eq([mark_failure[key] for key in
              ("focus_found", "screenshot_captured", "focus_marked")],
             [True, True, False], "画框失败仍返回截图")
        t.ok(Path(mark_failure["image_path"]).is_file(), "画框失败仍保存原始截图")
        t.eq(base64.b64decode(mark_failure["image_base64"]), png,
             "画框失败时 Base64 返回原始截图")
        t.ok("焦点框未能画到截图上" in mark_failure["error"], "画框失败给出错误")
        mcp_interface.render_focus_png = _original_render_focus_png

        _timing_calls()
        mcp_interface._connect = lambda **kwargs: (None, "fixture")
        connection_failure = mcp_interface.get_focus_screenshot()[0]
        t.eq([connection_failure[key] for key in
              ("focus_found", "screenshot_captured", "focus_marked", "image_path",
               "image_base64")],
             [False, False, False, None, None], "连接失败时返回完整的失败状态")
        t.ok("error" in connection_failure, "连接失败给出错误")
        t.eq(_timing_calls(), [("get_focus_screenshot", ["connect"], None)],
             "连接失败提前返回时仍写一行耗时")
        mcp_interface._connect = lambda **kwargs: (_fake_device, "fixture")

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        cli_tree_rc = cli.main(["tree", "--out", os.path.join(TD, "shared_tree.json")])
    with open(os.path.join(TD, "shared_tree.json"), encoding="utf-8") as source:
        cli_tree = json.load(source)
    mcp_tree = mcp_interface.get_full_tree()
    t.eq(cli_tree_rc, 0, "CLI 完整树退出码")
    t.eq(_without_capture_time(cli_tree), _without_capture_time(mcp_tree),
         "CLI 与 MCP 对同一快照返回相同完整树 JSON")
    t.eq(_timing_calls(), [("get_full_tree", ["connect", "capture_tree"], None)],
         "get_full_tree 写一行耗时")

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        cli_visible_rc = cli.main(["visible", "--out", os.path.join(TD, "shared_visible.json")])
    with open(os.path.join(TD, "shared_visible.json"), encoding="utf-8") as source:
        cli_visible = json.load(source)
    mcp_visible = mcp_interface.get_visible()
    t.eq(cli_visible_rc, 0, "CLI 可视树退出码")
    t.eq(_without_capture_time(cli_visible), _without_capture_time(mcp_visible),
         "CLI 与 MCP 对同一快照返回相同可视树 JSON")
    t.eq(_timing_calls(),
         [("get_visible", ["connect", "capture_tree", "summarize"], None)],
         "get_visible 写一行耗时")
    t.eq(set(mcp_visible), {"schema_version", "mode", "captured_at", "screen",
                            "focus", "page"}, "可视结果保留观察所需的焦点和页面结构")
    t.eq(mcp_visible["schema_version"], "tv-visible/v1", "可视摘要使用独立版本")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        offline_visible_rc = cli.main([
            "visible", "--from-json", os.path.join(TD, "shared_tree.json"),
            "--out", os.path.join(TD, "offline_visible.json"),
        ])
    with open(os.path.join(TD, "offline_visible.json"), encoding="utf-8") as source:
        offline_visible = json.load(source)
    t.eq(offline_visible_rc, 0, "离线可视树退出码")
    t.eq(offline_visible, cli_visible, "离线与实时可视筛选使用同一逻辑")

    sample = {"mode": "full", "screen": {"width": 100, "height": 80}, "tree": [
        {"source": "a11y", "class": "root", "bounds_screen": None, "children": [
            {"source": "a11y", "class": "partial", "text": "inside",
             "bounds_screen": [-4, 4, 5, 15], "children": []},
            {"source": "a11y", "class": "duplicate", "text": "inside",
             "bounds_screen": [10, 10, 20, 20], "children": []},
            {"source": "a11y", "class": "outside", "text": "outside", "focused": True,
             "bounds_screen": [100, 4, 110, 15], "children": []},
            {"source": "a11y", "class": "zero", "text": "zero",
             "bounds_screen": [4, 4, 4, 15], "children": []},
            {"source": "a11y", "class": "missing", "text": "missing",
             "bounds_screen": None, "children": []},
            {"source": "a11y", "class": "unlabeled", "content_desc": "semantic-only",
             "bounds_screen": [4, 4, 10, 15], "children": []},
            {"source": "a11y", "class": "hidden", "text": "hidden",
             "visible_to_user": False,
             "bounds_screen": [4, 4, 10, 15], "children": [
                 {"source": "a11y", "class": "hidden-child", "text": "hidden-child",
                  "bounds_screen": [4, 4, 10, 15], "children": []},
             ]},
            {"source": "dumpsys", "class": "derived", "text": "derived", "visible": True,
             "bounds_local": [1, 1, 5, 5], "pred_visible_rect": [2, 2, 6, 6],
             "children": []},
            {"source": "dumpsys", "class": "gone", "text": "gone", "gone": True,
             "pred_visible_rect": [2, 2, 6, 6], "children": []},
        ]},
    ]}
    projected = domain_visible.select_visible(sample)
    t.eq([node["labels"] for node in projected["page"]["nodes"]],
         [["inside"], ["inside"]], "屏内文字保留两个实际位置，空容器和派生候选不输出")
    t.eq([node["bounds"] for node in projected["page"]["nodes"]],
         [[-4, 4, 5, 15], [10, 10, 20, 20]], "可视摘要保留 a11y 原始屏幕读数")
    t.eq(projected["focus"], {"status": "missing"}, "无可视焦点时不猜测焦点")
    t.eq(sample["tree"][0]["children"][0]["text"], "inside",
         "筛选不会修改输入的完整树")
    ellipsis_sample = {"screen": {"width": 100, "height": 80}, "tree": [
        {"source": "a11y", "text": "address ...", "bounds_screen": [1, 1, 20, 10],
         "children": []},
        {"source": "a11y", "text": "address\n192.168.1.1",
         "bounds_screen": [30, 1, 90, 25], "children": []},
    ]}
    t.eq([node["labels"] for node in
          domain_visible.select_visible(ellipsis_sample)["page"]["nodes"]],
         [["address\n192.168.1.1"]], "完整文字在屏幕上时不重复输出省略号摘要")
    row_sample = {"screen": {"width": 100, "height": 80}, "tree": [
        {"source": "a11y", "class": "Row", "bounds_screen": [0, 0, 80, 60],
         "clickable": True, "focusable": True, "focused": True, "children": [
             {"source": "a11y", "class": "TextView", "text": "IP address",
              "bounds_screen": [5, 5, 40, 20], "children": []},
             {"source": "a11y", "class": "TextView", "text": "192.168.1.1",
              "bounds_screen": [5, 25, 60, 40], "children": []},
         ]},
    ]}
    grouped = domain_visible.select_visible(row_sample)
    t.eq(grouped["focus"], {"status": "found", "path": "0"},
         "焦点引用页面项，不重复整份节点")
    t.eq([node["labels"] for node in grouped["page"]["nodes"]],
         [["IP address", "192.168.1.1"]], "同一可操作行的标题和值合并")
    t.eq(grouped["page"]["nodes"][0]["actions"], ["click", "focus"],
         "可见控件保留操作能力")
    icon_sample = {"screen": {"width": 100, "height": 80}, "tree": [
        {"source": "a11y", "class": "ImageButton", "content_desc": "Back",
         "bounds_screen": [5, 5, 30, 30], "clickable": True, "children": []},
    ]}
    icon_node = domain_visible.select_visible(icon_sample)["page"]["nodes"][0]
    t.eq(icon_node["accessibility_labels"], ["Back"],
         "可见图标的无障碍描述单独标记，不冒充屏幕文字")
    t.not_has(icon_node, "labels", "无显示文字的图标不生成文字标签")

    def _failed_snapshot(*args, **kwargs):
        raise adb.AdbError("fixture capture failed")

    _timing_calls()
    snapshot_adapter.snapshot = _failed_snapshot
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        failure_rc = cli.main(["observe"])
    t.eq(failure_rc, 3, "采集失败时 CLI 保留退出码 3")
    t.eq(mcp_interface.observe_tv()["focus"]["status"], "error",
         "采集失败时 MCP 返回结构化 error 状态")
    t.eq(mcp_interface.get_current_focus()["status"], "error",
         "独立焦点工具在采集失败时返回 error 状态")
    t.eq(mcp_interface.get_visible()["mode"], "visible",
         "可视工具采集失败时保留 visible 模式")
    failed_focus_shot = mcp_interface.get_focus_screenshot()[0]
    t.eq([failed_focus_shot[key] for key in
          ("focus_found", "screenshot_captured", "focus_marked")],
         [False, True, False], "焦点采集失败时仍返回未标注截图")
    t.ok("焦点采集失败" in failed_focus_shot["error"],
         "焦点采集失败时返回可读错误")
    t.eq(_timing_calls(), [
        ("observe_tv", ["connect", "capture_tree"], "capture_tree"),
        ("get_current_focus", ["connect", "capture_tree"], "capture_tree"),
        ("get_visible", ["connect", "capture_tree"], "capture_tree"),
        ("get_focus_screenshot", ["connect", "capture_tree", "screenshot", "encode", "save"],
         "capture_tree"),
    ], "采集失败被工具吞掉时日志仍标出 failed=capture_tree")
finally:
    snapshot_adapter.snapshot = _original_snapshot
    observe_interface.connect_for_cli = _original_observe_connect
    tree_interface.connect_for_cli = _original_tree_connect
    visible_interface.connect_for_cli = _original_visible_connect
    mcp_interface._connect = _original_mcp_connect
    mcp_interface.capture = _original_mcp_capture
    mcp_interface.FOCUS_SCREENSHOT_DIR = _original_focus_dir
    mcp_interface._save_focus_screenshot = _original_save_focus
    mcp_interface.collect_observation = _original_collect_observation
    mcp_interface.render_focus_png = _original_render_focus_png
    timing.LOG_STREAM = _original_log_stream

# ================================================================== 9. MCP 工具耗时日志

t.group("9. MCP 工具耗时日志")

_original_perf_counter = timing.perf_counter
_original_timing_stream = timing.LOG_STREAM
try:
    # 调用顺序：计时器创建、connect 起止、capture_tree 起止、总计结束
    _ticks = iter([10.0, 10.5, 11.0, 11.0, 11.25, 12.0])
    timing.perf_counter = lambda: next(_ticks)
    timing.LOG_STREAM = io.StringIO()
    with timing.tool_timing("demo_tool") as timer:
        with timer.stage("connect"):
            pass
        with timer.stage("capture_tree"):
            pass
    line = timing.LOG_STREAM.getvalue()
    t.ok(re.fullmatch(r"\[tv-uitree\] \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3} demo_tool "
                      r"total=2000\.0ms connect=500\.0ms capture_tree=250\.0ms\n", line),
         "耗时日志一行给出起始时间、工具名、总耗时和各阶段毫秒数", repr(line))

    _ticks = iter([0.0, 0.0, 0.1, 0.3])
    timing.LOG_STREAM = io.StringIO()
    escaped = False
    try:
        with timing.tool_timing("demo_tool") as timer:
            with timer.stage("screenshot"):
                raise ValueError("fixture")
    except ValueError:
        escaped = True
    line = timing.LOG_STREAM.getvalue()
    t.ok(escaped, "阶段异常不被计时器吞掉")
    t.ok(line.endswith(" demo_tool total=300.0ms screenshot=100.0ms failed=screenshot\n"),
         "异常穿出工具时仍写日志，并标出失败阶段", repr(line))

    class _BrokenStream:
        def write(self, text):
            raise OSError("fixture stderr closed")

        def flush(self):
            pass

    timing.perf_counter = _original_perf_counter
    timing.LOG_STREAM = _BrokenStream()
    try:
        with timing.tool_timing("demo_tool"):
            pass
        survived = True
    except Exception:
        survived = False
    t.ok(survived, "stderr 写入失败不影响工具结果")

    timing.LOG_STREAM = None
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        with timing.tool_timing("demo_tool"):
            pass
    t.eq(out.getvalue(), "", "耗时日志不写 stdout，stdio 协议不受干扰")
    t.ok(" demo_tool total=" in err.getvalue(), "耗时日志默认写 stderr", repr(err.getvalue()))
finally:
    timing.perf_counter = _original_perf_counter
    timing.LOG_STREAM = _original_timing_stream

# ================================================================== 10. 截图耗时压测脚本
t.group("10. 截图耗时压测脚本")

_bench_spec = importlib.util.spec_from_file_location(
    "bench_screencap", os.path.join(HERE, "scripts", "bench_screencap.py"))
bench = importlib.util.module_from_spec(_bench_spec)
sys.modules["bench_screencap"] = bench   # dataclass 需要按模块名找回命名空间
_bench_spec.loader.exec_module(bench)

_BENCH_PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 8   # 16 字节，能通过 image.capture 的 PNG 头校验


class _BenchDevice:
    """假设备：exec_out 依次吐出预置结果；异常（含 KeyboardInterrupt）就地抛出。"""

    def __init__(self, serial: str, outcomes=(), connected: bool = True,
                 state: str = "device", connect_error=None) -> None:
        self.serial = serial
        self._outcomes = iter(outcomes)
        self._connected = connected
        self._state = state
        self._connect_error = connect_error
        self.auto_connect = True

    def connect(self, quiet: bool = False) -> bool:
        if self._connect_error is not None:
            raise self._connect_error
        return self._connected

    def shell_raw(self, command: str, timeout: float = 30.0) -> tuple:
        if self._state == "device":
            return 0, "ok\n", ""
        return 1, "", f"error: device {self._state}\n"

    def exec_out(self, args: list, timeout: float = 60.0) -> bytes:
        item = next(self._outcomes)
        if isinstance(item, BaseException):
            raise item
        return item


def _bench_clock(*values: float):
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
    4, clock=_bench_clock(0.0, 0.25, 1.0, 2.0, 3.0, 3.5), out=_bench_out)
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
    2, clock=_bench_clock(0.0, 1.0), out=io.StringIO())
t.ok("没有成功的截图，无法统计耗时" in bench.format_report(_all_fail),
     "全部失败时报告不统计、不崩溃")

# Ctrl+C：停在当前轮，保留已完成的样本
_interrupted = bench.run_bench(
    _BenchDevice("192.0.2.10:5555", [_BENCH_PNG, KeyboardInterrupt()]),
    5, clock=_bench_clock(0.0, 0.5, 1.0), out=io.StringIO())
t.ok(_interrupted.interrupted, "Ctrl+C 标记为中断")
t.eq(_interrupted.durations_ms, [500.0], "中断前的样本保留")
_interrupted_report = bench.format_report(_interrupted)
t.ok("执行 1 次" in _interrupted_report and "已中断" in _interrupted_report,
     "中断报告只统计已执行轮次", _interrupted_report)

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

# 连接阶段按 Ctrl+C：已完成的设备照样写进报告，退出码 130
_ctrl_c_report = Path(TD) / "ctrl_c_connect.txt"
_code, _out, _, _created = _bench_main(
    ["192.0.2.10", "192.0.2.11", "-n", "1", "--report", str(_ctrl_c_report)],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", [_BENCH_PNG]),
     "192.0.2.11:5555": _BenchDevice("192.0.2.11:5555", connect_error=KeyboardInterrupt())})
_ctrl_c_text = _ctrl_c_report.read_text(encoding="utf-8") if _ctrl_c_report.is_file() else ""
t.eq(_code, 130, "连接阶段 Ctrl+C 退出码 130")
t.ok("== 192.0.2.10:5555 ==" in _ctrl_c_text and "已中断" in _ctrl_c_text,
     "连接阶段 Ctrl+C 仍写出已完成设备的报告并标明中断", _ctrl_c_text)

# 压测期间关掉自动重连：掉线要记成失败，不能把重连时间算进一次成功
_heal_device = _BenchDevice("192.0.2.10:5555", [_BENCH_PNG])
_bench_main(["192.0.2.10", "-n", "1"], {"192.0.2.10:5555": _heal_device})
t.ok(_heal_device.auto_connect is False, "压测循环里关闭 adb 自动重连")

# 在 adb devices 里但状态不是 device（unauthorized / offline）：当作连不上
_code, _out, _err, _ = _bench_main(
    ["192.0.2.10", "-n", "2"],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", state="unauthorized")})
t.eq(_code, 2, "unauthorized 设备按连接失败处理，退出码 2")
t.ok("无法连接 192.0.2.10:5555" in _err and "unauthorized" in _err,
     "unauthorized 在 stderr 说明原因", _err)
t.ok("[1/2]" not in _out, "不可用的设备不跑截图轮次", _out)

# adb 路径指向目录等 OSError：连接阶段报错不崩，截图阶段记成失败
_code, _, _err, _ = _bench_main(
    ["192.0.2.10", "-n", "1"],
    {"192.0.2.10:5555": _BenchDevice("192.0.2.10:5555", connect_error=PermissionError("denied"))})
t.eq(_code, 2, "连接阶段 OSError 退出码 2，不抛 traceback")
t.ok("denied" in _err, "连接阶段 OSError 在 stderr 说明", _err)
_os_result = bench.run_bench(
    _BenchDevice("192.0.2.10:5555", [OSError("resource busy"), _BENCH_PNG]),
    2, clock=_bench_clock(0.0, 1.0, 1.5), out=io.StringIO())
t.eq([index for index, _ in _os_result.failures], [1], "截图阶段 OSError 记成失败并继续")

# 控制台是 GBK 时，adb 报错里的替换字符 U+FFFD 不能让打印崩掉
_gbk_stdout = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
_saved_stdout = sys.stdout
sys.stdout = _gbk_stdout
try:
    try:
        _gbk_code = bench.main(
            ["192.0.2.10", "-n", "1", "--report", str(Path(TD) / "gbk.txt")],
            make_device=lambda target: _BenchDevice(target, [adb.AdbError("bad � byte")]))
    except UnicodeEncodeError as error:
        _gbk_code = repr(error)
finally:
    sys.stdout = _saved_stdout
t.eq(_gbk_code, 1, "GBK 控制台打印不可编码字符时不崩溃")

# ================================================================== 11. 默认设备配置写入

t.group("11. 默认设备配置写入与切换")

from tvuitree.infrastructure import device_config
from tvuitree.application import connection as app_connection

_original_config_path = device_config.CONFIG_PATH
_original_timing_stream_11 = timing.LOG_STREAM
_config_dir = Path(TD) / "device_config"
_config_dir.mkdir(exist_ok=True)


def _write_fixture_config(text: str) -> Path:
    path = _config_dir / "config.json"
    path.write_text(text, encoding="utf-8")
    device_config.CONFIG_PATH = path
    return path


def _replace_failure(src, dst):
    raise PermissionError("fixture locked")


_FIXTURE_CONFIG = ('{\n  "TV_IP_Address": "10.0.0.1",\n  "port": 5555,\n'
                   '  "adb": "X:\\\\adb.exe"\n}\n')
try:
    path = _write_fixture_config(_FIXTURE_CONFIG)
    device_config.save_device_config(
        {"TV_IP_Address": "10.0.0.2", "port": 5555, "adb": "X:\\adb.exe"})
    t.eq(path.read_text(encoding="utf-8"),
         '{\n  "TV_IP_Address": "10.0.0.2",\n  "port": 5555,\n'
         '  "adb": "X:\\\\adb.exe"\n}\n',
         "保存保持 2 空格缩进、字段顺序和末尾换行")
    t.eq(sorted(p.name for p in _config_dir.iterdir()), ["config.json"],
         "保存后不残留临时文件")

    path = _write_fixture_config(_FIXTURE_CONFIG)
    _original_replace = device_config.os.replace
    device_config.os.replace = _replace_failure
    try:
        device_config.save_device_config({"TV_IP_Address": "10.0.0.9", "port": 1})
        raised = False
    except ValueError:
        raised = True
    finally:
        device_config.os.replace = _original_replace
    t.ok(raised, "替换失败抛出 ValueError，说明写入失败")
    t.eq(path.read_text(encoding="utf-8"), _FIXTURE_CONFIG, "替换失败时原配置不变")
    t.eq(sorted(p.name for p in _config_dir.iterdir()), ["config.json"],
         "替换失败时删除临时文件")

    path = _write_fixture_config(_FIXTURE_CONFIG)
    result = app_connection.update_default_device(TV_IP_Address="10.0.0.2")
    t.eq(result["previous"], {"TV_IP_Address": "10.0.0.1", "port": 5555}, "返回切换前的目标")
    t.eq(result["current"], {"TV_IP_Address": "10.0.0.2", "port": 5555},
         "只传 IP 时端口保持原值")
    t.eq(result["config_path"], str(path), "返回被修改的配置文件路径")
    saved = json.loads(path.read_text(encoding="utf-8"))
    t.eq(saved, {"TV_IP_Address": "10.0.0.2", "port": 5555, "adb": "X:\\adb.exe"},
         "切换设备保留 adb 等其他字段")
    t.eq(app_connection.connection_options().target, "10.0.0.2:5555",
         "切换后下一次连接立即使用新目标，无需重启")

    result = app_connection.update_default_device(TV_IP_Address="10.0.0.3", port=5556)
    t.eq(result["current"], {"TV_IP_Address": "10.0.0.3", "port": 5556}, "可同时切换端口")

    for bad_kwargs in ({"TV_IP_Address": "10.0.0.4:5555"},
                       {"TV_IP_Address": " 10.0.0.4"},
                       {"TV_IP_Address": ""},
                       {"TV_IP_Address": "10.0.0.4", "port": True},
                       {"TV_IP_Address": "10.0.0.4", "port": 0},
                       {"TV_IP_Address": "10.0.0.4", "port": 70000}):
        before = path.read_bytes()
        try:
            app_connection.update_default_device(**bad_kwargs)
            rejected = False
        except ValueError:
            rejected = True
        t.ok(rejected, f"非法参数被拒绝：{bad_kwargs}")
        t.eq(path.read_bytes(), before, f"非法参数不改动配置文件：{bad_kwargs}")

    _write_fixture_config('{\n  "port": 5555\n}\n')
    result = app_connection.update_default_device(TV_IP_Address="10.0.0.5")
    t.eq(result["previous"], {"TV_IP_Address": None, "port": 5555},
         "原配置缺地址时 previous 如实给 None")

    timing.LOG_STREAM = io.StringIO()
    path = _write_fixture_config(_FIXTURE_CONFIG)
    mcp_result = mcp_interface.set_default_device(TV_IP_Address="10.0.0.7")
    t.eq(mcp_result["current"], {"TV_IP_Address": "10.0.0.7", "port": 5555},
         "MCP 工具切换默认设备")
    t.eq(_timing_calls(), [("set_default_device", ["save"], None)],
         "set_default_device 写一行耗时，只有 save 阶段")

    before = path.read_bytes()
    bad = mcp_interface.set_default_device(TV_IP_Address="10.0.0.8:5555")
    t.eq(set(bad), {"error", "error_type"}, "非法地址返回结构化错误")
    t.eq(bad["error_type"], "ValueError", "错误类型是 ValueError")
    t.eq(path.read_bytes(), before, "MCP 非法调用不改动配置")
    t.eq(_timing_calls(), [("set_default_device", ["save"], "save")],
         "失败时日志标出 failed=save")

    _original_replace = device_config.os.replace
    device_config.os.replace = _replace_failure
    try:
        locked = mcp_interface.set_default_device(TV_IP_Address="10.0.0.9")
    finally:
        device_config.os.replace = _original_replace
    t.ok("无法写入设备配置文件" in locked.get("error", ""), "写入失败返回可读错误")
    t.eq(path.read_bytes(), before, "写入失败时配置不变")
finally:
    device_config.CONFIG_PATH = _original_config_path
    timing.LOG_STREAM = _original_timing_stream_11

# ================================================================== 收尾

shutil.rmtree(TD, ignore_errors=True)
sys.exit(t.summary())
