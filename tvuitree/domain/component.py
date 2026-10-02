"""Pure Android component normalization."""

from __future__ import annotations

import re
from typing import Optional

def component_from_window(text: Optional[str]) -> Optional[str]:
    """`Window{... u0 com.pkg/.Cls}` → `com.pkg/.Cls`"""
    if not text:
        return None
    m = re.search(r"\s([A-Za-z][\w.]*)/([\w.$]+)\}", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"([A-Za-z][\w.]*)/([\w.$]+)", text)
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
