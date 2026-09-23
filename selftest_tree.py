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
  python selftest_tree.py            # 全部通过 → 退出码 0；有失败 → 退出码 1
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tv_adb          # noqa: E402
import tv_input        # noqa: E402
import tv_shot         # noqa: E402
import tv_tree         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


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
    blocks = tv_tree.parse_dumpsys_top(DUMPSYS)
    u2_roots = tv_tree.parse_u2_xml(A11Y)
    view_roots = blocks[0].roots
    st = tv_tree.align(u2_roots, view_roots, PKG, SCR)
    obj = tv_tree.build_full_json(
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
        rc = tv_tree.main(argv)
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

t.group("0. 三个脚本共用同一套设备接入（tv_adb 是唯一出口）")

for mod, name in ((tv_tree, "tv_tree.py"), (tv_input, "tv_input.py"),
                  (tv_shot, "tv_shot.py")):
    help_text = mod.build_parser().format_help()
    for opt in ("--host", "--port", "--serial", "--address", "--adb", "--no-connect",
                "--no-color", "--quiet"):
        t.ok(opt in help_text, f"{name} 要有公共参数 {opt}（设备接入参数只能有一处定义）")
t.eq(tv_adb.resolve_adb("X:/adb.exe"), "X:/adb.exe", "显式指定的 adb 路径优先（不查文件系统）")
t.eq(tv_adb.normalize_component("com.demo/.MainActivity"),
     ("com.demo", "com.demo.MainActivity"), "`.Cls` 写法要补全包名")
t.eq(tv_adb.normalize_component("com.demo/.MainActivity"),
     tv_adb.normalize_component("com.demo/com.demo.MainActivity"),
     "同一个 component 的两种写法必须归一化成同一个值（否则段匹配会时不时失手）")
t.eq(tv_adb.normalize_component("没有斜杠"), None, "不合法输入返回 None（不猜）")
t.eq(tv_adb.normalize_component(None), None, "None 输入")
t.eq(tv_adb.component_from_activity_record(
    "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0"),
    "com.demo/.MainActivity", "从 ACTIVITY 行取 component")
t.eq(tv_adb.component_from_window(
    "  mFocusedWindow=Window{abc u0 com.demo/.MainActivity}"),
    "com.demo/.MainActivity", "从 window dump 取 component")
t.eq(tv_adb.resolve_serial(tv_input.build_parser().parse_args(["--host", "1.2.3.4",
                                                              "--port", "5555"])),
     "1.2.3.4:5555", "serial 默认由 host:port 拼出")
_CN = ("R", "B", "DIM", "RED", "GRN", "YEL", "BLU", "MAG", "CYA", "GRY")
_saved = {k: getattr(tv_adb.C, k) for k in _CN}
_saved_on = tv_adb.C._on
tv_adb.C.off()
t.eq(tv_adb.c("x", tv_adb.C.RED), "x", "关色后 c() 返回原文（重定向到文件时不带转义码）")
tv_adb.C._on = _saved_on
for _k, _v in _saved.items():
    setattr(tv_adb.C, _k, _v)


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
bad_blocks = tv_tree.parse_dumpsys_top(BAD)
anom = list(tv_tree.PARSE_ANOMALIES)
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
tv_tree.parse_dumpsys_top(BAD2)
t.ok(any("整数倍" in w for _, _, w in tv_tree.PARSE_ANOMALIES),
     "缩进不是 2 的倍数要记成解析告警（层级可能错位，不能默默吞掉）",
     f"实际告警 {tv_tree.PARSE_ANOMALIES}")
tv_tree.parse_dumpsys_top(DUMPSYS)
t.eq(tv_tree.PARSE_ANOMALIES, [], "正常 dump 不该产生任何解析告警")


# ================================================================== 2. 坐标与谓词

t.group("2. 坐标换算与谓词（读数 / 派生值分离）")

gamma_v = [n for n in blk.all_nodes if n.res_id == "app:id/gamma"][0]
t.eq(tv_tree.absolute_bounds(gamma_v), (0, 700, 1920, 1300),
     "absolute_bounds = 沿祖先链累加（**派生值**，dump 不含 scrollX/scrollY）")
t.eq(tv_tree.clip_to_chain(gamma_v, None), (0, 700, 1920, 1080),
     "clip_to_chain = 再与各祖先求交 → 裁剪后的可见矩形")
t.eq(tv_tree.pred_visible_rect(gamma_v, SCR), (0, 700, 1920, 1080),
     "pred_visible_rect = 再与屏幕求交")
t.eq(tv_tree.absolute_bounds(root), None, "根节点没 bounds → 派生值也给不出（不猜）")

t.eq(tv_tree.intersect((0, 0, 10, 10), (20, 20, 30, 30)), (20, 20, 20, 20),
     "无交集 → 退化成零面积矩形（判「屏幕外」就靠它）")
t.eq(tv_tree.intersect(None, (1, 2, 3, 4)), (1, 2, 3, 4), "None 视作无约束")

t.eq(tv_tree.norm_res_id("app:id/x", "com.demo"), "com.demo:id/x",
     "ViewDebug 的 app:id/ 要归一化成 <包名>:id/")
t.eq(tv_tree.norm_res_id("android:id/content", "com.demo"), "android:id/content",
     "android: 前缀原样保留")
t.eq(tv_tree.norm_res_id(None, "com.demo"), None, "None 仍是 None")
t.eq(tv_tree.norm_res_id("app:id/x", None), "app:id/x", "不知道包名就不动它（不猜）")

t.eq(tv_tree.is_framework_cls("android.widget.TextView"), True, "android.widget.* 是框架类")
t.eq(tv_tree.is_framework_cls("androidx.recyclerview.widget.RecyclerView"), False,
     "androidx.* **不**算框架类 —— a11y 不替换它，也就不能拿它当配对硬条件")
t.eq(tv_tree.is_framework_cls("com.demo.MyGrid"), False, "自定义类不是框架类")

u_all = tv_tree.u2_all(FX["u2_roots"])
u_beta = [n for n in u_all if n.res_id == "com.demo:id/beta"][0]
u_grid = [n for n in u_all if n.cls == "com.demo.MyGrid"][0]
u_rec = [n for n in u_all if n.res_id == "com.demo:id/grid"][0]
my_rec = [n for n in blk.all_nodes if n.res_id == "app:id/grid"][0]

t.eq(tv_tree.class_ok(beta, u_beta), (True, False), "框架类且同名 → 通过、无替换")
t.eq(tv_tree.class_ok(grid, u_grid), (True, False), "自定义类同名 → 通过、无替换")
t.eq(tv_tree.class_ok(my_rec, u_rec), (True, True),
     "自定义类名被 a11y 换成框架类名 → 通过、记一次「类名替换」")
t.eq(tv_tree.class_ok(tv_tree.Node(cls="android.widget.TextView"), u_rec)[0], False,
     "框架类名不等 → **拒绝**配对（框架类不会被 a11y 替换，不等就是配错了）")

t.eq(tv_tree.resid_ok(my_rec, u_rec, PKG), True, "res-id 归一化后相等")
t.eq(tv_tree.resid_ok(beta, u_rec, PKG), False, "res-id 不等")
t.eq(tv_tree.resid_ok(grid, u_grid, PKG), True, "两侧都是 None 也算相等（同为 None 不比）")


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
    kids_u = [tv_tree.U2Node(raw={}, cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                             res_id=r) for r in u_rids]
    kids_v = [tv_tree.Node(cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                           res_id=r) for r in v_rids]
    pu = tv_tree.U2Node(raw={}, cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                        children=kids_u)
    pv = tv_tree.Node(cls="android.widget.FrameLayout", bounds=(0, 0, 10, 10),
                      children=kids_v)
    return tv_tree.align([pu], [pv], PKG, None)


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

uni = tv_tree.build_unified(FX["u2_roots"], FX["view_roots"], ST, SCR)
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

# 同一份输入跑两次，结果必须一致
t.eq(json.dumps(clean(OBJ)["tree"]), json.dumps(OBJ["tree"]), "同输入 → 同输出（树部分）")

# --no-dumpsys：只剩主源，且必须**不假装**有 dumpsys 信息
nd_roots = tv_tree.parse_u2_xml(A11Y)                      # 全新解析：不带任何配对结果
nd_st = tv_tree.align(nd_roots, [], None, None)
t.eq(nd_st.paired, 0, "--no-dumpsys 时不做任何配对")
no_d = tv_tree.build_full_json(nd_roots, [], {"version": "x", "info": {}},
                               {}, SCREEN, WIN, nd_st, None, None, show_dumpsys=False)
t.eq(no_d["supplement_source"], None, "--no-dumpsys 时补充源标注为 None")
t.eq(count(no_d["tree"]), EXP_A11Y_NODES, "--no-dumpsys 时树只剩 a11y 节点")
t.eq(no_d["dumpsys_only"], [], "--no-dumpsys 时不输出 dumpsys 章节")
t.ok(all("dumpsys" not in n for n in flat(no_d["tree"])),
     "--no-dumpsys 时节点上没有 dumpsys 子字典")
t.eq(no_d["align_stats"]["view_nodes"], 0, "--no-dumpsys 时 view 节点数为 0")


# ================================================================== 5. 剪枝

t.group("5. 剪枝：开关语义与 --keep 增量")

SW = tv_tree.default_switches()
t.eq(sorted(SW), ["defaults", "derived", "empty", "gone", "instance", "meta",
                  "offscreen", "zeroarea"], "8 个开关")
t.ok(all(SW.values()), "默认状态下每个开关都执行剪枝")
t.eq(sorted(tv_tree.PRUNE_SWITCHES), sorted(SW), "开关表与默认值表必须同名同数")
t.eq(tv_tree.OWNER_PRIORITY, ("gone", "zeroarea", "offscreen", "empty"),
     "树级开关的认领优先序固定（改这个顺序会改变 --keep 的语义）")
t.ok(set(tv_tree.OWNER_PRIORITY) <= set(SW), "认领优先序里的名字都必须是真开关")
for name, (scope, on, desc) in tv_tree.PRUNE_SWITCHES.items():
    t.ok(scope in ("树", "字段"), f"开关 {name} 要标清作用域")
    t.ok(isinstance(on, bool), f"开关 {name} 的默认值要显式给")
    t.ok(len(desc) > 10, f"开关 {name} 要有文字说明（--prune-list 要读它）")

t.eq(tv_tree.parse_switch_spec(None, list(SW)), [], "空参数 → []")
t.eq(tv_tree.parse_switch_spec("gone，empty", list(SW)), ["gone", "empty"],
     "全角逗号也要能拆")
t.eq(len(tv_tree.parse_switch_spec("all", list(SW))), len(SW), "all = 全部")
t.eq(len(tv_tree.parse_switch_spec("*", list(SW))), len(SW), "* = 全部")
t.eq(tv_tree.parse_switch_spec("gone,gone", list(SW)), ["gone"], "重复的开关名去重")
try:
    tv_tree.parse_switch_spec("nope", list(SW))
    t.ok(False, "未知开关名必须报错", "它没报错")
except ValueError:
    t.ok(True, "未知开关名必须报错（不猜、不静默忽略）")

slim = tv_tree.apply_prune(clean(OBJ), tv_tree.default_switches())
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
    sw = tv_tree.default_switches()
    sw[name] = False
    got = tv_tree.apply_prune(clean(OBJ), sw)
    t.eq(count(got["tree"]), 7, f"--keep {name} → 节点数（只放回这一类）")
    t.eq(got["slim"]["pruned_nodes"][name], 0, f"--keep {name} 之后该开关不再剪任何节点")
    t.not_has(got, "align_stats", f"--keep {name} 不影响 meta 开关的状态")

# 回归锁：GONE 节点在真机上**同时是零面积**。若树级开关不按固定优先序认领，
# `--keep gone` 把 GONE 放过之后会被 zeroarea 顺手剪掉 —— 节点数一个不变，
# 开关表里写着「可保留」的选项实际不起作用。这里必须看到 7 而不是 6。
sw = tv_tree.default_switches()
sw["gone"] = False
got = tv_tree.apply_prune(clean(OBJ), sw)
t.eq(count(got["tree"]), 7, "--keep gone 必须真的把 GONE 节点留下（认领顺序回归）")
t.ok(find(got["tree"], resource_id="app:id/hidden") is not None,
     "--keep gone 之后 GONE 节点要在树里")
t.eq(got["slim"]["pruned_nodes"]["zeroarea"], 1, "GONE 节点归 gone 管，不被 zeroarea 兼职认领")
t.eq(tv_tree._is_zeroarea(find(clean(OBJ)["tree"], resource_id="app:id/hidden")), True,
     "前提校验：那条 GONE 节点确实也是零面积（否则这条回归测不出东西）")

# 全关 = 全量：一个开关都不剪，树必须与全量**逐字节**一致
sw_all = {k: False for k in SW}
got = tv_tree.apply_prune(clean(OBJ), sw_all)
t.eq(count(got["tree"]), EXP_TREE_NODES, "--keep all → 节点数与全量相同")
t.eq(json.dumps(got["tree"]), json.dumps(OBJ["tree"]),
     "--keep all 时精简树与全量树逐字节一致")
t.eq(got["slim"]["pruned_nodes"], {k: 0 for k in SW}, "--keep all 时没有节点被剪")
t.eq(got["slim"]["field_defaults"], None, "--keep defaults 时不给默认值表（字段没被省略）")
t.eq(got["slim"]["nodes"], {"full": EXP_TREE_NODES, "slim": EXP_TREE_NODES}, "节点计数")

# 对已经剪过的结果再剪一次：幂等，不崩、也不把剪掉的节点变回来
again = tv_tree.apply_prune(clean(slim), tv_tree.default_switches())
t.eq(count(again["tree"]), count(slim["tree"]), "再剪一次是幂等的")

# 剪枝是**原地改**，但绝不能改动调用方传进来的那份（否则 full 会被 slim 污染）
t.eq(count(OBJ["tree"]), EXP_TREE_NODES, "全量 JSON 未被剪枝污染（节点数）")
t.has(OBJ, "align_stats", "全量 JSON 未被剪枝污染（align_stats 还在）")
t.eq(OBJ["mode"], "full", "全量 JSON 的 mode 未被改成 slim")


# ================================================================== 6. 命令行

t.group("6. 命令行（离线路径）")

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = tv_tree.main(["--prune-list"])
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
t.eq(tv_tree.hierarchy_drift(d1, d1), (False, None), "同一份 dump 不比出漂移")
t.eq(tv_tree.hierarchy_drift(d1, d2), (False, None),
     "只有单调时钟字段不同 → **不算**漂移（拿整份文本比会恒定误报）")
drift, why = tv_tree.hierarchy_drift(d1, _dumpsys(alpha_bounds="10,0-470,200"))
t.eq(drift, True, "布局矩形变了 → 判定漂移")
t.ok(why and "行不同" in why, "漂移说明要指出第一处不同在哪一行")
t.eq(tv_tree.hierarchy_drift(d1, d1 + "\n  多出来的一行{x}")[0], True, "行数不同 → 判漂移")
t.eq(tv_tree.hierarchy_drift("", "")[0], False, "两边都没有层次行 → 不判漂移")


# ================================================================== 7. 辅助脚本

t.group("7. 辅助脚本（tv_input 键码 / tv_shot 画框）")

t.eq(tv_input.normalize_keycode("DOWN"), "KEYCODE_DPAD_DOWN", "短名 → KEYCODE_*")
t.eq(tv_input.normalize_keycode("down"), "KEYCODE_DPAD_DOWN", "大小写不敏感")
t.eq(tv_input.normalize_keycode("  dpad_down  "), "KEYCODE_DPAD_DOWN", "两侧空格要去掉")
t.eq(tv_input.normalize_keycode("OK"), "KEYCODE_DPAD_CENTER", "别名映射")
t.eq(tv_input.normalize_keycode("CENTER"), "KEYCODE_DPAD_CENTER", "多个短名指向同一键码")
t.eq(tv_input.normalize_keycode("KEYCODE_MENU"), "KEYCODE_MENU", "已是全名就不重复加前缀")
t.eq(tv_input.normalize_keycode("20"), "20", "数字键码原样传递（不能加成 KEYCODE_20）")
# 真机踩过的坑：`input keyevent DOWN` 静默失败 —— 焦点不动但命令返回成功
t.ok(tv_input.normalize_keycode("DOWN") != "DOWN",
     "裸名必须加 KEYCODE_ 前缀（input keyevent 不认裸名，且会**静默**失败）")
for short, full in tv_input.KEY_ALIASES.items():
    t.eq(tv_input.normalize_keycode(short), "KEYCODE_" + full,
         f"短名 {short} 与它的键码 {full} 必须一致")
t.not_has(tv_input.KEY_ALIASES, "KEYCODE_DPAD_DOWN", "别名表里只放不带前缀的键码名")

# tv_shot：从树 JSON 取两种坐标 + 祖先链溢出告警
sn = tv_shot.flatten([tv_shot.Node(n) for n in OBJ["tree"]])
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

boxes_focus, warns_focus = tv_shot.collect(OBJ, "focus", "both")
t.eq(len(boxes_focus), 2, "焦点节点 × both = 2 个框（a11y 红实线 + dumpsys 蓝虚线）")
t.eq([b[5] for b in boxes_focus], ["reading", "derived"], "框要标明来源是读数还是派生")
t.eq(warns_focus, [], "焦点节点的祖先链没有溢出 → 不该告警")
boxes_all, warns_all = tv_shot.collect(OBJ, "all", "both")
t.eq(len(boxes_all), 1 + 2 * (EXP_A11Y_NODES - 1) + EXP_INSERTED,
     "all × both：配对上、有布局矩形的 a11y 节点各 2 个框（读数+派生），"
     "根节点只有读数框，dumpsys 节点各 1 个派生框")
t.eq(len(warns_all), 2, "只有溢出链上的派生框才告警（Gamma 与 off）")
t.ok(any("Gamma" in w for w in warns_all), "告警要指名道姓（Gamma）")
t.eq(len(tv_shot.collect(OBJ, "all", "a11y")[0]), EXP_A11Y_NODES,
     "--source a11y 只画有屏幕读数的节点")
t.eq(len(tv_shot.collect(OBJ, "actionable", "a11y")[0]), 1,
     "actionable = 可点击/可聚焦/持焦点的节点（本夹具只有 beta）")
lines = tv_shot.compare_focus(OBJ)
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
ln_near = tv_shot.compare_focus(near)
t.ok(any("不是等比缩放" in x for x in ln_near),
     "比例只差 1 像素也要判成「不等比」——判定是整数等式，不留经验容差")
t.ok(any("两轴比例不等" in x for x in ln_near), "不等比要指名是哪一条不成立")

# 两个来源不等时**不能一律说成缩放**：真机两面板页上差值是 1008 像素的横向偏移，
# 说成「1.05 倍缩放」是误报成因。这里锁住「不同心」那条分支。
shift = clean(OBJ)
fb = find(shift["tree"], resource_id="com.demo:id/beta")
fb["dumpsys"]["bounds_abs_unclipped"] = [1000, 0, 1480, 200]
ln2 = tv_shot.compare_focus(shift)
t.ok(any("不是等比缩放" in x for x in ln2),
     "平移型偏差不能说成缩放（否则滚动偏移会被误报成缩放动效）")
t.ok(any("中心不重合" in x for x in ln2), "不成等比时要指出是中心不重合")
t.ok(any("滚动偏移" in x for x in ln2), "不成等比时要指向可查的原因（溢出告警）")
t.ok(any("不改" in x and "补偿" in x for x in ln2),
     "说明里要写死「不改读数、不补偿」——这是本脚本的立场")
t.eq(tv_shot.load_tree(FULL_PATH)["mode"], "full", "load_tree 能读回自己写出的 JSON")

try:
    from PIL import Image
    has_pil = True
except ImportError:
    has_pil = False
if has_pil:
    red = tv_shot.COLOR_READING      # 后面所有像素级断言都要用
    src = os.path.join(TD, "src.png")
    Image.new("RGB", (1920, 1080), (40, 40, 40)).save(src)
    with open(src, "rb") as f:
        png = f.read()
    ok1, sk1, notes1 = tv_shot.draw_boxes(png, boxes_focus, os.path.join(TD, "d1.png"), SCREEN)
    t.eq((ok1, sk1), (2, 0), "同尺寸下两个框都画出、无跳过")
    # 夹具里 beta 的 a11y 读数是 [468,-5][972,205]：焦点缩放把上边顶出了屏幕上沿。
    # 「读数本身越界」必须被报出来（而旧实现只是默默裁掉，画面上看不出任何异常）。
    t.eq(len(notes1), 1, "读数部分越界 → 恰好 1 条裁切提示（不静默）")
    t.ok("468,-5" in notes1[0], "裁切提示要保留原始读数（-5 是读数越界，不是画框的毛病）")
    t.ok("实际画 [468,0-972,205]" in notes1[0], "还要给出裁到边界后实际画的坐标")

    Image.new("RGB", (960, 540), (40, 40, 40)).save(os.path.join(TD, "small.png"))
    with open(os.path.join(TD, "small.png"), "rb") as f:
        png2 = f.read()
    ok2, sk2, notes2 = tv_shot.draw_boxes(png2, boxes_focus, os.path.join(TD, "d2.png"), SCREEN)
    t.eq(ok2, 2, "尺寸不一致时仍要画（按比例换算）")
    t.ok(any("换算后绘制" in n for n in notes2), "尺寸不一致必须提示，不能默默缩放")
    t.ok(any("x×0.500000" in n and "y×0.500000" in n for n in notes2),
         "换算系数要逐轴报出（而不是只按宽度算一个）")

    # 宽高比不一致 → 不是相似变换，必须点明「对应关系不成立」，不许按单轴凑
    ok5, sk5, notes5 = tv_shot.draw_boxes(png, boxes_focus, os.path.join(TD, "d5.png"),
                                          {"width": 1920, "height": 960})
    t.ok(any("两轴换算系数不相等" in n for n in notes5),
         "宽高比不一致（x×1.0 ≠ y×1.125）必须点明「不是相似变换」")
    t.ok(any("不成立" in n for n in notes5), "且要说清画出的框与读数的对应关系不成立")

    # 三种「画不出来/画不全」必须分得开，不许混成一句「落在画面外」：
    #   零面积（读数自身没有面积）≠ 真越界（读数超出画面）≠ 压屏幕外沿（栅格约定）
    ok4, sk4, notes4 = tv_shot.draw_boxes(png, [(1900, 1000, 2000, 1100, "越界半", "reading")],
                                          os.path.join(TD, "d4.png"), SCREEN)
    t.eq((ok4, sk4), (1, 0), "部分越界的框仍要画（裁到边界）")
    t.ok(any("越出画面" in n and "2000" in n for n in notes4),
         "被裁掉多少必须报出来（读数没变，只是画不出）")

    okZ, skZ, notesZ = tv_shot.draw_boxes(png, [(500, 300, 500, 400, "零宽", "reading")],
                                          os.path.join(TD, "dZ.png"), SCREEN)
    t.eq((okZ, skZ), (0, 1), "零面积的框画不出来")
    t.ok(any("零面积" in n for n in notesZ),
         "零面积要说「零面积」，不能说成「落在画面外」（性质不同）")
    t.ok(not any("画面外" in n for n in notesZ), "零面积不得被说成越界")

    # 读数边界刚好等于屏幕宽/高（a11y 的半开区间写法）→ 只给总数，不逐条刷屏，
    # 但必须说清「画出的框在那两条边上比读数少 1 像素」这个栅格事实。
    okE, skE, notesE = tv_shot.draw_boxes(
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

    ok3, sk3, notes3 = tv_shot.draw_boxes(png, [(5000, 5000, 5100, 5100, "越界框", "reading")],
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
    red = tv_shot.COLOR_READING
    okX, skX, notesX = tv_shot.draw_boxes(
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
    tv_shot.draw_boxes(blank2.getvalue(), [(100, 120, 200, 180, "标签", "reading")],
                       os.path.join(TD, "label.png"), canvas)
    imL = Image.open(os.path.join(TD, "label.png")).convert("RGB")
    t.eq([imL.getpixel(p) for p in ((100, 150), (200, 150), (150, 120), (150, 180))],
         [red] * 4, "有标签文字时框线几何不变（文字只为可读，不参与坐标）")

    # 加宽：线带以读数为中线**对称**展开，中线不得离开读数
    blank3 = io.BytesIO()
    Image.new("RGB", (400, 300), (0, 0, 0)).save(blank3, format="PNG")
    okW, skW, notesW = tv_shot.draw_boxes(
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
tree_src = open(os.path.join(HERE, "tv_tree.py"), "r", encoding="utf-8").read()
shot_src = open(os.path.join(HERE, "tv_shot.py"), "r", encoding="utf-8").read()
input_src = open(os.path.join(HERE, "tv_input.py"), "r", encoding="utf-8").read()
t.ok("screencap" not in tree_src, "tv_tree.py 绝不截图（截图是 tv_shot.py 的事）")
t.ok("input keyevent" not in tree_src, "tv_tree.py 绝不发按键（按键是 tv_input.py 的事）")
t.ok("screencap" in shot_src, "截图要真的在 tv_shot.py 里实现")
t.ok("input keyevent" in input_src, "发按键要真的在 tv_input.py 里实现")
t.ok("fetch_u2" not in shot_src and "parse_dumpsys_top" not in shot_src,
     "tv_shot.py 不自己取树（它只读 JSON）")

# 画框的立场必须写在代码里，并挡住「靠经验修偏差」的两种典型写法复发
t.ok("逐像素对齐" in shot_src and "不加偏移" in shot_src,
     "几何约定要写在 tv_shot.py 里：框 = 读数，逐像素对齐、不加偏移")
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
    for f in ("tv_tree.py", "tv_input.py", "tv_shot.py", "selftest_tree.py"):
        t.ok(f in md, f"README 要提到 {f}")
    for phrase in ("画框约定", "--width", "不加偏移", "逐像素", "不补偿"):
        t.ok(phrase in md,
             f"README 要写明画框约定中的「{phrase}」（框 = 读数，偏差要原样暴露）")
else:
    print("  （跳过 README 同步检查：文件不存在）")


# ================================================================== 收尾

shutil.rmtree(TD, ignore_errors=True)
sys.exit(t.summary())
