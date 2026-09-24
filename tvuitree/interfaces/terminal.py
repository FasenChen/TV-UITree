"""Terminal formatting and diagnostics for command line interfaces."""

from __future__ import annotations

import os
import sys

class C:
    """终端着色。非 tty 或 --no-color 时整体关掉。"""

    _on = True
    R = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
    RED = "\033[31m"; GRN = "\033[32m"; YEL = "\033[33m"
    BLU = "\033[34m"; MAG = "\033[35m"; CYA = "\033[36m"; GRY = "\033[90m"

    @classmethod
    def off(cls):
        cls._on = False
        for name in ("R", "B", "DIM", "RED", "GRN", "YEL", "BLU", "MAG", "CYA", "GRY"):
            setattr(cls, name, "")


def c(text: str, color: str) -> str:
    return f"{color}{text}{C.R}" if C._on else text


def setup_console(no_color: bool = False) -> None:
    """Windows 控制台兼容 + 着色开关。

    编码这条是实测踩过的坑：本机 stdout 可能是 cp936 或 ascii。cp936 能显示中文
    就保留（切 UTF-8 反而会让重定向出来的文件乱码），只有编码根本无法表示中文
    （None/ascii）时才切到 UTF-8。
    """
    if no_color or os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        C.off()
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", None) or "").lower()
            if enc in ("", "ascii", "us-ascii", "ansi_x3.4-1968"):
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
        except Exception:
            pass
