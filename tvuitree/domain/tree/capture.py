"""Coordinate TV reads and produce a single captured tree snapshot."""

from __future__ import annotations

from .models import AlignStats
from .parsing import iter_nodes, parse_u2_xml
from .matching import align, u2_all

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
