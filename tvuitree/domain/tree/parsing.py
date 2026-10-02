"""Parse dumpsys and accessibility hierarchy input into tree models."""

from __future__ import annotations

from typing import Iterable, Optional

from tvuitree.domain.component import normalize_component
from .models import (
    ACT_RE, A11Y_BOUNDS_RE, BOUNDS_RE, DUMP_INDENT_UNIT, FLAGS_RE, NODE_RE,
    NODE_RE_POST_NAME, RES_RE, VH_RE, Block, Node, U2Node, record_anomaly,
)

# ------------------------------------------------------------------ 解析 dumpsys 视图树


def parse_node_line(text: str, lineno: int, indent: int,
                    anomalies: Optional[list] = None) -> Optional[Node]:
    m = NODE_RE.match(text) or NODE_RE_POST_NAME.match(text)
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
        if n.bounds is None and anomalies is not None:
            record_anomaly(lineno, text, f"该行有字段但没解析出 bounds：{rest!r}", anomalies)
    elif m.group("vhash") and anomalies is not None:
        record_anomaly(lineno, text, "有 {hash} 但后面没有任何字段", anomalies)
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


def parse_dumpsys_top(raw: str, anomalies: Optional[list] = None) -> list:
    """解析 `dumpsys activity top` 输出 → [Block]"""
    target: list = [] if anomalies is None else anomalies
    target.clear()
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
                    record_anomaly(i + 1, cur,
                             f"缩进 {ind} 不是 {DUMP_INDENT_UNIT} 的整数倍，树层级可能错位", target)
                node = parse_node_line(cur.lstrip(" ").rstrip(), i + 1, ind, target)
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
