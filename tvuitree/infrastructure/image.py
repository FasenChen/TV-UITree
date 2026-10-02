"""PNG capture and drawing backed by Pillow. 框 = 读数，逐像素对齐、不加偏移。"""

from __future__ import annotations

import io
import json
import os
import tempfile

from tvuitree.domain.screenshot import _px, _scale_factors

COLOR_READING = (255, 0, 0)
COLOR_DERIVED = (0, 90, 255)
DASH_ON = 8
DASH_OFF = 6
CROSS_ARM = 12


def focus_border_width(png_bytes: bytes) -> int:
    """Scale the MCP focus border with the PNG height (6 px at 1080p)."""
    if len(png_bytes) < 24 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n" or png_bytes[12:16] != b"IHDR":
        return 6
    height = int.from_bytes(png_bytes[20:24], "big")
    return max(1, round(height / 180))


def load_tree(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as source:
        obj = json.load(source)
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError(f"{path} 里没有 tree，不像是本工具输出的控件树 JSON。")
    return obj


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
               screen: dict, width: int = 1, show_details: bool = True) -> tuple:
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
        if show_details:
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


def draw_boxes_png(png_bytes: bytes, boxes: list, screen: dict,
                   width: int = 1, show_details: bool = True) -> tuple:
    """Draw using the shared renderer and return PNG bytes without a saved artifact."""
    with tempfile.TemporaryDirectory(prefix="tv-uitree-focus-") as directory:
        path = os.path.join(directory, "focus.png")
        drawn, skipped, notes = draw_boxes(
            png_bytes, boxes, path, screen, width, show_details=show_details,
        )
        with open(path, "rb") as image_file:
            return image_file.read(), drawn, skipped, notes


def capture(adb) -> bytes:
    data = adb.exec_out(["screencap", "-p"], timeout=60)
    if not data or not data.startswith(b"\x89PNG"):
        raise ValueError("screencap 没有返回 PNG，无法截图（设备可能已锁屏或不允许抓屏）")
    return data
