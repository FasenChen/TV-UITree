#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tv_shot.py — 截图 + 在图上画框（验证辅助脚本，**不属于本项目的核心功能**）

它回答一个问题：**tv_tree.py 解析出来的坐标，画到真实截图上，落在哪里？**

典型用法：先用 tv_tree.py 抓一份控件树，再用本脚本截图并把焦点框画上去，
肉眼核对「树里说的焦点位置」与「画面上实际的焦点」是不是一回事。

两种坐标来源，必须分得清（这是本脚本的核心价值）
------------------------------------------------
  --source a11y     用 `bounds_screen`：a11y 的**读数**，屏幕上真实可见的矩形。红框。
  --source dumpsys  用 `dumpsys.bounds_abs_unclipped`：**派生值**，沿祖先链累加出来的。
                    前提是祖先链上没有滚动偏移，而 dump 不含 scrollX/scrollY、
                    这个前提无法从数据里验证。蓝框。
                    ⇒ 拿它和 a11y 读数一比，偏差在哪儿、有多大，一眼就能看出来。
  --source both     两种都画（红=读数，蓝=派生），直接对照。

为什么不像主脚本那样「拒绝画」而只给告警
----------------------------------------
主脚本面对「祖先链上有溢出容器」时会拒绝用派生坐标画框，因为那种框会落在屏幕内但
**错误的控件**上，比明显越界更危险。但本脚本的用途**就是**验证，把可疑的框藏起来
反而没用 —— 所以这里照画，同时把「为什么可疑」打成告警，并在图上用虚线框区分。

画框的几何约定（本脚本的立身之本，不可违反）
--------------------------------------------
本脚本是**验证工具**：它的价值在于把「控件树算出来的位置」与「画面上的实际位置」
的差异原样摆在眼前。任何让框「看起来更贴合焦点」的修饰都是在擦掉要验证的东西。
因此：

  1. **框的几何 = 坐标读数本身，逐像素对齐。** 不做偏移、不做容差、不做
     「为了看清而向外挪几像素」这类修饰。要加粗就把线带**以坐标为中线的对称**
     展开（`--width`），中线永不离开读数。
  2. **唯一允许的变换是分辨率换算。** 控件树坐标基于 `wm size`，截图是物理像素；
     `截图 px / 坐标 px` 逐轴各算一个系数并**报出来**。两轴系数不等（宽高比不一致）
     时已不是相似变换，必须点明「画出的框与读数的对应关系不成立」，不许按单轴凑。
  3. **两个来源只靠样式区分**：读数=红实线，派生=蓝虚线。绝不靠几何偏移区分 ——
     那会把真实的差值伪装成样式差异。
  4. **画不出来的照实说，并且分得清性质**：三种情况分开报 ——
     **零面积**（读数自身没有面积，与越界是两回事）／**真越界**（读数超出画面，逐条报
     原读数与裁后坐标）／**压屏幕外沿**（右/下边界等于屏幕宽高，是像素栅格的半开区间
     约定，只给总数）。**「画不出来」本身是信息，不是要抹平的噪声。**
  5. **说明文字的位置只为可读**（画在框上方），不参与任何坐标计算；判定「框落在哪」
     只看框线，不看文字。
  6. 判定偏差成因时**只用读数的算术**：中心是否严格重合、两轴比例是否严格相等，
     用整数等式精确判定，不设「0.9~1.2 就算缩放」这类经验区间。
     → 否则会把滚动偏移误报成缩放动效，正好掩盖要查的问题。

依赖：`pip install pillow`（没有则只保存截图，不画框，并说明）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import sys

from tv_adb import C, add_conn_args, c, connect_device, setup_console

# 读数来源 = 实线红；派生来源 = 虚线蓝。两个来源**只靠样式区分，不靠几何偏移**。
COLOR_READING = (255, 0, 0)
COLOR_DERIVED = (0, 90, 255)

DASH_ON = 8      # 虚线段长（像素）—— 只影响线的样式，不改变线的位置
DASH_OFF = 6     # 虚线间隙（像素）
CROSS_ARM = 12   # 中心十字的臂长（像素）—— 只影响标记可见度，不参与坐标计算


# ------------------------------------------------------------------ 读 JSON 与取矩形


def load_tree(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        raise SystemExit(f"读不了 {path}：{type(e).__name__}: {e}")
    if not isinstance(obj.get("tree"), list):
        raise SystemExit(f"{path} 里没有 tree，不像是 tv_tree.py 输出的控件树 JSON。")
    return obj


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


def _px(v: float) -> int:
    """换算后的坐标落到像素：四舍五入。

    不用 `int()` —— 截断是**单边偏小**的系统性偏差（每个坐标最多 1 px），
    而四舍五入是对称的，且这是栅格化的必然结果，不是对读数的修正。
    """
    return int(v + 0.5)


def _scale_factors(img_w: int, img_h: int, screen: dict) -> tuple:
    """`截图像素 / 控件树坐标` 的**逐轴**换算系数；缺 wm size 时返回 (None, None)。

    控件树坐标基于 `wm size`（有 Override 时是 Override），截图是物理像素。
    这是本脚本唯一允许的坐标变换 —— 纯数学换算，两轴各算各的、都不藏起来。
    """
    sw = (screen or {}).get("width")
    sh = (screen or {}).get("height")
    sx = (img_w / float(sw)) if sw else None
    sy = (img_h / float(sh)) if sh else None
    return sx, sy


def _band(dr, x0: int, y0: int, x1: int, y1: int, color, dashed: bool):
    """画一条像素带。dashed 只改变样式，不改变位置。"""
    if x1 < x0 or y1 < y0:
        return
    if not dashed:
        dr.rectangle([x0, y0, x1, y1], fill=color)
        return
    if (x1 - x0) >= (y1 - y0):
        x = x0
        while x <= x1:
            dr.rectangle([x, y0, min(x + DASH_ON - 1, x1), y1], fill=color)
            x += DASH_ON + DASH_OFF
    else:
        y = y0
        while y <= y1:
            dr.rectangle([x0, y, x1, min(y + DASH_ON - 1, y1)], fill=color)
            y += DASH_ON + DASH_OFF


def _stroke_rect(dr, rect: tuple, color, width: int, dashed: bool):
    """按读数坐标画矩形。

    width=1：线所占据的像素**就是**坐标所指的那一行/列 —— 零歧义，
    框的外沿再外面一个像素必须是干净的。
    width>1：线带以坐标为中线的**对称**展开（向内外各扩 (w-1)//2、w//2），
    中线严格落在读数上，绝不单边外扩。
    """
    l, t, r, b = rect
    w = max(1, int(width))
    lo, hi = (w - 1) // 2, w // 2
    _band(dr, l - lo, t - lo, r + hi, t + hi, color, dashed)   # 上边
    _band(dr, l - lo, b - lo, r + hi, b + hi, color, dashed)   # 下边
    _band(dr, l - lo, t - lo, l + hi, b + hi, color, dashed)   # 左边
    _band(dr, r - lo, t - lo, r + hi, b + hi, color, dashed)   # 右边


def _cross(dr, rect: tuple, color):
    """标出矩形几何中心，供肉眼判断两个框是否同心。

    中心是 ((l+r)/2, (t+b)/2)。跨度为奇数时几何中心落在**两个像素之间**，
    此时两个中央像素都画（对称展开）—— 单边取整会让十字偏 0.5 像素，
    而「是否同心」恰恰是要靠它看的。
    """
    l, t, r, b = rect
    cx2, cy2 = l + r, t + b                       # 2 倍中心，整数，精确
    x0, x1 = cx2 // 2 - CROSS_ARM, cx2 - cx2 // 2 + CROSS_ARM
    y0, y1 = cy2 // 2 - CROSS_ARM, cy2 - cy2 // 2 + CROSS_ARM
    _band(dr, x0, cy2 // 2, x1, cy2 - cy2 // 2, color, False)
    _band(dr, cx2 // 2, y0, cx2 - cx2 // 2, y1, color, False)


def draw_boxes(png_bytes: bytes, boxes: list, out_path: str,
               screen: dict, width: int = 1) -> tuple:
    """在截图上画框。返回 (画出数, 未画出数, 提示列表)。

    几何约定见模块文档：**框 = 读数，逐像素对齐**；只用分辨率换算，无偏移、无容差。
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        with open(out_path, "wb") as f:
            f.write(png_bytes)
        return 0, len(boxes), ["未安装 Pillow，只保存了原始截图（画框需 pip install pillow）"]

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    dr = ImageDraw.Draw(img)
    notes = []

    sw = (screen or {}).get("width")
    sh = (screen or {}).get("height")
    sx, sy = _scale_factors(img.width, img.height, screen)
    if sx is None or sy is None:
        notes.append(f"JSON 里没有 wm size（width/height），无法核对截图 "
                     f"{img.width}×{img.height} 与控件树坐标的像素对应关系，"
                     f"框按坐标原值绘制")
        sx = sy = 1.0
    else:
        if sx != 1.0 or sy != 1.0:
            notes.append(f"截图 {img.width}×{img.height} 与 wm size {sw}×{sh} 不等："
                         f"框按 x×{sx:.6f}、y×{sy:.6f} 换算后绘制"
                         f"（是坐标换算，不是修正；落像素时四舍五入，单点误差 ≤0.5 像素）")
        if sx != sy:
            notes.append(f"[!] 两轴换算系数不相等（x×{sx:.6f} ≠ y×{sy:.6f}）："
                         f"截图与坐标的宽高比不一致，这已不是相似变换，"
                         f"画出的框与读数的对应关系**不成立** —— "
                         f"先把截图分辨率与 wm size 对齐，再谈验证")
    if width > 1:
        notes.append(f"线宽 {width} 像素：线带以读数坐标为中线对称展开"
                     f"（中线仍是读数，未被加粗推移）")

    drawn = skipped = 0
    edge_only = 0          # 读数边界正好落在截图外沿（半开区间约定，不是越界）
    for l, t, r, b, label, kind in boxes:
        fl, ft, fr, fb = l * sx, t * sy, r * sx, b * sy
        # 零面积：读数本身就没有面积，任何像素都画不出来。
        # 这与「越界」是两回事，不能混成一句「落在画面外」。
        if fr <= fl or fb <= ft:
            notes.append(f"框零面积，没有可画的像素（读数自身如此，不是画框的问题）："
                         f"{label}｜读数 [{l},{t}-{r},{b}]")
            skipped += 1
            continue
        if fr <= 0 or fl >= img.width or fb <= 0 or ft >= img.height:
            notes.append(f"框完全落在画面外，未绘制：{label}｜读数 [{l},{t}-{r},{b}]"
                         f" → 换算后 [{fl:g},{ft:g}-{fr:g},{fb:g}]")
            skipped += 1
            continue
        cl, ct = max(0.0, fl), max(0.0, ft)
        cr, cb = min(img.width - 1.0, fr), min(img.height - 1.0, fb)
        if (cl, ct, cr, cb) != (fl, ft, fr, fb):
            # 再分一层：读数是**真的越出画面**，还是仅仅压在截图外沿？
            # 后者（右边=屏宽、下边=屏高）是像素栅格的半开区间约定，
            # 与「读数越界」性质不同，不能混在一起报警 —— 但也不能不说，
            # 所以逐条报「真越界」，压外沿的只给总数。
            if fl < 0 or ft < 0 or fr > img.width or fb > img.height:
                notes.append(f"框有部分越出画面，裁到边界后绘制：{label}"
                             f"｜读数 [{l},{t}-{r},{b}] → 换算后 [{fl:g},{ft:g}-{fr:g},{fb:g}]"
                             f" → 实际画 [{_px(cl)},{_px(ct)}-{_px(cr)},{_px(cb)}]"
                             f"（越出的像素画不出来，读数没变）")
            else:
                edge_only += 1
        rect = (_px(cl), _px(ct), _px(cr), _px(cb))
        color = COLOR_READING if kind == "reading" else COLOR_DERIVED
        _stroke_rect(dr, rect, color, width, dashed=(kind != "reading"))
        _cross(dr, rect, color)
        try:
            dr.text((rect[0] + 2, max(0, rect[1] - 13)), label, fill=color)
        except Exception:
            pass
        drawn += 1
    if edge_only:
        # 汇总行放最前：per-box 提示可能很多、会被截断，这条不能被挤掉
        notes.insert(0, f"另有 {edge_only} 个框的读数边界正好压在截图外沿"
                        f"（{img.width}×{img.height}）：右/下边界等于画面宽/高时，"
                        f"末像素落在 {img.width - 1}/{img.height - 1}，"
                        f"画出的框在那两条边上比读数少 1 像素 —— "
                        f"这是像素栅格的半开区间约定，不是读数越界，故只给总数")
    img.save(out_path)
    return drawn, skipped, notes


def capture(adb) -> bytes:
    data = adb.exec_out(["screencap", "-p"], timeout=60)
    if not data or not data.startswith(b"\x89PNG"):
        raise SystemExit("screencap 没有返回 PNG，无法截图（设备可能已锁屏或不允许抓屏）")
    return data


# ------------------------------------------------------------------ CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tv_shot.py",
        description="截图 + 按控件树 JSON 画框（验证辅助）。主脚本不负责截图，本脚本不负责取树。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""典型流程：
  python tv_tree.py --out full.json
  python tv_shot.py --json full.json --out shot.png
  python tv_shot.py --json full.json --source both --out shot_both.png
""")
    add_conn_args(p)
    p.add_argument("--json", dest="json_path", required=True, metavar="FILE",
                   help="tv_tree.py 输出的控件树 JSON（画框的坐标来源）")
    p.add_argument("--out", default="shot.png", metavar="FILE",
                   help="截图输出路径（默认 shot.png）")
    p.add_argument("--image", default=None, metavar="FILE",
                   help="用已有的 PNG 代替现拍截图（离线核对用）")
    p.add_argument("--source", choices=["a11y", "dumpsys", "both"], default="a11y",
                   help="画哪个坐标：a11y=a11y 屏幕读数（红实线，默认）；"
                        "dumpsys=沿祖先累加的派生值（蓝虚线）；both=两个都画")
    p.add_argument("--draw", choices=["focus", "actionable", "all"], default="focus",
                   help="画哪些节点：focus=焦点节点（默认）；actionable=可点击/可聚焦节点；"
                        "all=所有有矩形的节点")
    p.add_argument("--width", type=int, default=1, metavar="N",
                   help="框线宽度（像素，默认 1）。1=线所占像素就是读数所指的行/列，零歧义；"
                        "N>1 时线带以读数为中线对称展开，中线不离开读数。"
                        "**不要**用加宽去「贴近」焦点，那会挡住要看的差值")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    setup_console(args.no_color)

    obj = load_tree(args.json_path)
    screen = obj.get("screen") or {}

    # 截图与取树不在同一时刻 → 说清楚，别让人误以为两者必然对齐
    cap_at = obj.get("captured_at")
    if cap_at:
        try:
            age = (_dt.datetime.now() - _dt.datetime.fromisoformat(cap_at)).total_seconds()
            if age > 60:
                print(c(f"[警告] 这份 JSON 是 {cap_at} 抓的（{int(age)} 秒前）。"
                        f"截图是现在拍的，画面可能已经变了 —— 框对不上不一定是坐标错。",
                        C.YEL), file=sys.stderr)
        except ValueError:
            pass

    if args.image:
        with open(args.image, "rb") as f:
            png = f.read()
        if not args.quiet:
            print(c(f"[img] 用已有截图 {args.image}", C.GRY), file=sys.stderr)
    else:
        adb = connect_device(args)
        if adb is None:
            return 2
        png = capture(adb)

    boxes, warnings = collect(obj, args.draw, args.source)
    drawn, skipped, notes = draw_boxes(png, boxes, args.out, screen, args.width)

    if not args.quiet:
        print(c("画框约定：框的几何 = 读数坐标逐像素对齐；只做分辨率换算（逐轴、如实报出），"
                "不加偏移、不做容差；读数=红实线，派生=蓝虚线（用样式区分，不用偏移区分）；"
                f"线宽 {args.width} 像素"
                + ("（以坐标为中线的对称线带）" if args.width > 1
                   else "（线所占像素即坐标所在的行/列）")
                + "；画不出来的分三类如实报：" 
                  "零面积 / 真越界（逐条） / 压屏幕外沿（汇总，半开区间约定）；"
                  "说明文字的位置只为可读，不含几何含义。", C.GRY))
    print(c(f"[out] {args.out}：{args.draw} × {args.source}，{len(boxes)} 个框，"
            f"画出 {drawn} 个"
            + (f"，未画出 {skipped} 个（零面积或完全在画面外，逐条见下）" if skipped
               else ""), C.GRY))
    for n in notes[:20]:
        print(c(f"  {n}", C.GRY))
    if len(notes) > 20:
        print(c(f"  …… 另有 {len(notes) - 20} 条同类提示（内容同上，不再逐条列出）", C.GRY))

    if args.draw == "focus":
        lines = compare_focus(obj)
        if lines:
            print("\n焦点坐标对照（a11y 读数 vs dumpsys 派生）：")
            print("\n".join(lines))
        else:
            print(c("  这份 JSON 里没有 focused 节点，没什么可对照的。", C.YEL))

    if warnings:
        print(c(f"\n[告警] {len(warnings)} 个派生坐标的祖先链上存在溢出容器"
                f"（滚动偏移就藏在那儿，而 dump 不含 scrollX/scrollY）：", C.YEL))
        for w in warnings[:6]:
            print(c(f"  {w}", C.YEL))
    if not drawn and not boxes:
        print(c("  没有可画的框：检查 --draw/--source，或确认那份 JSON 里有焦点节点。",
                C.YEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
