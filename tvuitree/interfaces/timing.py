"""Per-call timing diagnostics for MCP tools.

每次工具调用向 stderr 写一段耗时（首行总计，每个阶段一行）；
stdout 留给 MCP 协议，工具返回内容不变。
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

    def summary(self) -> str:
        """首行给时间、工具名和总耗时；每个阶段一行，毫秒和占比右对齐。"""
        total_ms = (perf_counter() - self._start) * 1000
        header = (f"[tv-uitree] {self.started_at:%H:%M:%S}.{self.started_at.microsecond // 1000:03d}"
                  f" {self.tool}  total {total_ms:.1f} ms")
        if self.failed is not None:
            header += f"  failed at {self.failed}"
        name_width = max([12] + [len(name) for name, _ms in self.stages])
        lines = [header]
        for name, ms in self.stages:
            share = ms / total_ms * 100 if total_ms > 0 else 0.0
            lines.append(f"  {name:<{name_width}} {ms:>8.1f} ms {share:>6.1f}%")
        return "\n".join(lines)


@contextlib.contextmanager
def tool_timing(tool: str) -> Iterator[ToolTimer]:
    """包住一次工具调用；无论正常返回、提前返回还是异常，都恰好写一段。"""
    timer = ToolTimer(tool)
    try:
        yield timer
    finally:
        _emit(timer.summary())


def _emit(block: str) -> None:
    stream = LOG_STREAM if LOG_STREAM is not None else sys.stderr
    try:
        # 一次 write 写完整段，减少与其他 stderr 输出交错
        stream.write(block + "\n")
        stream.flush()
    except (OSError, ValueError, AttributeError):
        pass  # 诊断日志不可写时不能拖垮工具调用
