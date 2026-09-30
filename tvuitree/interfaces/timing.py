"""Per-call timing diagnostics for MCP tools.

每次工具调用向 stderr 写一行耗时；stdout 留给 MCP 协议，工具返回内容不变。
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sys
from time import perf_counter
from typing import Iterator, Optional, TextIO

# None 表示写入时再取 sys.stderr，便于测试替换或重定向。
LOG_STREAM: Optional[TextIO] = None


class ToolTimer:
    """记录一次工具调用的起点和各阶段耗时。"""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.started_at = dt.datetime.now()
        self._start = perf_counter()
        self.stages: list[tuple[str, float]] = []
        self.failed: Optional[str] = None

    @contextlib.contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """计一个阶段的毫秒数；阶段内的异常照常抛出，只记下第一个失败阶段。"""
        start = perf_counter()
        try:
            yield
        except Exception:
            if self.failed is None:
                self.failed = name
            raise
        finally:
            self.stages.append((name, (perf_counter() - start) * 1000))

    def summary_line(self) -> str:
        total_ms = (perf_counter() - self._start) * 1000
        parts = [
            "[tv-uitree]",
            self.started_at.isoformat(timespec="milliseconds"),
            self.tool,
            f"total={total_ms:.1f}ms",
        ]
        parts += [f"{name}={ms:.1f}ms" for name, ms in self.stages]
        if self.failed is not None:
            parts.append(f"failed={self.failed}")
        return " ".join(parts)


@contextlib.contextmanager
def tool_timing(tool: str) -> Iterator[ToolTimer]:
    """包住一次工具调用；无论正常返回、提前返回还是异常，都恰好写一行。"""
    timer = ToolTimer(tool)
    try:
        yield timer
    finally:
        _emit(timer.summary_line())


def _emit(line: str) -> None:
    stream = LOG_STREAM if LOG_STREAM is not None else sys.stderr
    try:
        stream.write(line + "\n")
        stream.flush()
    except (OSError, ValueError, AttributeError):
        pass  # 诊断日志不可写时不能拖垮工具调用
