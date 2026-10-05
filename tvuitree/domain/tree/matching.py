"""Geometry, R0–R3 matching, and unified-tree construction."""

from __future__ import annotations

from typing import Optional

from .models import (
    AlignStats, FRAMEWORK_CLS_PREFIXES, MATCH_FOCUS, MATCH_GEOM, MATCH_ROOT,
    MATCH_SEQ, Node, U2Node, UniNode,
)
from .parsing import iter_nodes

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


def clip_to_chain(node: Node) -> Optional[tuple]:
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


def pred_visible_rect(node: Node, screen: Optional[tuple]) -> Optional[tuple]:
    """view 节点的**预测可见矩形**：自身累加矩形 ∩ 各祖先累加矩形 ∩ 屏幕。

    纯几何计算，不含阈值、不含推测。它成立与否由 R1 与实际 a11y bounds 比对直接验证。
    """
    r = clip_to_chain(node)
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
    return list(iter_nodes(roots))


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
        if r is not None and id(v) not in paired_v:
            by_rect.setdefault(r, []).append(v)
    candidates, reverse_count = {}, {}
    for u in u_nodes:
        if id(u) in paired_u or u.bounds is None:
            continue
        values = [v for v in by_rect.get(u.bounds, [])
                  if resid_ok(v, u, pkg) and class_ok(v, u)[0]]
        candidates[id(u)] = values
        for v in values:
            reverse_count[id(v)] = reverse_count.get(id(v), 0) + 1
    for u in u_nodes:
        values = candidates.get(id(u), [])
        if len(values) == 1 and reverse_count[id(values[0])] == 1:
            bind(values[0], u, MATCH_GEOM)

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
        # 统计与节点输出共用几何分级。
        grade = geom_of(u, screen)
        field = f"geom_{grade}"
        setattr(st, field, getattr(st, field) + 1)

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
    if (clip_to_chain(u.view) == u.bounds
            or pred_visible_rect(u.view, screen) == u.bounds):
        return "clip"
    return "drift"


def build_unified(u2_roots: list, screen: Optional[tuple]) -> list:
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
