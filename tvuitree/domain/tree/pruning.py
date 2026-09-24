"""Apply the documented field and subtree pruning switches."""

from __future__ import annotations

from typing import Optional

from .matching import intersect

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
