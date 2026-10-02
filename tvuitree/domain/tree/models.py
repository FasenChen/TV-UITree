"""Tree data models and format constants shared by the collector."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

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
# Android 16 的 ViewDebug 可能把可选的外部 name 放在实例块后面，
# 例如 DecorView{abc ...}[MainSettings]。
NODE_RE_POST_NAME = re.compile(
    r"^(?P<indent>[ ]*)"
    r"(?P<cls>[A-Za-z_$][\w.$]*)"
    r"(?:@(?P<ohash>[0-9a-fA-F]+))?"
    r"(?:\{(?P<vhash>[0-9a-fA-F]+)(?P<rest>[^}]*)\})"
    r"\[(?P<oname>[^\]]*)\]"
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
def record_anomaly(lineno: int, text: str, why: str, anomalies: list) -> None:
    if len(anomalies) < 50:
        anomalies.append((lineno, text.strip()[:160], why))
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
    # 本工具也不做跨源回填：文字只以 a11y 读数为准，避免两个来源的读数被静默合成。

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
    def drawn(self) -> bool:
        return bool(self.flags1) and len(self.flags1) > 3 and self.flags1[3] == "D"

    @property
    def context_clickable(self) -> bool:
        return bool(self.flags1) and len(self.flags1) > 8 and self.flags1[8] == "X"

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
