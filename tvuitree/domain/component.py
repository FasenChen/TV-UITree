"""Pure Android component normalization."""

from __future__ import annotations

import re
from typing import Optional

# 系统包 android 合法；类名每段以标识符字符开头，不能是 UID 数字。
_WINDOW_COMPONENT = (r"([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)/"
                     r"(\.?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")


def component_from_window(text: Optional[str]) -> Optional[str]:
    """解析窗口组件，保留系统包并排除 UID 等非类名字段。"""
    if not text:
        return None
    match = re.search(r"\s" + _WINDOW_COMPONENT + r"\}", text)
    if not match:
        match = re.search(r"(?<![\w.$/])" + _WINDOW_COMPONENT + r"(?![\w.$/])", text)
    return f"{match.group(1)}/{match.group(2)}" if match else None


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
