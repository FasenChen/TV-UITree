#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tv_tree.py — Android TV 控件树采集与结构化输出

一句话
------
把屏幕上那一屏控件抓成一棵**可复核的 JSON 树**：类名、矩形、层级、文字、状态、
焦点，全部原样来自数据源读数；并支持在这棵全量树上按开关剪枝，输出精简版。

本脚本只做一件事：**取树 → 出 JSON**。
它不做按键、不做截图、不画框 —— 那些在 tv_input.py / tv_shot.py 里，与本脚本无关。

三种输出形态
------------
  --mode full   全量 JSON（默认）。所有读数 100% 保留，不做任何删减。
  --mode slim   精简 JSON。在上面的全量 JSON 上按开关剪枝，扣掉无用信息。
                **剪枝的对象是已经生成好的全量 JSON**，不是另一条采集路径，
                所以两个模式表达的是同一棵树、同一批读数。
  --keep LIST   精简版的增量选项：把指定剪枝开关**关掉**，把那部分信息加回来。
                例：--mode slim --keep empty  → 精简 JSON 但保留空节点。

两个数据源，各有各的短板（全部为实测结论，不是推断）
----------------------------------------------------
  主源  uiautomator2（a11y / 无障碍树）
        → 有文字（text / content-desc / hint）
        → bounds 是**屏幕上真实可见的矩形**（已按祖先与屏幕裁剪），是读数
        → 实测属性 21 个
        短板：
        → **不含** GONE / 不可见视图（ViewStub 等）的节点
        → **不含** 完全在屏幕外的节点
        → **不含** 未裁剪的布局矩形（屏外内容量不出来）
        → **不含** 实例标识（View 对象 hash / accessibility view id）
        → 类名对**自定义类**会被替换成框架类
          （`VerticalGridView→GridView`、`TwoPanelScrollView→HorizontalScrollView`）

  补充源 dumpsys activity top 的 View Hierarchy
        → 有完整 View 树（含 GONE、含屏外节点）
        → 有相对父容器的**布局矩形**（未裁剪）
        → 有实例标识：`vhash`（对象 hash）、`aid`（accessibility view id）、`id_hex`
        → 有 a11y 不输出的标志位：`drawn`、`contextClickable`、滚动条启用位
        短板：**没有文字**（ViewDebug 不调 getText()）

合并规则（**全部显式、可验证；一条不成立就不合并**）
--------------------------------------------------
本工具绝不「按坐标接近程度猜节点对应关系」。配对只用下面四条规则，逐条可复核：

  R0 根配对   两侧各恰好 1 个根节点 → 视为同一窗口根。
  R1 几何锚定  对 view 节点计算**预测可见矩形**
              pred(v) = abs(v) ∩ abs(各祖先) ∩ 屏幕
              若某 a11y 节点 u 满足：恰有**一个** view 节点 v 使
                  pred(v) == u.bounds（矩形完全相等）
                  且 res-id 谓词成立 且 class 谓词成立
              则配对。三个条件缺一不可；候选不唯一 → 不配对。
  R2 焦点锚定  两侧各恰好 1 个 focused 节点，且 class 谓词成立 → 配对。
              （焦点项在 TV 上会做 1.05 倍缩放动效，矩形必然不等，
               所以它**不能**走 R1。用「两侧唯一焦点」这条独立依据。）
  R3 序列插入  父节点已配对时，把 a11y 子序列 U 保序、全注入地映到 view 子序列 V：
              ok(i,j) = class 谓词 ∧ res-id 谓词 ∧ 不违反已确定的配对
              数解个数：**恰好 1 个解才采用**；0 个或 >1 个 → 放弃并记为「歧义」。
              采用后，V 中未被映射的子节点（GONE / 屏外）按 V 的顺序**插入**到
              a11y 树的对应位置上——位置由 view 树的顺序唯一确定，不是猜的。

  谓词定义
    res-id 谓词：view 侧 `app:id/X` 归一化为 `<段包名>:id/X`（ViewDebug 对 0x7f
                包固定写 `app`），再要求两侧字符串相等（同为 None 也算相等）。
    class 谓词 ：view 类名属框架类（android.widget./android.view./android.webkit./
                android.app./android.opengl./android.graphics. 前缀）时，要求
                a11y 类名与之**完全相等**；否则（自定义类，会被 a11y 替换）
                不做相等要求，但该节点会被标记。

  配不上的 dumpsys 节点 → JSON 里的 `dumpsys_only` 章节，**不塞进 a11y 树**、
  也不做位置推测。

坐标系（两个量分得很清楚，不许混用）
------------------------------------
  a11y 的 `bounds_screen`      = **读数**。屏幕上真实可见的矩形。
  dumpsys 的 `bounds_local`    = **读数**。相对父容器的布局矩形（未裁剪）。
  `bounds_abs_unclipped`       = **派生值**。沿祖先链累加得出，前提是祖先链上
                                 没有滚动偏移；而 dump 不含 scrollX/scrollY、
                                 无法验证该前提，所以它**不是**屏幕位置。
  `geom_check`                 = 对每个已配对节点，用上面两者做的独立几何校验：
                                 exact（相等）/ clip（有屏外内容被裁）/ drift（对不上）

设计原则（做了就等于用不严谨的方式掩盖缺陷）
--------------------------------------------
  1. **不猜节点对应关系**。只用 R0–R3，每条都能手工复核；规则给了多解就判为
     **歧义**并放弃该处合并，不硬挑一个。
  2. **读数与派生值分家**。派生量一律显式标注，不冒充读数。
  3. **补不进去 ≠ 丢掉**。合并失败的 dumpsys 节点进 `dumpsys_only` 章节。
  4. **拿不到就报错**。u2 装不上 / 连不上 → 报错退出，**不静默退回**单一数据源
     —— 否则同一条命令会时对时错。
  5. **解析只依赖格式，不依赖内容**。字段按「位置 + 字段宽度 + 字符类」取，不用
     值白名单（白名单会遇到集合外的合法取值，然后静默丢掉整行数据）。
     读不出来的行汇总成「解析告警」打到 stderr。
  6. **不做跨源字段搬运**。不会按坐标把 a11y 的文字「贴」到 view 树的字段上。

依赖
----
  标准库 + `pip install uiautomator2`（主源，**装不上就报错退出**）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

from tv_adb import (Adb, AdbError, C, add_conn_args, c, connect_device,
                    normalize_component, setup_console)

# ------------------------------------------------------------------ 常量

# a11y XML 的属性全集（uiautomator2 v3 实测 21 个）
A11Y_ATTRS = (
    "bounds", "checkable", "checked", "class", "clickable", "content-desc",
    "display-id", "drawing-order", "enabled", "focusable", "focused", "hint",
    "index", "long-clickable", "package", "password", "resource-id",
    "scrollable", "selected", "text", "visible-to-user",
)

# view 侧类名属这些前缀时视为「框架类」——a11y 不做替换，类名必须相等
FRAMEWORK_CLS_PREFIXES = (
    "android.widget.", "android.view.", "android.webkit.",
    "android.app.", "android.opengl.", "android.graphics.",
)

BOUNDS_RE = re.compile(r"^(-?\d+),(-?\d+)-(-?\d+),(-?\d+)$")
A11Y_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
RES_RE = re.compile(r"^[A-Za-z][\w.]*:id/[\w.]+$")

NODE_RE = re.compile(
    r"^(?P<indent>[ ]*)"
    r"(?P<cls>[A-Za-z_$][\w.$]*)"
    r"(?:@(?P<ohash>[0-9a-fA-F]+))?"
    r"(?:\[(?P<oname>[^\]]*)\])?"
    r"(?:\{(?P<vhash>[0-9a-fA-F]+)(?P<rest>[^}]*)\})?"
    r"\s*$"
)
# ViewDebug 每个 View 行的字段顺序与宽度是 dumper 固定的：
#     Class{hash flags1(9) flags2(8) bounds [#hex] ... [aid=N | pkg:id/name]}
# 实测 151/151 行：flags1 恒 9 位、flags2 恒 8 位，字符集均为 [.A-Za-z]。
FLAGS_RE = {width: re.compile(r"[.A-Za-z]{%d}" % width) for width in (8, 9)}
# 缩进单位：dumper 每层 2 空格。实测缩进集合 {8,10,...,36} 全为偶数、最小正差恒为 2。
DUMP_INDENT_UNIT = 2

ACT_RE = re.compile(
    r"^(?P<indent>[ ]*)ACTIVITY\s+(?P<comp>\S+)\s+(?P<ohash>[0-9a-fA-F]+)\s+pid=(?P<pid>\d+)")
VH_RE = re.compile(r"^[ ]*View Hierarchy:\s*$")

# 配对依据（同时是 align_stats.by_reason 的键）
MATCH_ROOT = "root"
MATCH_GEOM = "geom"
MATCH_FOCUS = "focus"
MATCH_SEQ = "seq"

# 解析异常记录：形如 (行号, 原文, 原因)。有内容就说明「有数据没读出来」。
PARSE_ANOMALIES: list = []


def _anomaly(lineno: int, text: str, why: str) -> None:
    if len(PARSE_ANOMALIES) < 50:
        PARSE_ANOMALIES.append((lineno, text.strip()[:160], why))


# ------------------------------------------------------------------ 数据模型


@dataclass
class Node:
    """dumpsys View 树节点。字段全部来自 dump 原文。"""

    cls: str
    ohash: Optional[str] = None      # {}-外部的 @hash（如 DecorView@a1b994）
    oname: Optional[str] = None      # [] 内的名字（如 DecorView[MainSettings]）
    vhash: Optional[str] = None      # {} 内的 hash
    flags1: Optional[str] = None
    flags2: Optional[str] = None
    bounds: Optional[tuple] = None   # 相对父容器的 (l, t, r, b)
    id_hex: Optional[str] = None
    res_id: Optional[str] = None     # 例：app:id/list
    aid: Optional[str] = None        # 无障碍 view id
    children: list = field(default_factory=list)
    parent: Optional["Node"] = None
    lineno: int = 0
    # 注意：这里**没有** text / desc 字段。
    # `dumpsys activity top` 的 View 树不携带文字（ViewDebug 不调 getText()），
    # 本工具也不做跨源回填（原因见文件头设计原则第 6 条）。

    # ---- 派生属性（全部来自 flag 位，不做猜测） ----
    @property
    def visible(self) -> bool:
        return bool(self.flags1) and self.flags1[0] == "V"

    @property
    def gone(self) -> bool:
        return bool(self.flags1) and self.flags1[0] == "G"

    @property
    def focusable(self) -> bool:
        return bool(self.flags1) and self.flags1[1] == "F"

    @property
    def enabled(self) -> bool:
        return bool(self.flags1) and self.flags1[2] == "E"

    @property
    def clickable(self) -> bool:
        return bool(self.flags1) and self.flags1[6] == "C"

    @property
    def long_clickable(self) -> bool:
        return bool(self.flags1) and self.flags1[7] == "L"

    @property
    def scrollbar_h(self) -> bool:
        """flags1[4]=='H'：横向滚动条被启用。

        ⚠ 这**不等于**该 View 可滚动。实测本机多张快照里这一位恒为 '.'，而
        `TwoPanelScrollView` 明明可以滚动——说明该位只表示「滚动条是否启用」。
        """
        return bool(self.flags1) and self.flags1[4] == "H"

    @property
    def scrollbar_v(self) -> bool:
        """flags1[5]=='V'：纵向滚动条被启用（同 scrollbar_h，不等于可滚动）"""
        return bool(self.flags1) and self.flags1[5] == "V"

    @property
    def focused(self) -> bool:
        """flags2 第 2 位 == 'F' → 该 View 持有焦点（实测结论）"""
        return bool(self.flags2) and len(self.flags2) >= 2 and self.flags2[1] == "F"

    @property
    def bounds_str(self) -> Optional[str]:
        if not self.bounds:
            return None
        l, t, r, b = self.bounds
        return f"{l},{t}-{r},{b}"

    @property
    def short_cls(self) -> str:
        return self.cls.rsplit(".", 1)[-1] if "." in self.cls else self.cls

    @property
    def label(self) -> str:
        s = self.short_cls
        if self.res_id:
            s += f"#{self.res_id}"
        return s


@dataclass
class Block:
    """一个 ACTIVITY 段 + 其 View Hierarchy。"""

    component: str
    pid: str
    roots: list = field(default_factory=list)
    all_nodes: list = field(default_factory=list)


@dataclass(eq=False)
class U2Node:
    """无障碍节点。**每个字段都直接来自 XML 属性，无任何推算。**"""

    raw: dict
    cls: str = "(unknown)"
    text: Optional[str] = None
    desc: Optional[str] = None
    hint: Optional[str] = None
    res_id: Optional[str] = None
    package: Optional[str] = None
    bounds: Optional[tuple] = None
    checkable: bool = False
    checked: bool = False
    clickable: bool = False
    enabled: bool = True
    focusable: bool = False
    focused: bool = False
    long_clickable: bool = False
    password: bool = False
    scrollable: bool = False
    selected: bool = False
    visible_to_user: bool = True
    index: Optional[str] = None
    drawing_order: Optional[str] = None
    display_id: Optional[str] = None
    children: list = field(default_factory=list)
    parent: Optional["U2Node"] = None

    # 配对结果（由 align() 填）
    view: Optional[Node] = None
    match_reason: Optional[str] = None

    @property
    def short_cls(self) -> str:
        return self.cls.rsplit(".", 1)[-1] if "." in self.cls else self.cls

    @property
    def bounds_str(self) -> Optional[str]:
        if not self.bounds:
            return None
        l, t, r, b = self.bounds
        return f"{l},{t}-{r},{b}"


@dataclass
class UniNode:
    """一体式树节点。

    kind = "a11y"    → 来自主源（v 可能非 None，表示已配对上 dumpsys 节点）
    kind = "dumpsys" → a11y 未收录，由 R3 按 view 子序列顺序补入
    """

    kind: str
    u: Optional[U2Node] = None
    v: Optional[Node] = None
    children: list = field(default_factory=list)
    geom: Optional[str] = None      # exact / clip / drift / na
    note: Optional[str] = None


@dataclass
class AlignStats:
    a11y_nodes: int = 0
    view_nodes: int = 0
    paired: int = 0
    by_reason: dict = field(default_factory=dict)
    geom_exact: int = 0
    geom_clip: int = 0
    geom_drift: int = 0
    geom_na: int = 0
    class_substituted: int = 0
    a11y_unpaired: list = field(default_factory=list)
    view_unpaired: list = field(default_factory=list)     # 位置也无法确定
    seq_refused: list = field(default_factory=list)        # [(v_node, u_node, 原因)]
    # 子序列对齐解唯一 ⇒ 这些 dumpsys 独有节点的兄弟位次已由 view 顺序唯一确定
    insert_pos: dict = field(default_factory=dict)         # id(view_node) -> a11y 父
    unexplained: list = field(default_factory=list)        # 可见却未被 a11y 收录
    window_note: Optional[str] = None
    align_skipped: Optional[str] = None


# ------------------------------------------------------------------ 解析 dumpsys 视图树


def parse_node_line(text: str, lineno: int, indent: int) -> Optional[Node]:
    m = NODE_RE.match(text)
    if not m:
        return None
    n = Node(cls=m.group("cls"), ohash=m.group("ohash"), oname=m.group("oname"),
             vhash=m.group("vhash"), lineno=lineno)
    rest = (m.group("rest") or "").strip()
    if rest:
        toks = rest.split()
        i = 0
        # 按「位置 + 字段宽度 + 字符类」解析（格式规则），不做值白名单：
        # 白名单一旦遇到集合外的合法字母（例如 flags2 以 'R'/'W' 开头），
        # 该字段会被判为非 flags，后面的 bounds 也一起对不上 —— 静默丢数据。
        if i < len(toks) and FLAGS_RE[9].fullmatch(toks[i]):
            n.flags1 = toks[i]; i += 1
        if i < len(toks) and FLAGS_RE[8].fullmatch(toks[i]):
            n.flags2 = toks[i]; i += 1
        if i < len(toks):
            bm = BOUNDS_RE.match(toks[i])
            if bm:
                n.bounds = tuple(int(g) for g in bm.groups())
                i += 1
        while i < len(toks):
            t = toks[i]
            if t.startswith("#"):
                n.id_hex = t[1:]
            elif t.startswith("aid="):
                n.aid = t[4:]
            elif RES_RE.match(t):
                n.res_id = t
            i += 1
        if n.bounds is None:
            _anomaly(lineno, text, f"该行有字段但没解析出 bounds：{rest!r}")
    elif m.group("vhash"):
        _anomaly(lineno, text, "有 {hash} 但后面没有任何字段")
    return n


def build_tree(items: list, base_indent: int) -> tuple:
    """按缩进构建树。

    缩进单位用 dumper 的**固定格式值 2**，不做推断。（取「缩进值集合里的最小正差」
    是推断：一旦某次 dump 恰好只有一层子节点，回退值可能与实际单位不符，整棵树错位。）
    """
    unit = DUMP_INDENT_UNIT
    roots: list = []
    stack: list = []          # [(depth, node)]
    for ind, node in items:
        depth = (ind - base_indent) // unit
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            parent = stack[-1][1]
            node.parent = parent
            parent.children.append(node)
        else:
            roots.append(node)
        stack.append((depth, node))
    return roots, [n for _, n in items]


def parse_dumpsys_top(raw: str) -> list:
    """解析 `dumpsys activity top` 输出 → [Block]"""
    PARSE_ANOMALIES.clear()
    lines = raw.splitlines()
    blocks: list = []
    pending: Optional[dict] = None
    i = 0
    while i < len(lines):
        line = lines[i]
        am = ACT_RE.match(line)
        if am:
            pending = {"comp": am.group("comp"), "pid": am.group("pid")}
            i += 1
            continue
        if VH_RE.match(line) and pending is not None:
            i += 1
            collected = []
            base_indent = None
            while i < len(lines):
                cur = lines[i]
                if not cur.strip():
                    i += 1
                    continue
                ind = len(cur) - len(cur.lstrip(" "))
                if ind % DUMP_INDENT_UNIT:
                    _anomaly(i + 1, cur,
                             f"缩进 {ind} 不是 {DUMP_INDENT_UNIT} 的整数倍，树层级可能错位")
                node = parse_node_line(cur.lstrip(" ").rstrip(), i + 1, ind)
                if node is None or ind < 4:
                    break
                if base_indent is None:
                    base_indent = ind
                collected.append((ind, node))
                i += 1
            if collected:
                blk = Block(component=pending["comp"], pid=pending["pid"])
                blk.roots, blk.all_nodes = build_tree(collected, base_indent or 6)
                blocks.append(blk)
            pending = None
            continue
        i += 1
    return blocks


def pick_block_ex(blocks: list, component: Optional[str]) -> tuple:
    """挑出与前台窗口对应的 ACTIVITY 段，返回 (block, note)；note 为 None 表示精确匹配。

    背景（实测）：`dumpsys activity top` 只输出**承载 Activity 的窗口**的 View 树。
    display 0 上实测有 5 个窗口，只有 2 个有 View Hierarchy。所以当前台焦点落在
    对话框 / 输入法 / 壁纸等**独立窗口**上时，dump 里根本没有它的树 —— 此时若不说明，
    输出看着正常，其实是另一个页面的树、另一个 View 的坐标。
    """
    want = normalize_component(component)
    if want:
        for blk in blocks:
            if normalize_component(blk.component) == want:
                return blk, None
    if not blocks:
        return None, "dump 里没有任何 ACTIVITY 段"
    names = ", ".join(b.component.split("/")[-1] for b in blocks)
    if want:
        note = (f"前台窗口「{component}」不在 dump 的 ACTIVITY 段里——它可能是对话框/"
                f"输入法/壁纸等独立窗口，`dumpsys activity top` 不输出这类窗口的 View 树。"
                f"下面用的是回退段，不一定是当前画面。可用段: {names}")
    else:
        note = (f"没能从 `dumpsys window` 解析出前台 component，已回退到最后一个段，"
                f"不保证对应当前画面。可用段: {names}")
    return blocks[-1], note


def iter_nodes(roots: Iterable[Node]) -> Iterable[Node]:
    stack = list(roots)
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


# ------------------------------------------------------------------ 坐标换算


def absolute_bounds(node: Node) -> Optional[tuple]:
    """沿祖先链累加 left/top。**派生值**，不是读数（dump 不含 scrollX/scrollY）。"""
    if not node.bounds:
        return None
    x = y = 0
    cur: Optional[Node] = node
    while cur is not None and cur.bounds:
        x += cur.bounds[0]
        y += cur.bounds[1]
        cur = cur.parent
    l, t, r, b = node.bounds
    return (x, y, x + (r - l), y + (b - t))


def intersect(a: Optional[tuple], b: Optional[tuple]) -> Optional[tuple]:
    if a is None:
        return b
    if b is None:
        return a
    l = max(a[0], b[0]); t = max(a[1], b[1])
    r = min(a[2], b[2]); bo = min(a[3], b[3])
    if r < l or bo < t:
        return (l, t, l, t)
    return (l, t, r, bo)


def _clip_ancestors(node: Node) -> Optional[tuple]:
    own = absolute_bounds(node)
    if own is None:
        return None
    r = own
    cur = node.parent
    while cur is not None:
        ab = absolute_bounds(cur)
        if ab is not None:
            r = intersect(r, ab)
        cur = cur.parent
    return r


def clip_to_chain(node: Node, screen: Optional[tuple]) -> Optional[tuple]:
    return _clip_ancestors(node)


def pred_visible_rect(node: Node, screen: Optional[tuple]) -> Optional[tuple]:
    """view 节点的**预测可见矩形**：自身累加矩形 ∩ 各祖先累加矩形 ∩ 屏幕。

    纯几何计算，不含阈值、不含推测。它成立与否由 R1 与实际 a11y bounds 比对直接验证。
    """
    r = _clip_ancestors(node)
    if screen:
        r = intersect(r, screen)
    return r


# ------------------------------------------------------------------ 谓词


def norm_res_id(rid: Optional[str], pkg: Optional[str]) -> Optional[str]:
    """把 view 侧资源 id 归一化到 a11y 的写法。

    ViewDebug 对包 id 为 0x7f（应用自身资源）的 id 固定写成 `app:id/name`，
    而 a11y 写的是 `<包名>:id/name`。实测某 TV 设置页 view 侧 res-id 前缀
    只有 `android:`(59) 与 `app:`(36) 两种。其余前缀原样保留。
    """
    if not rid:
        return None
    if ":id/" not in rid:
        return rid
    pre, name = rid.split(":id/", 1)
    if pre == "app" and pkg:
        return f"{pkg}:id/{name}"
    return rid


def is_framework_cls(cls: str) -> bool:
    return cls.startswith(FRAMEWORK_CLS_PREFIXES)


def class_ok(v: Node, u: U2Node) -> tuple:
    """返回 (是否通过, 是否发生了类名替换)。"""
    if is_framework_cls(v.cls):
        return v.cls == u.cls, False
    return True, (v.cls != u.cls)


def resid_ok(v: Node, u: U2Node, pkg: Optional[str]) -> bool:
    return norm_res_id(v.res_id, pkg) == (u.res_id or None)


# ------------------------------------------------------------------ 配对 R0–R3


def u2_all(roots: list) -> list:
    out, stack = [], list(roots)
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(reversed(n.children))
    return out


def find_u2_focus(roots: list) -> list:
    return [n for n in u2_all(roots) if n.focused]


def _align_children(u: U2Node, v: Node, pkg: Optional[str],
                    paired_u: dict, paired_v: dict, st: AlignStats) -> None:
    """R3：把 u 的子序列保序全注入到 v 的子序列。**只接受唯一解。**"""
    U = list(u.children)
    V = list(v.children)
    if not U or not V or len(U) > len(V):
        return

    def ok(i: int, j: int) -> bool:
        uc, vc = U[i], V[j]
        if id(uc) in paired_u and paired_u[id(uc)] is not vc:
            return False
        if id(vc) in paired_v and paired_v[id(vc)] is not uc:
            return False
        if not resid_ok(vc, uc, pkg):
            return False
        if not class_ok(vc, uc)[0]:
            return False
        return True

    m, n = len(U), len(V)
    CAP = 2  # 只需要知道 0 / 1 / >1
    ways = [[0] * (n + 1) for _ in range(m + 1)]
    for j in range(n + 1):
        ways[0][j] = 1
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            s = ways[i][j - 1]
            if ok(i - 1, j - 1):
                s += ways[i - 1][j - 1]
            ways[i][j] = CAP if s >= CAP else s
    if ways[m][n] != 1:
        if U and V:
            st.seq_refused.append((v, u, "无解" if ways[m][n] == 0 else "多解（歧义）"))
        return

    i, j = m, n
    mapping = {}
    while i > 0:
        if ok(i - 1, j - 1) and ways[i - 1][j - 1] == 1:
            mapping[i - 1] = j - 1
            i -= 1
            j -= 1
        else:
            j -= 1
    for i, j in mapping.items():
        uc, vc = U[i], V[j]
        if id(uc) not in paired_u and id(vc) not in paired_v:
            uc.view = vc
            uc.match_reason = MATCH_SEQ
            paired_u[id(uc)] = vc
            paired_v[id(vc)] = uc
    # 注意：这里**不**记录 insert_pos。dumpsys 独有节点能否并入主树、位次是否确定，
    # 统一由 merge_children() 判定，避免两处判据漂移。


def align(u2_roots: list, view_roots: list, pkg: Optional[str],
          screen: Optional[tuple], max_rounds: int = 6) -> AlignStats:
    """按 R0/R1/R2/R3 配对两棵树。**只做规则允许的配对，宁缺毋滥。**"""
    st = AlignStats()
    u_nodes = u2_all(u2_roots)
    v_nodes = list(iter_nodes(view_roots))
    st.a11y_nodes = len(u_nodes)
    st.view_nodes = len(v_nodes)

    pred = {id(v): pred_visible_rect(v, screen) for v in v_nodes}
    pred_noscreen = {id(v): clip_to_chain(v, None) for v in v_nodes}

    paired_u, paired_v = {}, {}

    def bind(v: Node, u: U2Node, reason: str):
        u.view = v
        u.match_reason = reason
        paired_u[id(u)] = v
        paired_v[id(v)] = u

    # ---- R0 根配对
    if len(u2_roots) == 1 and len(view_roots) == 1:
        bind(view_roots[0], u2_roots[0], MATCH_ROOT)

    # ---- R1 几何锚定（双向唯一）
    by_rect = {}
    for v in v_nodes:
        r = pred[id(v)]
        if r is not None:
            by_rect.setdefault(r, []).append(v)
    for u in u_nodes:
        if id(u) in paired_u or u.bounds is None:
            continue
        cands = [v for v in by_rect.get(u.bounds, [])
                 if id(v) not in paired_v and resid_ok(v, u, pkg) and class_ok(v, u)[0]]
        if len(cands) == 1:
            bind(cands[0], u, MATCH_GEOM)

    # ---- R2 焦点锚定
    uf = [u for u in u_nodes if u.focused]
    vf = [v for v in v_nodes if v.focused]
    if (len(uf) == 1 and len(vf) == 1 and id(uf[0]) not in paired_u
            and id(vf[0]) not in paired_v and class_ok(vf[0], uf[0])[0]):
        bind(vf[0], uf[0], MATCH_FOCUS)

    # ---- R3 序列插入（迭代到不动点）
    for _ in range(max_rounds):
        before = len(paired_u)
        for u in u_nodes:
            v = paired_u.get(id(u))
            if v is not None:
                _align_children(u, v, pkg, paired_u, paired_v, st)
        if len(paired_u) == before:
            break

    # ---- 统计
    for u in u_nodes:
        v = paired_u.get(id(u))
        if v is None:
            st.a11y_unpaired.append(u)
            continue
        st.paired += 1
        st.by_reason[u.match_reason] = st.by_reason.get(u.match_reason, 0) + 1
        if class_ok(v, u)[1]:
            st.class_substituted += 1
        # 几何三档：判据是「未裁剪的累加布局矩形」与「a11y 屏幕读数」的关系
        av = absolute_bounds(v)
        p = pred[id(v)]
        pc = pred_noscreen[id(v)]
        if av is None or u.bounds is None:
            st.geom_na += 1
        elif av == u.bounds:
            st.geom_exact += 1
        elif pc == u.bounds or p == u.bounds:
            st.geom_clip += 1
        else:
            st.geom_drift += 1

    # 哪些 dumpsys 独有节点会被并入主树？判据只有一个：merge_children()。
    # 再做一次闭包：已并入节点的整棵子树内部顺序完全由 view 树决定，无歧义。
    for u in u_nodes:
        v = paired_u.get(id(u))
        if v is None:
            continue
        order = merge_children(u, v)
        if order is None:
            continue
        for tag, obj in order:
            if tag == "d":
                st.insert_pos.setdefault(id(obj), u)
    stack = [v for v in v_nodes if id(v) in st.insert_pos]
    while stack:
        cur = stack.pop()
        for ch in cur.children:
            if id(ch) in paired_v or id(ch) in st.insert_pos:
                continue
            st.insert_pos[id(ch)] = st.insert_pos[id(cur)]
            stack.append(ch)

    for v in v_nodes:
        if id(v) in paired_v:
            continue
        if id(v) in st.insert_pos:
            # 已并入主树；但若它其实「可见且有面积」，说明 a11y 没收录一个本应可见的
            # 节点——这不是正常剪枝，必须点出来，而不是混在正常项里。
            vis = pred_visible_rect(v, screen)
            if (not v.gone) and vis is not None and vis[2] > vis[0] and vis[3] > vis[1]:
                st.unexplained.append(v)
            continue
        st.view_unpaired.append(v)
    return st


# ------------------------------------------------------------------ a11y 解析与采集


def parse_u2_xml(xml_text: str) -> list:
    """uiautomator2 的 XML → [U2Node] 树。逐属性解析，不做换算、不做默认值猜测。"""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    def b(el, k) -> bool:
        return el.get(k) == "true"

    def conv(el) -> U2Node:
        m = A11Y_BOUNDS_RE.match(el.get("bounds") or "")
        n = U2Node(
            raw=dict(el.attrib),
            cls=el.get("class") or "(unknown)",
            text=el.get("text") or None,
            desc=el.get("content-desc") or None,
            hint=el.get("hint") or None,
            res_id=el.get("resource-id") or None,
            package=el.get("package") or None,
            bounds=tuple(int(g) for g in m.groups()) if m else None,
            checkable=b(el, "checkable"),
            checked=b(el, "checked"),
            clickable=b(el, "clickable"),
            enabled=el.get("enabled") != "false",
            focusable=b(el, "focusable"),
            focused=b(el, "focused"),
            long_clickable=b(el, "long-clickable"),
            password=b(el, "password"),
            scrollable=b(el, "scrollable"),
            selected=b(el, "selected"),
            visible_to_user=el.get("visible-to-user") != "false",
            index=el.get("index"),
            drawing_order=el.get("drawing-order"),
            display_id=el.get("display-id"),
        )
        for ch in el.findall("node"):
            cn = conv(ch)
            cn.parent = n
            n.children.append(cn)
        return n

    return [conv(el) for el in root.findall("node")]


def fetch_u2(serial: Optional[str], quiet: bool = False) -> tuple:
    """连接设备并取**非压缩**全量层次。返回 (xml_text, meta)。

    失败一律抛异常 —— 不做「拿不到就退回 dumpsys」的静默降级，
    那会让同一条命令有时候是一体式结果、有时候只有一半。
    """
    try:
        import uiautomator2 as u2
    except ImportError as e:
        raise AdbError(
            "未安装 uiautomator2。本工具以它为主数据源，装不上就无法产出结果。\n"
            "  安装： <python> -m pip install uiautomator2\n"
            f"  (import 报错：{e})"
        )
    try:
        d = u2.connect(serial) if serial else u2.connect()
    except Exception as e:
        raise AdbError(f"uiautomator2 连接失败（{serial}）：{type(e).__name__}: {e}")

    try:
        info = dict(d.info or {})
    except Exception:
        info = {}
    try:
        info = dict(info, window_size=list(d.window_size()))
    except Exception:
        pass

    try:
        xml = d.dump_hierarchy(compressed=False)
    except TypeError:
        xml = d.dump_hierarchy()          # 老版本没有 compressed 形参
    except Exception as e:
        raise AdbError(f"dump_hierarchy 失败：{type(e).__name__}: {e}")

    if not xml or "<hierarchy" not in xml:
        raise AdbError("dump_hierarchy 返回内容不含 <hierarchy>，无法解析")

    try:
        import importlib.metadata as md
        ver = md.version("uiautomator2")
    except Exception:
        ver = "?"

    if not quiet:
        print(c(f"[u2] uiautomator2 {ver} 已连接，层次 {len(xml)} 字节", C.GRY),
              file=sys.stderr)
    return xml, {"version": ver, "info": info}


# ------------------------------------------------------------------ 一体式树


def classify_view_extra(v: Node, own_abs: Optional[tuple],
                        visible_rect: Optional[tuple]) -> str:
    """给「a11y 未收录」的 dumpsys 节点归因。

    两个矩形必须分开给，否则会误判（实测踩过）：
      own_abs      = 该节点自身的累加布局矩形（**不**与祖先求交）
      visible_rect = own_abs ∩ 各祖先矩形 ∩ 屏幕
    若把两者混用，「完全落在滚动容器可视区之外」的节点（如 frame3..frame10，自身
    1008×1080）会被链式求交压成零面积矩形，从而被误判成「零面积」。
    """
    if v.gone:
        return "GONE（a11y 不收录不可见节点）"
    if own_abs is None:
        return "无布局矩形（dump 未输出 bounds）"
    if own_abs[2] <= own_abs[0] or own_abs[3] <= own_abs[1]:
        return "零面积（自身布局矩形为空，不占布局）"
    if visible_rect is None or visible_rect[2] <= visible_rect[0] or visible_rect[3] <= visible_rect[1]:
        return "裁剪后无可见部分（在屏幕外，或位于滚动容器可视区之外）"
    return "a11y 未收录（原因未定）"


def merge_children(u: U2Node, v: Node) -> Optional[list]:
    """把「已配对的 a11y 子序列」与「view 子序列」合并成一个统一顺序。

    这是**唯一**判断「dumpsys 独有子节点的位次是否已确定」的地方，
    输出与统计都调它，避免两处判据漂移（实测踩过：同一批节点既出现在主树里、
    又被列进「位置无法确定」的章节）。

    成立条件（必须同时满足）：
      a) u 的**每一个**子节点都已配对；
      b) 这些子节点在 v.children 里恰好各出现一次。
    成立 → 返回 [("a", U2Node) | ("d", Node)] 的唯一顺序。
    不成立 → 返回 None，**不做任何位次推测**。
    """
    kids = u.children
    if any(c.view is None for c in kids):
        return None
    inv = {id(c.view): c for c in kids}
    order = []
    hit = 0
    for vc in v.children:
        uc = inv.get(id(vc))
        if uc is None:
            order.append(("d", vc))
        else:
            order.append(("a", uc))
            hit += 1
    if hit != len(kids):
        return None
    return order


def geom_of(u: U2Node, screen: Optional[tuple]) -> str:
    """已配对节点的几何校验档位（exact / clip / drift / na）。

    **判据只能有一处**，否则同一条命令的不同输出会对同一个节点给出不同结论。
      exact: 未裁剪累加布局矩形 == a11y 屏幕读数（该坐标被独立证实）
      clip : 只按祖先裁剪、或再按屏幕裁剪后 == 读数（有屏外内容被裁）
      drift: 两者都不等（实测为焦点项的 1.05 缩放）
      na   : 缺读数或缺布局矩形，无法比对
    """
    if u.bounds is None or u.view is None:
        return "na"
    av = absolute_bounds(u.view)
    if av is None:
        return "na"
    if av == u.bounds:
        return "exact"
    if (clip_to_chain(u.view, None) == u.bounds
            or pred_visible_rect(u.view, screen) == u.bounds):
        return "clip"
    return "drift"


def build_unified(u2_roots: list, view_roots: list, st: AlignStats,
                  screen: Optional[tuple]) -> list:
    """建一体式树：a11y 树为骨架，把位次已确定的 view 独有节点插入。

    每层子节点顺序由 merge_children() 唯一给出；拿不到顺序就不插入那层的独有节点
    （它们会出现在 `dumpsys_only` 章节里）。
    """
    paired_v = {id(u.view): u for u in u2_all(u2_roots) if u.view is not None}

    def conv_u(u: U2Node) -> UniNode:
        n = UniNode(kind="a11y", u=u)
        if u.view is not None:
            n.geom = geom_of(u, screen)
        order = merge_children(u, u.view) if u.view is not None else None
        if order is None:
            for uc in u.children:
                n.children.append(conv_u(uc))
        else:
            for tag, obj in order:
                n.children.append(conv_u(obj) if tag == "a" else conv_extra(obj))
        return n

    def conv_extra(v: Node) -> UniNode:
        n = UniNode(kind="dumpsys", v=v,
                    note=classify_view_extra(v, absolute_bounds(v),
                                             pred_visible_rect(v, screen)))
        # 该节点不在 a11y 树里，其子树顺序完全由 view 树决定，无歧义
        for vc in v.children:
            uc = paired_v.get(id(vc))
            n.children.append(conv_u(uc) if uc is not None else conv_extra(vc))
        return n

    return [conv_u(u) for u in u2_roots]


# ------------------------------------------------------------------ 采集编排


def _hierarchy_lines(raw: str) -> list:
    """从 dumpsys 文本里取出**我们真正消费的部分**：View 层次行。

    为什么单独抽出来比：整份 dumpsys 里含 `mLastFrameTime=… (N ms ago)` 这类
    单调时钟字段，每次抓取必然变化。拿整份文本做前后一致性比较会**恒定误报**
    「画面在动」—— 误报比漏报更伤信任。
    """
    return [ln.rstrip() for ln in raw.splitlines() if "{" in ln and "}" in ln]


def hierarchy_drift(raw_a: str, raw_b: str) -> tuple:
    """返回 (是否漂移, 差异说明)。只给第一处不同，便于人工判断。"""
    la, lb = _hierarchy_lines(raw_a), _hierarchy_lines(raw_b)
    if la == lb:
        return False, None
    if len(la) != len(lb):
        return True, f"View 层次行数 {len(la)} → {len(lb)}"
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return True, (f"第 {i + 1} 行不同：\n      旧 {x.strip()[:120]}\n"
                          f"      新 {y.strip()[:120]}")
    return True, "内容不同（顺序差异）"


def snapshot(adb: Adb, serial: Optional[str], save_raw: Optional[str],
             quiet: bool, use_dumpsys: bool = True) -> dict:
    """同一时刻抓两棵树（先 dumpsys 后 a11y，间隔最小化并记录前后一致性）。"""
    dev = {}
    try:
        dev = adb.props()
    except AdbError:
        pass
    screen = adb.screen()
    win = adb.window_focus()

    top1 = top2 = ""
    blocks, blk, note, drift, drift_detail = [], None, None, False, None
    if use_dumpsys:
        top1 = adb.exec_out(["dumpsys", "activity", "top"]).decode("utf-8", "replace")
    xml, u2_meta = fetch_u2(serial, quiet=quiet)
    if use_dumpsys:
        top2 = adb.exec_out(["dumpsys", "activity", "top"]).decode("utf-8", "replace")
        drift, drift_detail = hierarchy_drift(top1, top2)
        blocks = parse_dumpsys_top(top2)
        blk, note = pick_block_ex(blocks, win.get("component"))
        if blk is None:
            note = "dump 里没有可用的 ACTIVITY 段"
        if note and not quiet:
            print(c(f"[段匹配] {note}", C.YEL), file=sys.stderr)

    pkg = blk.component.split("/")[0] if blk else None

    if save_raw:
        os.makedirs(save_raw, exist_ok=True)
        pairs = [("u2_hierarchy.xml", xml)]
        if use_dumpsys:
            pairs += [("activity_top_before.txt", top1), ("activity_top_after.txt", top2)]
        for name, text in pairs:
            with open(os.path.join(save_raw, name), "w", encoding="utf-8") as f:
                f.write(text)

    return {"dev": dev, "screen": screen, "win": win, "xml": xml, "u2_meta": u2_meta,
            "blocks": blocks, "block": blk, "pkg": pkg, "pick_note": note,
            "drift": drift, "drift_detail": drift_detail}


def _flat(roots) -> list:
    return list(iter_nodes(roots))


def run_align(snap: dict, quiet: bool = False) -> tuple:
    u2_roots = parse_u2_xml(snap["xml"])
    view_roots = snap["block"].roots if snap["block"] else []
    scr = (0, 0, snap["screen"].get("width") or 0, snap["screen"].get("height") or 0)
    st = align(u2_roots, view_roots, snap["pkg"], scr if scr[2] else None)
    st.window_note = snap["pick_note"]

    # 窗口一致性：a11y 根节点自报的 package 必须与选中的 dumpsys 段一致
    if u2_roots and view_roots:
        up = u2_roots[0].package
        if up and snap["pkg"] and up != snap["pkg"]:
            st.align_skipped = (
                f"a11y 根节点自报 package={up}，与选中的 dumpsys 段 package={snap['pkg']} "
                f"不一致；两棵树不是同一个窗口，**不做任何配对**。")
            st2 = AlignStats(a11y_nodes=st.a11y_nodes, view_nodes=st.view_nodes)
            st2.align_skipped = st.align_skipped
            st2.a11y_unpaired = u2_all(u2_roots)
            st2.view_unpaired = _flat(view_roots)
            return u2_roots, view_roots, st2
    return u2_roots, view_roots, st


# ------------------------------------------------------------------ 全量 JSON


def _rev_chain(node) -> list:
    chain = []
    cur = node
    while cur is not None:
        chain.append(cur)
        cur = cur.parent
    return list(reversed(chain))


def build_full_json(u2_roots: list, view_roots: list, u2_meta: dict, dev: dict,
                    screen: dict, win: dict, st: AlignStats, pkg: Optional[str],
                    snap: Optional[dict] = None, show_dumpsys: bool = True) -> dict:
    """把**一体式树**序列化成 JSON。

    节点用 `source` 区分：
      `"a11y"`    → 主源节点，`bounds_screen` 是**屏幕上真实可见的矩形**（读数）
      `"dumpsys"` → a11y 未收录、由 R3 补入的节点，`bounds_local` 是**相对父容器**的布局读数
    """
    _w, _h = screen.get("width") or 0, screen.get("height") or 0
    _scr = (0, 0, _w, _h) if _w and _h else None

    def u2_fields(n: U2Node) -> dict:
        return {
            "source": "a11y",
            "class": n.cls,
            "resource_id": n.res_id,
            "package": n.package,
            "bounds_screen": list(n.bounds) if n.bounds else None,
            "index": n.index,
            "text": n.text,
            "content_desc": n.desc,
            "hint": n.hint,
            "checkable": n.checkable,
            "checked": n.checked,
            "clickable": n.clickable,
            "enabled": n.enabled,
            "focusable": n.focusable,
            "focused": n.focused,
            "long_clickable": n.long_clickable,
            "password": n.password,
            "scrollable": n.scrollable,
            "selected": n.selected,
            "visible_to_user": n.visible_to_user,
            "drawing_order": n.drawing_order,
            "display_id": n.display_id,
        }

    def dumpsys_extra(u: U2Node) -> dict:
        """配对上来的 dumpsys 侧补充字段（只放 view 侧**独有**的信息）。"""
        v = u.view
        extra = {
            "match_reason": u.match_reason,
            "aid": v.aid,
            "view_hash": v.vhash,
            "outer": {"hash": v.ohash, "name": v.oname},
            "id_hex": v.id_hex,
            "bounds_local": list(v.bounds) if v.bounds else None,
            "bounds_abs_unclipped": (lambda x: list(x) if x else None)(absolute_bounds(v)),
            "flags1": v.flags1,
            "flags2": v.flags2,
            "drawn": bool(v.flags1 and len(v.flags1) > 3 and v.flags1[3] == "D"),
            "context_clickable": bool(v.flags1 and len(v.flags1) > 8 and v.flags1[8] == "X"),
            "scrollbar_h": v.scrollbar_h,
            "scrollbar_v": v.scrollbar_v,
        }
        p_only = clip_to_chain(v, None)
        extra["pred_visible_rect"] = list(p_only) if p_only else None
        return extra

    def view_fields(n: Node) -> dict:
        return {
            "source": "dumpsys",
            "class": n.cls,
            "resource_id": n.res_id,
            "resource_id_normalized": norm_res_id(n.res_id, pkg),
            "bounds_local": list(n.bounds) if n.bounds else None,
            "bounds_abs_unclipped": (lambda x: list(x) if x else None)(absolute_bounds(n)),
            "pred_visible_rect": (lambda x: list(x) if x else None)(clip_to_chain(n, None)),
            "visible": n.visible,
            "gone": n.gone,
            "focusable": n.focusable,
            "clickable": n.clickable,
            "long_clickable": n.long_clickable,
            "enabled": n.enabled,
            "drawn": bool(n.flags1 and len(n.flags1) > 3 and n.flags1[3] == "D"),
            "context_clickable": bool(n.flags1 and len(n.flags1) > 8 and n.flags1[8] == "X"),
            "scrollbar_h": n.scrollbar_h,
            "scrollbar_v": n.scrollbar_v,
            "aid": n.aid,
            "view_hash": n.vhash,
            "outer": {"hash": n.ohash, "name": n.oname},
            "id_hex": n.id_hex,
            "flags1": n.flags1,
            "flags2": n.flags2,
            "why_not_in_a11y": classify_view_extra(n, absolute_bounds(n),
                                                  pred_visible_rect(n, _scr)),
        }

    def keep_child(ch) -> bool:
        return show_dumpsys or ch.kind != "dumpsys"

    def uni_json(n) -> dict:
        if n.kind == "dumpsys":
            o = view_fields(n.v)
            o["note"] = n.note
            o["position_by"] = "R3：兄弟位次由 view 子序列顺序唯一确定（不是推测）"
        else:
            o = u2_fields(n.u)
            o["geom_check"] = n.geom
            if show_dumpsys and n.u.view is not None:
                o["dumpsys"] = dumpsys_extra(n.u)
        o["children"] = [uni_json(ch) for ch in n.children if keep_child(ch)]
        return o

    def view_only_json(n: Node) -> dict:
        o = view_fields(n)
        o["children"] = [view_only_json(ch) for ch in n.children]
        return o

    uni = build_unified(u2_roots, view_roots, st, _scr) if show_dumpsys else \
        build_unified(u2_roots, [], AlignStats(), None)

    drift = bool(snap and snap.get("drift"))
    out = {
        "mode": "full",
        "generator": "tv_tree.py",
        "captured_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "primary_source": "uiautomator2 (a11y)",
        "supplement_source": ("dumpsys activity top (View Hierarchy)"
                              if show_dumpsys else None),
        "u2": {"version": u2_meta.get("version"), "info": u2_meta.get("info")},
        "device": dev,
        "screen": screen,
        "window": win,
        "segment": pkg,
        "source_consistency": {
            "dumpsys_taken_twice": show_dumpsys,
            "drift": drift,
            "detail": (snap or {}).get("drift_detail"),
            "note": ("两次 dumpsys 之间 View 层次行不一致 → 画面在动，"
                     "配对结果的可信度下降" if drift else
                     "两次 dumpsys 的 View 层次行一致（单调时钟字段已排除，不参与比较）"
                     if show_dumpsys else "未抓取 dumpsys"),
        },
        "segment_match_note": (snap or {}).get("pick_note"),
        "coordinate_note": {
            "bounds_screen": "a11y 读数：屏幕上真实可见的矩形（已按祖先与屏幕裁剪）",
            "bounds_local": "dumpsys 读数：相对父容器的布局矩形（未裁剪）",
            "bounds_abs_unclipped": "由 bounds_local 沿祖先累加得出的**派生值**；前提是祖先链"
                                    "上没有滚动偏移，该前提由逐节点的 geom_check 给出，不做全局假设",
            "pred_visible_rect": "**派生值**：bounds_abs_unclipped ∩ 各祖先 ∩ 屏幕",
        },
        "align_rules": {
            "R0": "两侧各唯一根 → 同一窗口根",
            "R1": "pred_visible_rect(view)==a11y bounds 且 res-id/class 谓词成立且候选唯一",
            "R2": "两侧各自唯一 focused 且 class 谓词成立",
            "R3": "父已配对时 a11y 子序列到 view 子序列的保序全注入解唯一才采用",
            "predicate_resid": "view 侧 app:id/X 归一化为 <段包名>:id/X 后字符串相等（同为 None 也算）",
            "predicate_class": "view 类名为框架类时要求与 a11y 类名完全相等；自定义类不要求（会被 a11y 替换）",
        },
        "align_stats": {
            "a11y_nodes": st.a11y_nodes,
            "view_nodes": st.view_nodes,
            "paired": st.paired,
            "by_reason": st.by_reason,
            "geom_exact": st.geom_exact,
            "geom_clip": st.geom_clip,
            "geom_drift": st.geom_drift,
            "geom_na": st.geom_na,
            "class_substituted": st.class_substituted,
            "a11y_unpaired": len(st.a11y_unpaired),
            "view_unpaired": len(st.view_unpaired),
            "dumpsys_only_inserted": len(st.insert_pos),
            "unexplained_visible_not_in_a11y": [
                {"class": v.short_cls, "bounds": v.bounds_str, "resource_id": v.res_id}
                for v in st.unexplained],
            "seq_refused": [{"view": v.short_cls, "a11y": u.short_cls, "why": w}
                            for v, u, w in st.seq_refused],
            "align_skipped": st.align_skipped,
            "window_note": st.window_note,
        },
        "tree_note": "tree 是**一体式树**：source=a11y 的节点坐标是屏幕可见矩形读数；"
                     "source=dumpsys 的节点是 a11y 未收录、由 R3 按 view 子序列顺序补入的"
                     "（坐标是相对父容器的布局坐标，不是屏幕坐标）。",
        "tree": [uni_json(n) for n in uni if keep_child(n)],
        "dumpsys_only": ([] if not show_dumpsys
                         else [view_only_json(v) for v in st.view_unpaired]),
        "focus": [{
            "class": u.cls,
            "resource_id": u.res_id,
            "bounds_screen": list(u.bounds) if u.bounds else None,
            "text": u.text,
            "content_desc": u.desc,
            "path": " > ".join(cur.short_cls for cur in _rev_chain(u)),
        } for u in find_u2_focus(u2_roots)],
    }
    return out


# ------------------------------------------------------------------ 剪枝（精简 JSON）


# 每个开关： (作用域说明, 默认是否执行剪枝, 剪掉什么)
PRUNE_SWITCHES = {
    "gone": (
        "树", True,
        "visibility=GONE 的节点（只可能出现在 dumpsys 侧；a11y 根本不收录不可见节点）。"
        "GONE 的 View 不做布局也不参与绘制，故整棵子树一并剪掉"),
    "zeroarea": (
        "树", True,
        "自身布局矩形为零面积的节点。整棵子树一并剪掉——子节点的 bounds_local 是"
        "相对该节点的，脱离它之后坐标不可解释，保留等于给出无法解释的坐标"),
    "offscreen": (
        "树", True,
        "可见区域与屏幕无交集的节点。整棵子树一并剪掉——可见区域满足单调性"
        "（子节点的可见矩形 ⊆ 父节点的可见矩形），剪子树不会漏掉可见内容"),
    "empty": (
        "树", True,
        "「自身与整棵子树都没有任何信息」的节点（无文字/描述/提示、无 resource-id、"
        "不可点击/聚焦/长按/滚动/勾选）。整棵子树一并剪掉——按定义它不含信息"),
    "derived": (
        "字段", True,
        "派生量：bounds_abs_unclipped、pred_visible_rect。它们由布局坐标累加/裁剪得出，"
        "不是读数；剪掉后剩下的坐标全部是数据源直读值"),
    "defaults": (
        "字段", True,
        "取默认值的布尔字段（false 一律省略，enabled/visible/visible_to_user 的 true 省略）。"
        "省略即表示默认值，默认值表见输出里的 slim.field_defaults"),
    "meta": (
        "字段", True,
        "对齐元数据：节点上的 geom_check / match_reason / why_not_in_a11y / position_by / "
        "note，以及顶层的 coordinate_note / align_rules / align_stats / tree_note"),
    "instance": (
        "字段", True,
        "实例标识：view_hash / id_hex / outer / aid / drawing_order。它们用于跨两次 dump "
        "认同一个 View，对「这一屏长什么样」没有贡献"),
}

# defaults 开关用的默认值表（字段名 → 默认值）
FIELD_DEFAULTS = {
    "checkable": False, "checked": False, "clickable": False, "context_clickable": False,
    "drawn": False, "focusable": False, "focused": False, "gone": False,
    "long_clickable": False, "password": False, "scrollable": False,
    "scrollbar_h": False, "scrollbar_v": False, "selected": False,
    "enabled": True, "visible": True, "visible_to_user": True,
}

# 树级开关的认领优先序：一个节点只归第一个命中的开关
OWNER_PRIORITY = ("gone", "zeroarea", "offscreen", "empty")

DERIVED_FIELDS = ("bounds_abs_unclipped", "pred_visible_rect")
META_FIELDS = ("geom_check", "match_reason", "why_not_in_a11y", "position_by", "note")
INSTANCE_FIELDS = ("view_hash", "id_hex", "outer", "aid", "drawing_order")
TOP_META_FIELDS = ("coordinate_note", "align_rules", "align_stats", "tree_note")

# a11y 侧「这个节点算不算带信息」看的字段
_U2_INFO_TEXT = ("text", "content_desc", "hint")
_U2_INFO_BOOLS = ("clickable", "focusable", "long_clickable", "scrollable",
                  "checkable", "checked", "selected", "password", "focused")


def default_switches() -> dict:
    """默认状态：每个开关是否执行剪枝。"""
    return {k: v[1] for k, v in PRUNE_SWITCHES.items()}


def parse_switch_spec(spec: Optional[str], names) -> list:
    """解析逗号分隔的开关名；all / * = 全部。非法值直接报错，不猜。"""
    if not spec:
        return []
    out = []
    for tok in str(spec).replace("，", ",").split(","):
        t = tok.strip().lower()
        if not t:
            continue
        if t in ("all", "*"):
            for x in names:
                if x not in out:
                    out.append(x)
            continue
        if t not in names:
            raise ValueError(f"未知的剪枝开关 {t!r}；可用：{', '.join(names)}（或 all）")
        if t not in out:
            out.append(t)
    return out


def _rect_of(node: dict) -> Optional[tuple]:
    """该节点用于「屏幕外 / 零面积」判定的矩形（都是读数口径）。

    a11y 节点用 bounds_screen（屏幕绝对读数）；
    dumpsys 节点用 bounds_local（相对父容器的布局读数）判零面积、
    用派生出的可见矩形判屏幕外。
    """
    if node.get("source") == "a11y":
        b = node.get("bounds_screen")
    else:
        b = node.get("bounds_local")
    return tuple(b) if b else None


def _is_zeroarea(node: dict) -> bool:
    r = _rect_of(node)
    if r is None:
        return True                      # 布局矩形缺失 = 不占布局
    return r[2] <= r[0] or r[3] <= r[1]


def _visible_rect(node: dict, screen: Optional[tuple]) -> Optional[tuple]:
    """可见矩形。a11y 是读数；dumpsys 只有派生值可用（判屏幕外够用，输出时不冒充读数）。"""
    if node.get("source") == "a11y":
        b = node.get("bounds_screen")
        if not b:
            return None
        r = tuple(b)
        return intersect(r, screen) if screen else r
    p = node.get("pred_visible_rect")
    if p:
        return tuple(p)
    # 全量 JSON 里的 dumpsys 节点带 pred_visible_rect；若被 --from-json 的裁剪结果
    # 喂进来而缺失，则退回用 bounds_abs_unclipped 自己算一次，算不出就不判。
    ab = node.get("bounds_abs_unclipped")
    if ab and screen:
        return intersect(tuple(ab), screen)
    return None


def _is_offscreen(node: dict, screen: Optional[tuple]) -> bool:
    r = _visible_rect(node, screen)
    if r is None:
        return False                     # 判不了就不剪（不猜）
    return r[2] <= r[0] or r[3] <= r[1]


def _has_own_info(node: dict) -> bool:
    for k in _U2_INFO_TEXT:
        if node.get(k):
            return True
    if node.get("resource_id"):
        return True
    for k in _U2_INFO_BOOLS:
        if node.get(k):
            return True
    return False


def _has_info(node: dict) -> bool:
    """自身或**整棵子树**是否含信息。"""
    if _has_own_info(node):
        return True
    return any(_has_info(ch) for ch in (node.get("children") or []))


def _subtree_size(node: dict) -> int:
    return 1 + sum(_subtree_size(ch) for ch in (node.get("children") or []))


def _prune_fields(node: dict, sw: dict) -> None:
    """字段级剪枝。递归到子节点（树结构此时已定型）。"""
    targets = [node]
    if isinstance(node.get("dumpsys"), dict):
        targets.append(node["dumpsys"])
    for t in targets:
        if sw["derived"]:
            for k in DERIVED_FIELDS:
                t.pop(k, None)
        if sw["instance"]:
            for k in INSTANCE_FIELDS:
                t.pop(k, None)
        if sw["meta"]:
            for k in META_FIELDS:
                t.pop(k, None)
        if sw["defaults"]:
            for k, dv in FIELD_DEFAULTS.items():
                if k in t and t[k] == dv:
                    del t[k]


def _owner_switch(node: dict, screen: Optional[tuple]) -> Optional[str]:
    """这个节点归哪个开关管。None = 不该被剪。

    **每个节点只由一个开关认领**（按下面的固定优先序，先命中先认领）。
    这样 `--keep <开关>` 才有确定语义：关掉它，这一类节点就整类留下来，
    不会被后面的开关顺手剪掉。

    实测教训（不这么写就会踩）：14 个 GONE 节点**全部**是零面积矩形，
    于是 `--keep gone` 把它们放过后又被 `zeroarea` 认领剪掉，节点数一个没变 ——
    开关表里写着「可保留」的选项实际不起作用。
    """
    if node.get("source") == "dumpsys" and node.get("gone"):
        return "gone"
    if _is_zeroarea(node):
        return "zeroarea"
    if _is_offscreen(node, screen):
        return "offscreen"
    if not _has_info(node):
        return "empty"
    return None


def _prune_node(node: dict, sw: dict, screen: Optional[tuple], stats: dict) -> Optional[dict]:
    """对一个节点及其子树施加剪枝。返回 None 表示该子树被剪掉。

    认领规则见 _owner_switch()：一个节点只归一个开关，该开关开着才剪。
    """
    owner = _owner_switch(node, screen)
    if owner is not None and sw[owner]:
        stats[owner] = stats.get(owner, 0) + _subtree_size(node)
        return None
    node["children"] = [x for x in
                        (_prune_node(ch, sw, screen, stats) for ch in node.get("children") or [])
                        if x is not None]
    _prune_fields(node, sw)
    return node


def apply_prune(obj: dict, sw: dict) -> dict:
    """**在已经生成好的全量 JSON 上**做剪枝，返回精简 JSON（原地改）。

    剪枝的对象就是全量 JSON 本身，不是另一条采集路径 —— 所以两种模式表达的是
    同一棵树、同一批读数，差别只在「留多少」。
    """
    screen = None
    s = obj.get("screen") or {}
    if s.get("width") and s.get("height"):
        screen = (0, 0, s["width"], s["height"])

    before = sum(_subtree_size(n) for n in (obj.get("tree") or []))
    before += sum(_subtree_size(n) for n in (obj.get("dumpsys_only") or []))
    stats: dict = {}

    obj["tree"] = [x for x in
                   (_prune_node(n, sw, screen, stats) for n in (obj.get("tree") or []))
                   if x is not None]
    obj["dumpsys_only"] = [x for x in
                           (_prune_node(n, sw, screen, stats)
                            for n in (obj.get("dumpsys_only") or []))
                           if x is not None]
    after = sum(_subtree_size(n) for n in obj["tree"])
    after += sum(_subtree_size(n) for n in obj["dumpsys_only"])

    if sw["meta"]:
        for k in TOP_META_FIELDS:
            obj.pop(k, None)

    obj["mode"] = "slim"
    obj["slim"] = {
        "derived_from": "全量 JSON（同一次采集、同一棵树；只做剪枝，不做二次采集）",
        "switches": dict(sw),                       # true = 该开关已执行剪枝
        "pruned_nodes": {k: stats.get(k, 0) for k in PRUNE_SWITCHES},
        "nodes": {"full": before, "slim": after},
        "switch_meaning": {k: v[2] for k, v in PRUNE_SWITCHES.items()},
        "ownership": ("每个节点只由一个开关认领，按固定优先序先命中先认领："
                      + " → ".join(OWNER_PRIORITY)
                      + "。pruned_nodes 记的是各开关认领的节点数（含被剪子树的全部后代）。"
                        "所以 --keep <开关> 的语义是确定的：关掉它，这一类节点整类保留，"
                        "不会被后面的开关顺手剪掉。"),
        "field_defaults": (dict(FIELD_DEFAULTS) if sw["defaults"] else None),
        "note": ("想保留某类信息：--keep <开关名>（all = 一个都不剪）。"
                 "meta 开关还会剪掉 align_stats（对齐与几何校验统计）——"
                 "要看那部分用 --mode full 或 --keep meta。"),
    }
    return obj


# ------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tv_tree.py",
        description="Android TV 控件树采集 → JSON。uiautomator2(a11y) 为主源，"
                    "dumpsys activity top 为补充源，按显式可验证规则 R0–R3 合并成一棵树。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  python tv_tree.py --out full.json              # 全量 JSON（默认）
  python tv_tree.py --mode slim --out slim.json  # 精简 JSON
  python tv_tree.py --mode slim --keep empty     # 精简，但保留空节点
  python tv_tree.py --mode slim --keep all       # 精简，但一个开关都不剪（= 全量）
  python tv_tree.py --prune-list                 # 看剪枝开关表
  python tv_tree.py --from-json full.json --mode slim --out slim.json   # 离线重剪，不连设备
""")
    add_conn_args(p)
    p.add_argument("--mode", choices=["full", "slim"], default="full",
                   help="full=全量 JSON（默认）；slim=在全量 JSON 上剪枝得到的精简 JSON")
    p.add_argument("--keep", default=None, metavar="LIST",
                   help="精简版的增量选项：把指定剪枝开关**关掉**，把那部分信息加回来。"
                        "逗号分隔，all=全部关掉（等价于全量）。仅 --mode slim 生效")
    p.add_argument("--prune-list", action="store_true", help="打印剪枝开关表后退出")
    p.add_argument("--from-json", default=None, metavar="FILE",
                   help="不连设备：直接对一份已有的**全量** JSON 做剪枝（配合 --mode slim）")
    p.add_argument("--out", default=None, metavar="FILE",
                   help="把 JSON 写到文件（UTF-8，无 BOM）。默认打到 stdout")
    p.add_argument("--no-dumpsys", action="store_true",
                   help="只用主源 a11y：不抓 dumpsys、不做配对、不输出 dumpsys 章节")
    p.add_argument("--save-raw", default=None, metavar="DIR",
                   help="把原始输入落盘到该目录（u2 层次 XML + 两次 dumpsys 原文），便于人工复核")
    return p


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


def _emit(obj: dict, out_path: Optional[str]) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        print(c(f"[out] 已写入 {out_path}（{len(text)} 字节）", C.GRY), file=sys.stderr)
    else:
        print(text)


def _summary(obj: dict, out_path: Optional[str]) -> None:
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
    return sum(1 + _desc_count(n) for n in nodes)


def _desc_count(node: dict) -> int:
    """后代数量（不含自身）。"""
    return sum(1 + _desc_count(ch) for ch in (node.get("children") or []))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    setup_console(args.no_color)

    if args.prune_list:
        print_prune_list()
        return 0

    # ---- 剪枝参数
    try:
        keep = parse_switch_spec(args.keep, list(PRUNE_SWITCHES))
    except ValueError as e:
        print(c(str(e), C.RED), file=sys.stderr)
        return 2
    if keep and args.mode != "slim":
        print(c("--keep 只在 --mode slim 下有意义；全量 JSON 本来就没有剪枝。", C.RED),
              file=sys.stderr)
        return 2
    sw = default_switches()
    for k in keep:
        sw[k] = False

    # ---- 离线重剪：不连设备
    if args.from_json:
        if args.mode != "slim":
            print(c("从 JSON 再输出一份全量没有意义；请加 --mode slim。", C.RED),
                  file=sys.stderr)
            return 2
        try:
            with open(args.from_json, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception as e:
            print(c(f"读不了 {args.from_json}：{type(e).__name__}: {e}", C.RED),
                  file=sys.stderr)
            return 2
        if not isinstance(obj.get("tree"), list):
            print(c(f"{args.from_json} 里没有 tree，不像是本工具输出的全量 JSON。", C.RED),
                  file=sys.stderr)
            return 2
        apply_prune(obj, sw)
        _emit(obj, args.out)
        _summary(obj, args.out)
        return 0

    # ---- 连设备采集
    adb = connect_device(args)
    if adb is None:
        return 2

    try:
        snap = snapshot(adb, adb.serial, args.save_raw, args.quiet,
                        use_dumpsys=not args.no_dumpsys)
    except AdbError as e:
        print(c(str(e), C.RED), file=sys.stderr)
        return 3

    if not args.no_dumpsys and snap["block"] is None:
        print(c("dumpsys 里没有可用的 ACTIVITY 段，拿不到补充源。"
                "（若确认不需要补充源，用 --no-dumpsys）", C.RED), file=sys.stderr)
        return 3

    try:
        u2_roots, view_roots, st = run_align(snap, args.quiet)
    except Exception as e:
        print(c(f"配对失败：{type(e).__name__}: {e}", C.RED), file=sys.stderr)
        return 3

    # 解析期发现的异常（有字段却没读出来 / 缩进不是 2 的倍数）如实报出，不静默吞掉
    if PARSE_ANOMALIES:
        print(c(f"[解析告警] {len(PARSE_ANOMALIES)} 行未能按格式完整解析——"
                f"即存在「没读出来」的数据：", C.YEL), file=sys.stderr)
        for ln, txt, why in PARSE_ANOMALIES[:8]:
            print(c(f"  第 {ln} 行：{why}", C.YEL), file=sys.stderr)
            print(c(f"    {txt}", C.GRY), file=sys.stderr)

    obj = build_full_json(u2_roots, view_roots, snap["u2_meta"], snap["dev"],
                          snap["screen"], snap["win"], st, snap["pkg"], snap,
                          show_dumpsys=not args.no_dumpsys)
    if args.mode == "slim":
        apply_prune(obj, sw)
    _emit(obj, args.out)
    _summary(obj, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
