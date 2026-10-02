"""Serialize aligned TV trees into the full JSON representation."""

from __future__ import annotations

from typing import Optional

from .models import AlignStats, Node, U2Node
from .matching import (
    absolute_bounds, build_unified, classify_view_extra, clip_to_chain,
    find_u2_focus, norm_res_id, pred_visible_rect,
)

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
                    snap: Optional[dict] = None, show_dumpsys: bool = True,
                    captured_at: Optional[str] = None) -> dict:
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
            "drawn": v.drawn,
            "context_clickable": v.context_clickable,
            "scrollbar_h": v.scrollbar_h,
            "scrollbar_v": v.scrollbar_v,
        }
        p_only = clip_to_chain(v)
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
            "pred_visible_rect": (lambda x: list(x) if x else None)(clip_to_chain(n)),
            "visible": n.visible,
            "gone": n.gone,
            "focusable": n.focusable,
            "clickable": n.clickable,
            "long_clickable": n.long_clickable,
            "enabled": n.enabled,
            "drawn": n.drawn,
            "context_clickable": n.context_clickable,
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

    # dumpsys_only 是「未定位节点」组成的森林：每个未定位节点恰好输出一次。
    # 子节点只递归未定位的那些——已配对的后代在主树里，再列一次就是同一个 View
    # 出现两遍；未定位的后代也不能再作为顶层项重复列出。
    unpaired = {id(v) for v in st.view_unpaired}

    def view_only_json(n: Node) -> dict:
        o = view_fields(n)
        o["children"] = [view_only_json(ch) for ch in n.children if id(ch) in unpaired]
        return o

    uni = build_unified(u2_roots, view_roots, _scr) if show_dumpsys else \
        build_unified(u2_roots, [], None)

    drift = bool(snap and snap.get("drift"))
    out = {
        "mode": "full",
        "generator": "tv_tree.py",
        "captured_at": captured_at,
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
                         else [view_only_json(v) for v in st.view_unpaired
                               if v.parent is None or id(v.parent) not in unpaired]),
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
