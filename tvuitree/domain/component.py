"""Pure Android component normalization."""

from __future__ import annotations

import re
from typing import Optional

def component_from_window(text: Optional[str]) -> Optional[str]:
    """`Window{... u0 com.pkg/.Cls}` → `com.pkg/.Cls`

    包名组要求至少含一个点号：真机 component 的包名恒为反向域名，
    而 `uid/1000` 这类窗口字段没有点号。不收紧就会把 `uid/1000` 当成
    前台 component，进而让 pick_block 回退到最后一个 ACTIVITY 段——
    那可能是另一个页面的树。
    """
    if not text:
        return None
    m = re.search(r"\s([A-Za-z][\w]*(?:\.[\w]+)+)/([\w.$]+)\}", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"\b([A-Za-z][\w]*(?:\.[\w]+)+)/([\w.$]+)", text)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def component_from_activity_record(text: Optional[str]) -> Optional[str]:
    """`ActivityRecord{... u0 com.pkg/.Cls t42}` → `com.pkg/.Cls`"""
    if not text:
        return None
    m = re.search(r"\s([A-Za-z][\w.]*)/([\w.$]+)\s", text + " ")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def normalize_component(comp: Optional[str]) -> Optional[tuple]:
    """`com.pkg/.Cls` → `("com.pkg", "com.pkg.Cls")`；不合法返回 None。"""
    if not comp or "/" not in comp:
        return None
    pkg, cls = comp.split("/", 1)
    if cls.startswith("."):
        cls = pkg + cls
    return (pkg, cls)
