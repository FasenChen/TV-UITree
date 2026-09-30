# MCP 工具耗时日志 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每次调用 MCP 工具时，向 stderr 写一行日志，记录从进入工具到返回结果的总耗时和分阶段耗时（连接 / 树采集 / 摘要 / 截图 / 标注 / 编码 / 保存）。

**Architecture:** 新增 `tvuitree/interfaces/timing.py`，提供 `tool_timing(name)` 上下文管理器和 `ToolTimer.stage(name)` 子上下文。`tvuitree/interfaces/mcp.py` 的五个工具用它包住函数体，并在各阶段外包一层 `stage`。日志只写 stderr，工具的返回内容、输入 schema 和 CLI 行为都不变。计时用 `time.perf_counter`，时间戳用本地时间。

**Tech Stack:** Python 3.10+ 标准库（`contextlib`、`time`、`datetime`、`sys`）；`mcp` 1.30 FastMCP（已安装，不新增依赖）；离线自检 `tests/selftest_tree.py`（普通脚本，不是 pytest）。

**Spec:** 没有单独的 spec 文件。需求来自 2026-09-29 的对话：用户要拿到“从 tool 调用到返回结果的时间”，选定“只写 stderr 日志”和“总耗时加分阶段”。

## Global Constraints

- 不改变任何 MCP 工具的名字、输入 schema 或返回内容（不加 timing 字段）。
- `main.py mcp` 的 stdout 只承载 MCP 协议；耗时日志只能写 stderr（AGENTS.md 已有此规则）。
- 每次工具调用恰好写一行日志，包括提前返回和异常路径。
- 日志写入失败（stderr 已关闭等）不能影响工具结果。
- 不新增第三方依赖；domain 层不改；CLI 不输出耗时。
- Python 3.10+、四空格缩进、UTF-8、新代码带类型注解。
- 日志行格式固定为：`[tv-uitree] <本地时间 ISO 毫秒> <工具名> total=<x.x>ms <阶段>=<x.x>ms ... [failed=<阶段>]`
- 阶段名固定为：`connect`、`capture_tree`、`summarize`、`screenshot`、`mark`、`encode`、`save`。

## Review Focus

- 日志误写到 stdout，会破坏 stdio 协议，Inspector 或宿主直接断连。期望：只写 stderr（Task 1 测试）。
- stderr 不可写（宿主关闭管道、流已关闭）时，写日志抛异常，工具调用失败。期望：吞掉写入错误，结果照常返回（Task 1 测试）。
- 提前返回路径（`get_focus_screenshot` 连接失败返回 `[status]`）没写日志，用户看不到这次调用。期望：仍写一行，只含 `connect`（Task 2 测试）。
- 阶段内抛出的异常被工具自身的 `except` 吞掉后，日志看起来像成功。期望：行尾带 `failed=<阶段>`（Task 2 测试：截图失败、采集失败）。
- 埋点改变了工具的 schema、返回键集合或 CLI 与 MCP 的一致性。期望：完全不变。第 8 节已有的 schema、键集合和 CLI==MCP 断言必须继续通过，不许修改（Task 2）。

`total` 的范围：从工具函数开始到返回为止，不含 FastMCP 把结果转成 JSON、Base64 编码 MCP 图片内容以及 stdio 传输的时间。README 里要写明这一点（Task 3）。

---

## File Structure

- Create: `tvuitree/interfaces/timing.py`：计时器和 stderr 输出，唯一职责是生成并写出耗时行。
- Modify: `tvuitree/interfaces/mcp.py:162-324`：五个工具加埋点。`observe_tv` 和 `get_visible` 拆成“采集 + 摘要”两步调用应用层，结果与原来等价。
- Modify: `tests/selftest_tree.py`：顶部 import；第 8 节加埋点断言；新增第 9 节测试计时器本身。
- Modify: `README.md:209` 之后，`AGENTS.md:15` 和 `AGENTS.md:37`：文档。

检查命令（Git Bash，在仓库根目录执行）：

```bash
PY=.venv/Scripts/python.exe
FILES="main.py $(find tvuitree tests -name '*.py')"
$PY -m py_compile $FILES && $PY -m pyflakes $FILES && $PY tests/selftest_tree.py && git diff --check
```

---

### Task 1: 计时模块 `timing.py`

**Files:**
- Create: `tvuitree/interfaces/timing.py`
- Test: `tests/selftest_tree.py`（顶部 import，新增第 9 节，放在第 8 节 `finally` 之后、`# ==== 收尾` 之前）

**Interfaces:**
- Consumes: 无
- Produces:
  - `timing.LOG_STREAM: Optional[TextIO]`：`None` 表示写入时再取 `sys.stderr`；测试可替换。
  - `timing.perf_counter`：模块级名字，测试可替换为假时钟。
  - `timing.tool_timing(tool: str) -> ContextManager[ToolTimer]`：退出时（含异常）写一行。
  - `ToolTimer.stage(name: str) -> ContextManager[None]`：记录该阶段毫秒数；阶段内抛异常时记 `failed`（只记第一个），并继续抛出。

- [ ] **Step 1: 加 import**

`tests/selftest_tree.py` 顶部，在 `import os` 后加一行：

```python
import re
```

并把第 59-60 行的 interfaces import 改成：

```python
from tvuitree.interfaces import (cli, connection, terminal, timing, observe as observe_interface,
                                tree as tree_interface, visible as visible_interface)
```

- [ ] **Step 2: 写失败的测试（第 9 节）**

插在第 8 节 `finally:` 块结束之后、`# ================================================================== 收尾` 之前：

```python
# ================================================================== 9. MCP 工具耗时日志

t.group("9. MCP 工具耗时日志")

_original_perf_counter = timing.perf_counter
_original_timing_stream = timing.LOG_STREAM
try:
    # 调用顺序：计时器创建、connect 起止、capture_tree 起止、总计结束
    _ticks = iter([10.0, 10.5, 11.0, 11.0, 11.25, 12.0])
    timing.perf_counter = lambda: next(_ticks)
    timing.LOG_STREAM = io.StringIO()
    with timing.tool_timing("demo_tool") as timer:
        with timer.stage("connect"):
            pass
        with timer.stage("capture_tree"):
            pass
    line = timing.LOG_STREAM.getvalue()
    t.ok(re.fullmatch(r"\[tv-uitree\] \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3} demo_tool "
                      r"total=2000\.0ms connect=500\.0ms capture_tree=250\.0ms\n", line),
         "耗时日志一行给出起始时间、工具名、总耗时和各阶段毫秒数", repr(line))

    _ticks = iter([0.0, 0.0, 0.1, 0.3])
    timing.LOG_STREAM = io.StringIO()
    escaped = False
    try:
        with timing.tool_timing("demo_tool") as timer:
            with timer.stage("screenshot"):
                raise ValueError("fixture")
    except ValueError:
        escaped = True
    line = timing.LOG_STREAM.getvalue()
    t.ok(escaped, "阶段异常不被计时器吞掉")
    t.ok(line.endswith(" demo_tool total=300.0ms screenshot=100.0ms failed=screenshot\n"),
         "异常穿出工具时仍写日志，并标出失败阶段", repr(line))

    class _BrokenStream:
        def write(self, text):
            raise OSError("fixture stderr closed")

        def flush(self):
            pass

    timing.perf_counter = _original_perf_counter
    timing.LOG_STREAM = _BrokenStream()
    try:
        with timing.tool_timing("demo_tool"):
            pass
        survived = True
    except Exception:
        survived = False
    t.ok(survived, "stderr 写入失败不影响工具结果")

    timing.LOG_STREAM = None
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        with timing.tool_timing("demo_tool"):
            pass
    t.eq(out.getvalue(), "", "耗时日志不写 stdout，stdio 协议不受干扰")
    t.ok(" demo_tool total=" in err.getvalue(), "耗时日志默认写 stderr", repr(err.getvalue()))
finally:
    timing.perf_counter = _original_perf_counter
    timing.LOG_STREAM = _original_timing_stream
```

- [ ] **Step 3: 运行，确认失败**

Run: `.venv/Scripts/python.exe tests/selftest_tree.py`
Expected: 在顶部 import 处报 `ImportError: cannot import name 'timing'`（模块还不存在）。

- [ ] **Step 4: 实现 `tvuitree/interfaces/timing.py`**

```python
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
```

- [ ] **Step 5: 运行检查，确认通过**

Run: 上文“检查命令”。
Expected: `自检通过：N 条断言全部成立`；第 9 节无 FAIL；pyflakes 无输出；`git diff --check` 无输出。

- [ ] **Step 6: Commit**（仅当用户要求提交时）

```bash
git add tvuitree/interfaces/timing.py tests/selftest_tree.py
git commit -m "Add per-call timing logger for MCP tools"
```

---

### Task 2: 五个 MCP 工具加埋点

**Files:**
- Modify: `tvuitree/interfaces/mcp.py:17-21`（import），`:162-324`（五个工具）
- Test: `tests/selftest_tree.py` 第 8 节

**Interfaces:**
- Consumes: `timing.tool_timing(tool)`、`ToolTimer.stage(name)`、`timing.LOG_STREAM`（Task 1）
- Produces: 每个工具每次调用写一行。各工具的阶段序列：
  - `observe_tv`：`connect`、`capture_tree`、`summarize`
  - `get_current_focus`：`connect`、`capture_tree`、`summarize`
  - `get_full_tree`：`connect`、`capture_tree`
  - `get_visible`：`connect`、`capture_tree`、`summarize`
  - `get_focus_screenshot`：`connect`、`capture_tree`、`summarize`、`screenshot`、`mark`（仅在有唯一焦点时）、`encode`、`save`
  - 提前返回时只出现已执行的阶段。

- [ ] **Step 1: 第 8 节加补丁、helper 和还原**

在第 8 节 `_original_render_focus_png = mcp_interface.render_focus_png` 之后加：

```python
_original_log_stream = timing.LOG_STREAM
```

在 `_without_capture_time` 函数之后加：

```python
def _timing_calls() -> list:
    """取出并清空本节的耗时日志，返回 (工具名, 阶段名列表, failed) 列表。"""
    lines = timing.LOG_STREAM.getvalue().splitlines()
    timing.LOG_STREAM.seek(0)
    timing.LOG_STREAM.truncate(0)
    calls = []
    for line in lines:
        parts = line.split(" ")
        fields = parts[4:]
        stages = [part.split("=", 1)[0] for part in fields if part.endswith("ms")]
        failed = next((part.split("=", 1)[1] for part in fields
                       if part.startswith("failed=")), None)
        calls.append((parts[2], stages, failed))
    return calls
```

在 `try:` 块第一行（`snapshot_adapter.snapshot = _fixture_snapshot` 之前）加：

```python
    timing.LOG_STREAM = io.StringIO()
```

在 `finally:` 块末尾加：

```python
    timing.LOG_STREAM = _original_log_stream
```

- [ ] **Step 2: 第 8 节加埋点断言**

按位置逐条插入（行号是改动前的）：

1. 第 1196 行（CLI 与 MCP 观察 JSON 相等断言）之后：

```python
    t.eq(_timing_calls(), [("observe_tv", ["connect", "capture_tree", "summarize"], None)],
         "observe_tv 每次调用写一行耗时，分连接、采集、摘要")
```

2. 第 1205 行（`独立焦点工具报告唯一焦点`）之后：

```python
    t.eq(_timing_calls(),
         [("get_current_focus", ["connect", "capture_tree", "summarize"], None)],
         "get_current_focus 写一行耗时")
```

3. 第 1220 行（`MCP 截图工具返回精简状态和原生 image 内容`）之后：

```python
        t.eq(_timing_calls(), [("get_focus_screenshot",
                                ["connect", "capture_tree", "summarize", "screenshot",
                                 "mark", "encode", "save"], None)],
             "截图工具按连接、采集、摘要、截图、标注、编码、保存分段计时")
```

4. `for focus_status in ("not_found", "ambiguous"):` 循环内，`unmarked = mcp_interface.get_focus_screenshot()` 之后：

```python
            t.eq(_timing_calls()[-1][1],
                 ["connect", "capture_tree", "summarize", "screenshot", "encode", "save"],
                 f"{focus_status} 时不标注，也不记 mark 阶段")
```

5. `mcp_interface.capture = _capture_failure` 之前加一行 `_timing_calls()`（丢弃前面的日志）。在 `t.ok("截图失败" in capture_failure["error"], ...)` 之后：

```python
        t.eq(_timing_calls(), [("get_focus_screenshot",
                                ["connect", "capture_tree", "summarize", "screenshot"],
                                "screenshot")],
             "截图失败时日志停在 screenshot 并标出 failed")
```

6. `mcp_interface._connect = lambda **kwargs: (None, "fixture")` 之前加一行 `_timing_calls()`。在 `t.ok("error" in connection_failure, "连接失败给出错误")` 之后：

```python
        t.eq(_timing_calls(), [("get_focus_screenshot", ["connect"], None)],
             "连接失败提前返回时仍写一行耗时")
```

7. 第 1320 行（CLI 与 MCP 完整树相等断言）之后：

```python
    t.eq(_timing_calls(), [("get_full_tree", ["connect", "capture_tree"], None)],
         "get_full_tree 写一行耗时")
```

8. 第 1329 行（CLI 与 MCP 可视树相等断言）之后：

```python
    t.eq(_timing_calls(),
         [("get_visible", ["connect", "capture_tree", "summarize"], None)],
         "get_visible 写一行耗时")
```

9. `snapshot_adapter.snapshot = _failed_snapshot` 之前加一行 `_timing_calls()`。在 `t.ok("焦点采集失败" in failed_focus_shot["error"], ...)` 之后：

```python
    t.eq(_timing_calls(), [
        ("observe_tv", ["connect", "capture_tree"], "capture_tree"),
        ("get_current_focus", ["connect", "capture_tree"], "capture_tree"),
        ("get_visible", ["connect", "capture_tree"], "capture_tree"),
        ("get_focus_screenshot", ["connect", "capture_tree", "screenshot", "encode", "save"],
         "capture_tree"),
    ], "采集失败被工具吞掉时日志仍标出 failed=capture_tree")
```

第 8 节原有断言一条都不改，尤其是 schema 集合、`set(mcp_focus) == {"status", "node"}`、截图 `expected_keys` 和 CLI==MCP 相等断言。它们守住“返回内容不变”这条约束。

- [ ] **Step 3: 运行，确认失败**

Run: `.venv/Scripts/python.exe tests/selftest_tree.py`
Expected: 第 8 节新增断言 FAIL，比如 `期望 [('observe_tv', ...)]，实际 []`。其余断言通过。

- [ ] **Step 4: 改 `tvuitree/interfaces/mcp.py`**

在 import 区（第 21 行 `from tvuitree.infrastructure.image import capture` 之后）加：

```python
from tvuitree.interfaces.timing import tool_timing
```

把第 162-324 行的五个工具整体替换为：

```python
@mcp.tool()
def get_current_focus(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
) -> dict:
    """返回精简的当前焦点节点信息，不返回祖先、同级节点或子节点。"""
    with tool_timing("get_current_focus") as timer:
        try:
            with timer.stage("connect"):
                device, target = _connect(
                    TV_IP_Address=TV_IP_Address, port=port, adb=adb,
                    no_connect=False,
                )
            if device is None:
                return _focus_info(error_observation(f"无法连接 TV：{target}")["focus"])
            with timer.stage("capture_tree"):
                full = collect_full_json(
                    adb=device, serial=device.serial, quiet=True,
                    use_dumpsys=False,
                )
            with timer.stage("summarize"):
                focus = collect_observation(full_json=full)["focus"]
                return _focus_info(focus, full)
        except Exception as exc:
            return _focus_info(error_observation(exc)["focus"])


@mcp.tool(structured_output=False)
def get_focus_screenshot(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
) -> list:
    """返回截图结果和 PNG；唯一 a11y 焦点用加粗红框标出。"""
    with tool_timing("get_focus_screenshot") as timer:
        status = {
            "focus_found": False,
            "screenshot_captured": False,
            "focus_marked": False,
            "image_path": None,
            "image_base64": None,
        }
        try:
            with timer.stage("connect"):
                device, target = _connect(
                    TV_IP_Address=TV_IP_Address, port=port, adb=adb,
                    no_connect=False,
                )
        except Exception as exc:
            status["error"] = f"连接 TV 失败：{exc}"
            return [status]
        if device is None:
            status["error"] = f"无法连接 TV：{target}"
            return [status]

        errors = []
        full = None
        try:
            with timer.stage("capture_tree"):
                full = collect_full_json(
                    adb=device, serial=device.serial, quiet=True,
                    use_dumpsys=False,
                )
            with timer.stage("summarize"):
                observation = collect_observation(full_json=full)
                status["focus_found"] = observation["focus"]["status"] == "found"
        except Exception as exc:
            errors.append(f"焦点采集失败：{exc}")

        try:
            with timer.stage("screenshot"):
                png = capture(device)
        except Exception as exc:
            errors.append(f"截图失败：{exc}")
            status["error"] = "；".join(errors)
            return [status]

        status["screenshot_captured"] = True
        output_png = png
        if status["focus_found"] and full is not None:
            try:
                with timer.stage("mark"):
                    output_png, result = render_focus_png(full, png)
                status["focus_marked"] = result["drawn"] == 1 and len(result["boxes"]) == 1
                if not status["focus_marked"]:
                    errors.append("焦点框未能画到截图上")
            except Exception as exc:
                errors.append(f"焦点标注失败：{exc}")
                output_png = png

        with timer.stage("encode"):
            status["image_base64"] = base64.b64encode(output_png).decode("ascii")
        try:
            with timer.stage("save"):
                status["image_path"] = _save_focus_screenshot(output_png)
        except Exception as exc:
            errors.append(f"截图保存失败：{exc}")
        if errors:
            status["error"] = "；".join(errors)
        return [status, Image(data=output_png, format="png")]



@mcp.tool()
def observe_tv(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = False,
    max_nodes: int = 80,
) -> dict:
    """读取当前 TV 焦点、精简页面节点和 R0–R3 证据。"""
    with tool_timing("observe_tv") as timer:
        try:
            with timer.stage("connect"):
                device, target = _connect(
                    TV_IP_Address=TV_IP_Address, port=port, adb=adb,
                    no_connect=no_connect,
                )
            if device is None:
                return error_observation(f"无法连接 TV：{target}")
            # 拆成采集和摘要两步，分别计时；结果与 collect_observation(adb=...) 相同
            with timer.stage("capture_tree"):
                full = collect_full_json(
                    adb=device, serial=device.serial, quiet=True,
                    use_dumpsys=not no_dumpsys,
                )
            with timer.stage("summarize"):
                return collect_observation(full_json=full, max_nodes=max_nodes)
        except Exception as exc:  # MCP 工具返回结构化错误，避免宿主丢失上下文
            return error_observation(exc)


@mcp.tool()
def get_full_tree(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
    no_dumpsys: bool = False,
) -> dict:
    """读取当前 TV 的完整控件树；需要详细诊断时使用。"""
    with tool_timing("get_full_tree") as timer:
        try:
            with timer.stage("connect"):
                device, _target = _connect(
                    TV_IP_Address=TV_IP_Address, port=port, adb=adb,
                    no_connect=no_connect,
                )
            if device is None:
                return {"error": "无法连接 TV", "mode": "full"}
            with timer.stage("capture_tree"):
                full = collect_full_json(
                    adb=device, serial=device.serial, quiet=True,
                    use_dumpsys=not no_dumpsys,
                )
            full.pop("_parse_anomalies", None)
            return full
        except Exception as exc:  # MCP 工具返回可读错误，不向宿主泄漏 traceback
            return {"error": str(exc), "error_type": type(exc).__name__, "mode": "full"}


@mcp.tool()
def get_visible(
    TV_IP_Address: Optional[str] = None,
    port: Optional[int] = None,
    adb: Optional[str] = None,
    no_connect: bool = False,
) -> dict:
    """读取当前屏幕内的控件摘要和焦点，排除屏外节点与空布局。"""
    with tool_timing("get_visible") as timer:
        try:
            with timer.stage("connect"):
                device, _target = _connect(
                    TV_IP_Address=TV_IP_Address, port=port, adb=adb,
                    no_connect=no_connect,
                )
            if device is None:
                return {"error": "无法连接 TV", "mode": "visible"}
            # 与 collect_visible(adb=...) 相同：只采 a11y，再做可视筛选
            with timer.stage("capture_tree"):
                full = collect_full_json(
                    adb=device, serial=device.serial, quiet=True,
                    use_dumpsys=False,
                )
            with timer.stage("summarize"):
                return collect_visible(full_json=full)
        except Exception as exc:
            return {"error": str(exc), "error_type": type(exc).__name__, "mode": "visible"}
```

等价性说明：`collect_observation(adb=...)` 内部就是先 `collect_full_json(save_raw=None, ...)`，再 `summarize_full_json(full, max_nodes, parse_anomalies=full["_parse_anomalies"])`。`collect_observation(full_json=full, ...)` 走同一个 `summarize_full_json`。`collect_visible` 同理（`use_dumpsys=False`）。所以返回 JSON 不变，第 8 节的 CLI==MCP 断言会验证这一点。这里没有用装饰器，因为 FastMCP 靠 `inspect.signature` 生成 schema，显式 `with` 不碰函数签名。

- [ ] **Step 5: 运行检查，确认通过**

Run: 上文“检查命令”。
Expected: `自检通过`；第 8、9 节无 FAIL；pyflakes 无输出。第 8 节运行期间终端不应出现 `[tv-uitree]` 行，因为日志都被 `LOG_STREAM` 收走了。

- [ ] **Step 6: Commit**（仅当用户要求提交时）

```bash
git add tvuitree/interfaces/mcp.py tests/selftest_tree.py
git commit -m "Log per-stage timing for each MCP tool call"
```

---

### Task 3: 文档和端到端验证

**Files:**
- Modify: `README.md`（第 209 行段落之后；第 361 行“验证”段）
- Modify: `AGENTS.md:15`、`AGENTS.md:37`
- Temp: `_temp/mcp_timing_check.py`（验证完删除；`_temp/` 已被 Git 忽略）

**Interfaces:**
- Consumes: Task 1、2 的日志格式和阶段名
- Produces: 文档；无代码接口

- [ ] **Step 1: README 加一段**

在 `README.md` 第 209 行（`get_focus_screenshot` 段落）之后插入：

````markdown
每次调用 MCP 工具，服务都会向标准错误写一行耗时，工具返回内容不变：

```text
[tv-uitree] 2026-09-29T15:30:01.123 get_focus_screenshot total=1532.4ms connect=112.0ms capture_tree=903.6ms summarize=2.1ms screenshot=480.3ms mark=21.5ms encode=6.2ms save=6.7ms
```

`total` 从进入工具函数算到函数返回，不含 MCP 库序列化结果和 stdio 传输的时间。阶段含义：`connect` 读取 `config.json` 并连接 ADB；`capture_tree` 读取设备属性、dumpsys、uiautomator2 dump 并配对；`summarize` 生成焦点、观察或可视摘要；`screenshot` 截屏；`mark` 画焦点红框；`encode` 生成 Base64；`save` 写 PNG 文件。没有执行的阶段不出现；某阶段抛出异常时，行尾追加 `failed=<阶段名>`。日志显示在哪里取决于宿主：在终端直接运行 `python main.py mcp` 时显示在该终端，其他宿主一般写进它的 MCP 服务日志。
````

在第 361 行“验证”段末尾追加一句：

```markdown
调用任一 MCP 工具后，服务的标准错误中应出现一行以 `[tv-uitree]` 开头的耗时记录。
```

- [ ] **Step 2: AGENTS.md 更新**

第 15 行，`so diagnostics must go to stderr.` 之后加一句：

```markdown
Each MCP tool wraps its body in `interfaces/timing.tool_timing` and writes exactly one timing line to stderr; timing never goes into tool results.
```

第 37 行，`Section 8 monkeypatches \`snapshot.snapshot\` and each interface's \`connect_for_cli\`` 这句改为：

```markdown
Section 8 monkeypatches `snapshot.snapshot`, each interface's `connect_for_cli`, and `timing.LOG_STREAM`, so a new live command needs the same patch and restore, and a new MCP tool needs its timing stages asserted there.
```

- [ ] **Step 3: 端到端验证 stdio 协议和 stderr 日志**

新建 `_temp/mcp_timing_check.py`：

```python
"""临时脚本：真实启动 stdio MCP 服务，确认协议正常、stderr 有耗时行。"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOG = Path("_temp/mcp_stderr.log")


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["main.py", "mcp"], cwd=".")
    with LOG.open("w", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # 故意连一个不存在的地址：不依赖真机，只验证日志链路
                result = await session.call_tool(
                    "get_current_focus", {"TV_IP_Address": "127.0.0.1", "port": 1})
                print("result:", result.content[0].text)
    print("stderr:", LOG.read_text(encoding="utf-8"))


asyncio.run(main())
```

Run: `.venv/Scripts/python.exe _temp/mcp_timing_check.py`
Expected:`result:` 是 `get_current_focus` 的 error JSON，协议没有被打断。`stderr:` 里恰好有一行 `[tv-uitree] ... get_current_focus total=...ms connect=...ms`，后面可能带 `failed=connect`。如果 ADB 连接超时较长，等它结束即可。

有可用 TV 时，把参数换成 `{}`（读 `config.json`），确认日志出现 `capture_tree` 和 `summarize`，并把真实耗时记在交付说明里。

验证后删除临时文件：

```bash
rm _temp/mcp_timing_check.py _temp/mcp_stderr.log
```

- [ ] **Step 4: 完整检查**

Run: 上文“检查命令”，再运行 `.venv/Scripts/python.exe main.py --help` 和 `.venv/Scripts/python.exe main.py tree --prune-list`。
Expected: 自检通过；两条命令正常输出，且不含 `[tv-uitree]` 耗时行（CLI 不计时）。

- [ ] **Step 5: Commit**（仅当用户要求提交时）

```bash
git add README.md AGENTS.md
git commit -m "Document MCP tool timing log"
```
