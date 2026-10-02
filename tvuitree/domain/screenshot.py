"""Pure screenshot coordinate selection and comparison."""

from __future__ import annotations


def walk(nodes: list, parent=None):
    """(node, parent) 深度优先。"""
    for n in nodes:
        yield n, parent
        yield from walk(n.get("children") or [], n)


class Node:
    """给 JSON 节点套一层，缓存 parent，方便做祖先链检查。"""

    def __init__(self, raw: dict, parent=None):
        self.raw = raw
        self.parent = parent
        self.children = [Node(ch, self) for ch in (raw.get("children") or [])]

    def __getitem__(self, k):
        return self.raw.get(k)

    def dumpsys(self) -> dict:
        d = self.raw.get("dumpsys")
        return d if isinstance(d, dict) else {}

    # ---- 两种坐标（都返回 (l,t,r,b) 或 None） ----
    def rect_a11y(self):
        b = self["bounds_screen"]
        return tuple(b) if b else None

    def rect_dumpsys(self):
        d = self.dumpsys()
        b = d.get("bounds_abs_unclipped") or self["bounds_abs_unclipped"]
        return tuple(b) if b else None

    def rect_local(self):
        """相对父容器的布局读数。

        统一树里的节点分两种：`source=dumpsys` 的节点把读数放在顶层，
        `source=a11y` 的节点放在嵌套的 `dumpsys` 子字典里。两种都要取 ——
        只看顶层的话，a11y 节点一律返回 None，于是 chain_overflow() 对它们
        永远返回 None：**告警形同虚设**，而这恰恰是 `--source dumpsys`
        要画派生框的那些节点。
        """
        d = self.dumpsys()
        b = d.get("bounds_local") or self["bounds_local"]
        return tuple(b) if b else None

    def label(self) -> str:
        cls = (self["class"] or "?").rsplit(".", 1)[-1]
        rid = self["resource_id"]
        txt = self["text"] or self["content_desc"] or self["hint"]
        s = cls + (f"#{rid.split('/')[-1]}" if rid else "")
        if txt:
            s += f' "{txt[:20]}"'
        return s

    def chain_overflow(self):
        """祖先链上是否有「矩形超出父容器」的容器。有 → 那条链的累加坐标不可信。"""
        cur = self
        while cur is not None and cur.parent is not None:
            b, pb = cur.rect_local(), cur.parent.rect_local()
            if b and pb and (b[0] < pb[0] or b[1] < pb[1] or b[2] > pb[2] or b[3] > pb[3]):
                name = (cur["class"] or "?").rsplit(".", 1)[-1]
                rid = cur["resource_id"]
                return (f"祖先 {name}{('#' + rid.split('/')[-1]) if rid else ''} 的矩形 "
                        f"{b[0]},{b[1]}-{b[2]},{b[3]} 超出其父容器 "
                        f"{pb[0]},{pb[1]}-{pb[2]},{pb[3]}（该容器有溢出内容）。滚动偏移就"
                        f"发生在这样的容器里，而 dump 不含 scrollX/scrollY —— 这条链上的"
                        f"累加坐标无法验证，画出来的框可能落在屏幕内但错误的控件上")
            cur = cur.parent
        return None


def flatten(roots) -> list:
    out = []

    def rec(n: Node):
        out.append(n)
        for ch in n.children:
            rec(ch)

    for r in roots:
        rec(r)
    return out


def is_actionable(n: Node) -> bool:
    d = n.dumpsys()
    return bool(n["clickable"] or n["focusable"] or n["focused"]
                or d.get("clickable") or d.get("focusable"))


# ------------------------------------------------------------------ 收集要画的框


def collect(obj: dict, draw: str, source: str) -> tuple:
    """返回 (boxes, warnings)。box = (l, t, r, b, label, kind)。

    kind: "reading"（a11y 读数，实线红） / "derived"（dumpsys 派生，虚线蓝）
    """
    all_nodes = (flatten([Node(n) for n in obj.get("tree") or []])
                 + flatten([Node(n) for n in obj.get("dumpsys_only") or []]))
    if draw == "focus":
        picked = [n for n in all_nodes if n["focused"]]
    elif draw == "actionable":
        picked = [n for n in all_nodes if is_actionable(n)]
    else:
        picked = [n for n in all_nodes if n.rect_a11y() or n.rect_dumpsys()]

    boxes, warnings = [], []
    for n in picked:
        want = []
        if source in ("a11y", "both") and n.rect_a11y():
            want.append(("reading", n.rect_a11y(), "A11Y 读数"))
        if source in ("dumpsys", "both") and n.rect_dumpsys():
            want.append(("derived", n.rect_dumpsys(), "DUMPSYS 派生"))
        for kind, rect, tag in want:
            boxes.append((rect[0], rect[1], rect[2], rect[3],
                          f"{tag} | {n.label()}", kind))
            if kind == "derived":
                why = n.chain_overflow()
                if why:
                    warnings.append(f"{n.label()}：{why}")
    return boxes, warnings


def compare_focus(obj: dict) -> list:
    """a11y 焦点读数 vs dumpsys 派生坐标 —— 本脚本要给出的核心对照。

    判定只用**读数自身的算术**，不设容差、不套经验区间：

      * 中心是否严格重合 —— 中心是 ((l+r)/2,(t+b)/2)，比较 2 倍中心（`l+r`、`t+b`）
        即可避开浮点：整数相等与否，一步到位。
      * 是否等比 —— 比较 `dd_w/da_w` 与 `dd_h/da_h` 是否严格相等，用交叉相乘的
        **整数等式** `dd_w*da_h == dd_h*da_w`，不引入除法误差。

    两条同时成立才说「与以中心为基准的等比缩放一致」；否则逐条指出哪条不成立。

    为什么不用容差：真机 TV 设置页两面板布局下，焦点项的两个来源差值能到 1008 像素
    （横向滚动偏移），而它**同样同心**。只要容差稍宽（0.9~1.2 这类区间），
    这种偏移就会被判成「缩放动效一致」—— 恰好把要查的问题掩盖掉。
    """
    lines = []
    for n in flatten([Node(x) for x in obj.get("tree") or []]):
        if not n["focused"]:
            continue
        a, d = n.rect_a11y(), n.rect_dumpsys()
        if a and d:
            delta = tuple(d[i] - a[i] for i in range(4))
            lines.append(f"  焦点节点 {n.label()}")
            lines.append(f"    a11y 读数    [{a[0]},{a[1]}-{a[2]},{a[3]}]  "
                         f"尺寸 {a[2] - a[0]}×{a[3] - a[1]}  "
                         f"中心和(2 倍) {a[0] + a[2]},{a[1] + a[3]}")
            lines.append(f"    dumpsys 派生 [{d[0]},{d[1]}-{d[2]},{d[3]}]  "
                         f"尺寸 {d[2] - d[0]}×{d[3] - d[1]}  "
                         f"中心和(2 倍) {d[0] + d[2]},{d[1] + d[3]}")
            lines.append(f"    差值（派生−读数）{delta}")
            if all(v == 0 for v in delta):
                lines.append("    → 两个来源的读数完全相同（该焦点坐标被独立证实）")
            else:
                da_w, da_h = a[2] - a[0], a[3] - a[1]
                dd_w, dd_h = d[2] - d[0], d[3] - d[1]
                cs_same = (d[0] + d[2] == a[0] + a[2]) and (d[1] + d[3] == a[1] + a[3])
                if da_w > 0 and da_h > 0:
                    ratio_same = (dd_w * da_h == dd_h * da_w)
                else:
                    ratio_same = False
                if cs_same and ratio_same:
                    lines.append(f"    → 中心严格重合，两轴比例严格相等 "
                                 f"（{dd_w}/{da_w} = {dd_h}/{da_h}）："
                                 f"与以中心为基准的等比缩放一致，差值就是该缩放量")
                else:
                    why = []
                    if not cs_same:
                        why.append(f"中心不重合（中心和之差 "
                                   f"{d[0] + d[2] - (a[0] + a[2])},"
                                   f"{d[1] + d[3] - (a[1] + a[3])}，单位是像素的 2 倍）")
                    if not ratio_same:
                        if da_w > 0 and da_h > 0:
                            why.append(f"两轴比例不等（x {dd_w}/{da_w}={dd_w / da_w:.4f}，"
                                       f"y {dd_h}/{da_h}={dd_h / da_h:.4f}）")
                        else:
                            why.append("a11y 读数里有零边长的矩形，比例无从定义")
                    lines.append("    → 不是等比缩放能解释的：" + "；".join(why))
                    lines.append("      偏差最可能的来源在祖先链上（滚动偏移）。"
                                 "本工具**不改**读数、也不做补偿，"
                                 "见下面的溢出告警 —— 派生坐标在这种页面上不可信，"
                                 "以 a11y 读数为准")
            g = n["geom_check"]
            if g:
                lines.append(f"    geom_check = {g}")
        elif a:
            lines.append(f"  焦点节点 {n.label()}：只有 a11y 读数 "
                         f"[{a[0]},{a[1]}-{a[2]},{a[3]}]，没有配对的 dumpsys 节点可对照")
        else:
            lines.append(f"  焦点节点 {n.label()}：只有 dumpsys 派生坐标 "
                         f"[{d[0]},{d[1]}-{d[2]},{d[3]}]，没有 a11y 读数可对照")
    return lines


# ------------------------------------------------------------------ 截图与画图


def to_pixel(v: float) -> int:
    """换算后的坐标落到像素：四舍五入。

    不用 `int()` —— 截断是**单边偏小**的系统性偏差（每个坐标最多 1 px），
    而四舍五入是对称的，且这是栅格化的必然结果，不是对读数的修正。
    """
    return int(v + 0.5)


def scale_factors(img_w: int, img_h: int, screen: dict) -> tuple:
    """`截图像素 / 控件树坐标` 的**逐轴**换算系数；缺 wm size 时返回 (None, None)。

    控件树坐标基于 `wm size`（有 Override 时是 Override），截图是物理像素。
    这是本脚本唯一允许的坐标变换 —— 纯数学换算，两轴各算各的、都不藏起来。
    """
    sw = (screen or {}).get("width")
    sh = (screen or {}).get("height")
    sx = (img_w / float(sw)) if sw else None
    sy = (img_h / float(sh)) if sh else None
    return sx, sy
