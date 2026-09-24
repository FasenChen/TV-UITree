"""Read one TV state snapshot from external device interfaces."""

from __future__ import annotations

import logging
import os
from typing import Optional

from .adb import Adb, AdbError
from .uiautomator import fetch_u2
from tvuitree.domain.tree.capture import hierarchy_drift
from tvuitree.domain.tree.parsing import parse_dumpsys_top, pick_block_ex

def snapshot(adb: Adb, serial: Optional[str], save_raw: Optional[str],
             quiet: bool, use_dumpsys: bool = True,
             anomalies: Optional[list] = None) -> dict:
    """同一时刻抓两棵树（先 dumpsys 后 a11y，间隔最小化并记录前后一致性）。"""
    dev = {}
    try:
        dev = adb.props()
    except AdbError:
        pass
    screen = adb.screen()
    win = adb.window_focus()

    top1 = top2 = ""
    blocks, blk, note, drift, drift_detail = [], None, None, False, None
    if use_dumpsys:
        top1 = adb.exec_out(["dumpsys", "activity", "top"]).decode("utf-8", "replace")
    xml, u2_meta = fetch_u2(serial, quiet=quiet)
    if use_dumpsys:
        top2 = adb.exec_out(["dumpsys", "activity", "top"]).decode("utf-8", "replace")
        drift, drift_detail = hierarchy_drift(top1, top2)
        blocks = parse_dumpsys_top(top2, anomalies)
        blk, note = pick_block_ex(blocks, win.get("component"))
        if blk is None:
            note = "dump 里没有可用的 ACTIVITY 段"
        if note and not quiet:
            logging.info("[段匹配] %s", note)

    pkg = blk.component.split("/")[0] if blk else None

    if save_raw:
        os.makedirs(save_raw, exist_ok=True)
        pairs = [("u2_hierarchy.xml", xml)]
        if use_dumpsys:
            pairs += [("activity_top_before.txt", top1), ("activity_top_after.txt", top2)]
        for name, text in pairs:
            with open(os.path.join(save_raw, name), "w", encoding="utf-8") as f:
                f.write(text)

    return {"dev": dev, "screen": screen, "win": win, "xml": xml, "u2_meta": u2_meta,
            "blocks": blocks, "block": blk, "pkg": pkg, "pick_note": note,
            "drift": drift, "drift_detail": drift_detail}
