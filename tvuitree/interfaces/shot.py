"""Screenshot command presentation."""

from __future__ import annotations

import argparse
import sys

from tvuitree.infrastructure.adb import AdbError
from .connection import connect_for_cli
from .terminal import C, c


def run_shot(args: argparse.Namespace) -> int:
    import datetime as dt

    from tvuitree.application.screenshot import render
    from .json_io import _load_full
    from tvuitree.infrastructure.image import capture

    try:
        obj = _load_full(args.json_path)
    except (OSError, ValueError, TypeError) as error:
        print(c(str(error), C.RED), file=sys.stderr)
        return 1
    captured_at = obj.get("captured_at")
    if captured_at:
        try:
            age = (dt.datetime.now() - dt.datetime.fromisoformat(captured_at)).total_seconds()
            if age > 60:
                print(c(f"[警告] 这份 JSON 是 {captured_at} 抓的（{int(age)} 秒前）。"
                        "截图是现在拍的，画面可能已经变了 —— 框对不上不一定是坐标错。",
                        C.YEL), file=sys.stderr)
        except ValueError:
            pass
    if args.image:
        try:
            with open(args.image, "rb") as source:
                png = source.read()
        except OSError as error:
            print(c(str(error), C.RED), file=sys.stderr)
            return 1
        if not args.quiet:
            print(c(f"[img] 用已有截图 {args.image}", C.GRY), file=sys.stderr)
    else:
        device = connect_for_cli(args)
        if device is None:
            return 2
        try:
            png = capture(device)
        except (AdbError, ValueError) as error:
            print(c(str(error), C.RED), file=sys.stderr)
            return 1
    result = render(obj, png, args.out, draw=args.draw, source=args.source, width=args.width)
    boxes, warnings = result["boxes"], result["warnings"]
    drawn, skipped, notes = result["drawn"], result["skipped"], result["notes"]
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
    for note in notes[:20]:
        print(c(f"  {note}", C.GRY))
    if len(notes) > 20:
        print(c(f"  …… 另有 {len(notes) - 20} 条同类提示（内容同上，不再逐条列出）", C.GRY))
    if args.draw == "focus":
        if result["focus_lines"]:
            print("\n焦点坐标对照（a11y 读数 vs dumpsys 派生）：")
            print("\n".join(result["focus_lines"]))
        else:
            print(c("  这份 JSON 里没有 focused 节点，没什么可对照的。", C.YEL))
    if warnings:
        print(c(f"\n[告警] {len(warnings)} 个派生坐标的祖先链上存在溢出容器"
                "（滚动偏移就藏在那儿，而 dump 不含 scrollX/scrollY）：", C.YEL))
        for warning in warnings[:6]:
            print(c(f"  {warning}", C.YEL))
    if not drawn and not boxes:
        print(c("  没有可画的框：检查 --draw/--source，或确认那份 JSON 里有焦点节点。",
                C.YEL))
    return 0
