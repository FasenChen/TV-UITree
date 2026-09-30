# MCP 切换默认设备 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 MCP 工具 `set_default_device`，把 `config.json` 里的默认 `TV_IP_Address`（可选 `port`）改成新值，之后所有工具不传参就连新设备。

**Architecture:** 按现有分层走：`infrastructure/device_config.py` 增加原子写 `save_device_config`；`application/connection.py` 抽出地址/端口校验，并新增 `update_default_device` 做"读取→校验→合并→保存"；`interfaces/mcp.py` 注册工具，用 `tool_timing` 计时，失败返回结构化错误。`config.json` 本来就在每次连接时重新读取，所以写入后下一次调用立即生效，不需要改任何现有工具。

**Tech Stack:** Python 3.10+，`mcp` FastMCP，标准库 `json` / `os` / `tempfile`。

**Spec:** 用户需求（本对话）："当前 adb 的 devices ip 只能自己修改 config 文件来切换，我想添加一个 tool 来修改 devices 的 ip"。无单独 spec 文件。

## Global Constraints

- 依赖只向内：domain 不碰文件；文件读写只在 `infrastructure/`；校验规则只在 `application/connection.py` 一处。
- 写入必须原子：先写同目录临时文件，再 `os.replace`；失败时原 `config.json` 保持不变，临时文件被删除。
- 保留 `config.json` 中所有其他字段（如 `adb`）和字段顺序；格式 `indent=2`、`ensure_ascii=False`、末尾换行。
- 校验与 `connection_options` 完全一致：地址非空、无首尾空白、不含 `:` 和空白；端口是 1–65535 的 `int` 且不是 `bool`。
- MCP 工具体包在 `tool_timing("set_default_device")` 内，恰好一行 stderr 耗时日志；stdout 不写任何内容。
- 工具只改文件，不执行 `adb connect`（切换与连接解耦，设备离线也能先切换）。
- 自检不得改动仓库真实 `config.json`：测试一律把 `device_config.CONFIG_PATH` 指向临时文件，并在 `finally` 中还原。
- `config.json` 已被 git 跟踪；工具写入后它会出现在 `git status` 里，提交时不要带上本机设备地址（AGENTS.md）。
- 检查命令用 `.\.venv\Scripts\python.exe`。

## Review Focus

1. 传入 `"192.168.1.5:5555"`（带端口的地址）→ 拒绝，文件字节不变。测试在 Task 2。
2. `port=True`、`port=0`、`port=70000` → 拒绝，文件字节不变。测试在 Task 2。
3. 只传 IP 不传端口 → 端口保持原值，`adb` 字段原样保留。测试在 Task 2。
4. 切换后不重启服务，下一次 `connection_options()` 就返回新目标。测试在 Task 2。
5. `os.replace` 失败（如文件被占用）→ 原文件不变、不残留 `.tmp` 文件、工具返回 `error`。测试在 Task 1 和 Task 3。

---

## File Structure

- Modify `tvuitree/infrastructure/device_config.py`：新增 `save_device_config(config: dict) -> None`。
- Modify `tvuitree/application/connection.py`：抽出 `_check_address` / `_check_port`；新增 `update_default_device`。
- Modify `tvuitree/interfaces/mcp.py`：新增工具 `set_default_device`；模块文档不再写"只读"。
- Modify `tests/selftest_tree.py`：新增第 11 节（配置写入与切换），第 8 节补工具 schema 与耗时断言。
- Modify `README.md`：工具表、工具数量（"五个"→"六个"）、新工具说明。

---

### Task 1: 原子写 `save_device_config`

**Files:**
- Modify: `tvuitree/infrastructure/device_config.py`
- Test: `tests/selftest_tree.py`（新增第 11 节，放在第 10 节之后、汇总之前）

**Interfaces:**
- Produces: `save_device_config(config: dict[str, object]) -> None`，写到当前 `CONFIG_PATH`（调用时读取模块变量，便于测试替换）。

- [ ] **Step 1: 写失败测试**

在 `tests/selftest_tree.py` 第 10 节结束后、最终汇总之前追加：

```python
# ================================================================== 11. 默认设备配置写入

t.group("11. 默认设备配置写入与切换")

from tvuitree.infrastructure import device_config
from tvuitree.application import connection as app_connection

_original_config_path = device_config.CONFIG_PATH
_config_dir = Path(TD) / "device_config"
_config_dir.mkdir(exist_ok=True)


def _write_fixture_config(text: str) -> Path:
    path = _config_dir / "config.json"
    path.write_text(text, encoding="utf-8")
    device_config.CONFIG_PATH = path
    return path


_FIXTURE_CONFIG = ('{\n  "TV_IP_Address": "10.0.0.1",\n  "port": 5555,\n'
                   '  "adb": "X:\\\\adb.exe"\n}\n')
try:
    path = _write_fixture_config(_FIXTURE_CONFIG)
    device_config.save_device_config(
        {"TV_IP_Address": "10.0.0.2", "port": 5555, "adb": "X:\\adb.exe"})
    t.eq(path.read_text(encoding="utf-8"),
         '{\n  "TV_IP_Address": "10.0.0.2",\n  "port": 5555,\n'
         '  "adb": "X:\\\\adb.exe"\n}\n',
         "保存保持 2 空格缩进、字段顺序和末尾换行")
    t.eq(sorted(p.name for p in _config_dir.iterdir()), ["config.json"],
         "保存后不残留临时文件")

    path = _write_fixture_config(_FIXTURE_CONFIG)
    _original_replace = device_config.os.replace

    def _replace_failure(src, dst):
        raise PermissionError("fixture locked")

    device_config.os.replace = _replace_failure
    try:
        device_config.save_device_config({"TV_IP_Address": "10.0.0.9", "port": 1})
        raised = False
    except ValueError:
        raised = True
    finally:
        device_config.os.replace = _original_replace
    t.ok(raised, "替换失败抛出 ValueError，说明写入失败")
    t.eq(path.read_text(encoding="utf-8"), _FIXTURE_CONFIG, "替换失败时原配置不变")
    t.eq(sorted(p.name for p in _config_dir.iterdir()), ["config.json"],
         "替换失败时删除临时文件")
finally:
    device_config.CONFIG_PATH = _original_config_path
```

- [ ] **Step 2: 运行，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 11 节报 `AttributeError: module ... has no attribute 'save_device_config'`（脚本在该处中断或记失败），退出码 1。

- [ ] **Step 3: 实现**

在 `tvuitree/infrastructure/device_config.py` 顶部加 `import os`、`import tempfile`，文件末尾追加：

```python
def save_device_config(config: dict[str, object]) -> None:
    """Atomically replace the config so a failed write leaves the old file intact."""
    target = CONFIG_PATH
    text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
        os.replace(temp_name, target)
    except OSError as error:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise ValueError(f"无法写入设备配置文件 {target}：{error}") from error
```

- [ ] **Step 4: 运行，确认通过**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 11 节全部 ok，退出码 0。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree/infrastructure/device_config.py tests/selftest_tree.py
git commit -m "Add atomic writer for device config"
```

---

### Task 2: 应用层 `update_default_device`

**Files:**
- Modify: `tvuitree/application/connection.py`
- Test: `tests/selftest_tree.py`（第 11 节，接在 Task 1 的 `try` 块内、`finally` 之前）

**Interfaces:**
- Consumes: `load_device_config()`、`save_device_config(config)`（Task 1）。
- Produces: `update_default_device(*, TV_IP_Address: str, port: Optional[int] = None) -> dict`，返回

  ```python
  {"previous": {"TV_IP_Address": <旧值>, "port": <旧值>},
   "current": {"TV_IP_Address": <新值>, "port": <新值>},
   "config_path": "<CONFIG_PATH 绝对路径字符串>"}
  ```

  校验失败抛 `ValueError`，且不写文件。

- [ ] **Step 1: 写失败测试**

在第 11 节 `try` 块里、`finally:` 之前追加：

```python
    path = _write_fixture_config(_FIXTURE_CONFIG)
    result = app_connection.update_default_device(TV_IP_Address="10.0.0.2")
    t.eq(result["previous"], {"TV_IP_Address": "10.0.0.1", "port": 5555}, "返回切换前的目标")
    t.eq(result["current"], {"TV_IP_Address": "10.0.0.2", "port": 5555},
         "只传 IP 时端口保持原值")
    t.eq(result["config_path"], str(path), "返回被修改的配置文件路径")
    saved = json.loads(path.read_text(encoding="utf-8"))
    t.eq(saved, {"TV_IP_Address": "10.0.0.2", "port": 5555, "adb": "X:\\adb.exe"},
         "切换设备保留 adb 等其他字段")
    t.eq(app_connection.connection_options().target, "10.0.0.2:5555",
         "切换后下一次连接立即使用新目标，无需重启")

    result = app_connection.update_default_device(TV_IP_Address="10.0.0.3", port=5556)
    t.eq(result["current"], {"TV_IP_Address": "10.0.0.3", "port": 5556}, "可同时切换端口")

    for bad_kwargs in ({"TV_IP_Address": "10.0.0.4:5555"},
                       {"TV_IP_Address": " 10.0.0.4"},
                       {"TV_IP_Address": ""},
                       {"TV_IP_Address": "10.0.0.4", "port": True},
                       {"TV_IP_Address": "10.0.0.4", "port": 0},
                       {"TV_IP_Address": "10.0.0.4", "port": 70000}):
        before = path.read_bytes()
        try:
            app_connection.update_default_device(**bad_kwargs)
            rejected = False
        except ValueError:
            rejected = True
        t.ok(rejected, f"非法参数被拒绝：{bad_kwargs}")
        t.eq(path.read_bytes(), before, f"非法参数不改动配置文件：{bad_kwargs}")

    _write_fixture_config('{\n  "port": 5555\n}\n')
    result = app_connection.update_default_device(TV_IP_Address="10.0.0.5")
    t.eq(result["previous"], {"TV_IP_Address": None, "port": 5555},
         "原配置缺地址时 previous 如实给 None")
```

- [ ] **Step 2: 运行，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 11 节报 `AttributeError: ... 'update_default_device'`，退出码 1。

- [ ] **Step 3: 实现**

`tvuitree/application/connection.py`：导入整个模块，不要按值导入 `CONFIG_PATH` 或函数（测试会替换 `device_config.CONFIG_PATH`，按值导入会拿到旧路径）：

```python
from tvuitree.infrastructure import device_config
from tvuitree.infrastructure.adb import Adb, resolve_adb
```

并把 `connection_options` 里的 `load_device_config()` 改为 `device_config.load_device_config()`。然后把校验抽成两个函数，`connection_options` 改为调用它们，并新增 `update_default_device`：

```python
def _check_address(address: object) -> str:
    if not isinstance(address, str) or not address.strip():
        raise ValueError("TV_IP_Address 必须是非空字符串，请检查 config.json")
    if address != address.strip() or ":" in address or any(
        character.isspace() for character in address
    ):
        raise ValueError("TV_IP_Address 只能填写 IP 或主机名，不含端口")
    return address


def _check_port(port: object) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError("port 必须是 1 到 65535 的整数，请检查 config.json")
    return port


def connection_options(*, TV_IP_Address: Optional[str] = None,
                       port: Optional[int] = None, adb: Optional[str] = None,
                       no_connect: bool = False) -> ConnectionOptions:
    """Resolve explicit values over config defaults for both CLI and MCP."""
    config = device_config.load_device_config()
    address = _check_address(
        config.get("TV_IP_Address") if TV_IP_Address is None else TV_IP_Address)
    selected_port = _check_port(config.get("port") if port is None else port)
    selected_adb = config.get("adb") if adb is None else adb
    if selected_adb is not None and (
        not isinstance(selected_adb, str) or not selected_adb.strip()
    ):
        raise ValueError("adb 必须是非空路径字符串，请检查 config.json")
    return ConnectionOptions(address, selected_port, adb=selected_adb, no_connect=no_connect)


def update_default_device(*, TV_IP_Address: str,
                          port: Optional[int] = None) -> dict:
    """Validate and persist a new default target; other config fields stay as they are."""
    config = device_config.load_device_config()
    previous = {"TV_IP_Address": config.get("TV_IP_Address"), "port": config.get("port")}
    address = _check_address(TV_IP_Address)
    selected_port = _check_port(config.get("port") if port is None else port)
    config["TV_IP_Address"] = address
    config["port"] = selected_port
    device_config.save_device_config(config)
    return {
        "previous": previous,
        "current": {"TV_IP_Address": address, "port": selected_port},
        "config_path": str(device_config.CONFIG_PATH),
    }
```

说明：原配置端口非法且本次没传 `port` 时，`_check_port` 会拒绝，这是有意的——不把坏配置原样写回。

- [ ] **Step 4: 运行，确认通过**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 0 节（真实 `config.json` 默认目标）与第 11 节全部 ok，退出码 0。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree/application/connection.py tests/selftest_tree.py
git commit -m "Add use case to switch the default TV device"
```

---

### Task 3: MCP 工具 `set_default_device` 与文档

**Files:**
- Modify: `tvuitree/interfaces/mcp.py`
- Modify: `README.md`
- Test: `tests/selftest_tree.py`（第 8 节 schema 断言；第 11 节 MCP 调用与耗时断言）

**Interfaces:**
- Consumes: `update_default_device(*, TV_IP_Address, port)`（Task 2）。
- Produces: MCP 工具 `set_default_device(TV_IP_Address: str, port: Optional[int] = None) -> dict`。成功返回 Task 2 的 dict；失败返回 `{"error": str, "error_type": str}`。耗时日志阶段：`save`。

- [ ] **Step 1: 写失败测试**

第 8 节在 `for name in ("get_current_focus", "get_focus_screenshot"):` 这组 schema 断言之后追加：

```python
    t.eq(set(mcp_schemas["set_default_device"]["properties"]), {"TV_IP_Address", "port"},
         "set_default_device 只公开地址和端口")
    t.eq(mcp_schemas["set_default_device"].get("required"), ["TV_IP_Address"],
         "set_default_device 必须给出地址")
```

第 11 节 `try` 块里、`finally:` 之前追加（`timing` 已在文件顶部导入；在第 11 节 `try` 前加 `_original_timing_stream_11 = timing.LOG_STREAM`，`finally` 中还原）：

```python
    from tvuitree.interfaces import mcp as mcp_interface
    timing.LOG_STREAM = io.StringIO()
    path = _write_fixture_config(_FIXTURE_CONFIG)
    mcp_result = mcp_interface.set_default_device(TV_IP_Address="10.0.0.7")
    t.eq(mcp_result["current"], {"TV_IP_Address": "10.0.0.7", "port": 5555},
         "MCP 工具切换默认设备")
    t.eq(_timing_calls(), [("set_default_device", ["save"], None)],
         "set_default_device 写一行耗时，只有 save 阶段")

    before = path.read_bytes()
    bad = mcp_interface.set_default_device(TV_IP_Address="10.0.0.8:5555")
    t.eq(set(bad), {"error", "error_type"}, "非法地址返回结构化错误")
    t.eq(bad["error_type"], "ValueError", "错误类型是 ValueError")
    t.eq(path.read_bytes(), before, "MCP 非法调用不改动配置")
    t.eq(_timing_calls(), [("set_default_device", ["save"], "save")],
         "失败时日志标出 failed=save")

    _original_replace = device_config.os.replace
    device_config.os.replace = _replace_failure
    try:
        locked = mcp_interface.set_default_device(TV_IP_Address="10.0.0.9")
    finally:
        device_config.os.replace = _original_replace
    t.ok("无法写入设备配置文件" in locked.get("error", ""), "写入失败返回可读错误")
    t.eq(path.read_bytes(), before, "写入失败时配置不变")
```

并把第 11 节的 `finally` 改为：

```python
finally:
    device_config.CONFIG_PATH = _original_config_path
    timing.LOG_STREAM = _original_timing_stream_11
```

- [ ] **Step 2: 运行，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 第 8 节 `KeyError: 'set_default_device'`，第 11 节 `AttributeError`，退出码 1。

- [ ] **Step 3: 实现工具**

`tvuitree/interfaces/mcp.py`：

模块文档改为：

```python
"""tv-uitree 的 MCP 服务。

宿主通过 stdio 启动本文件。服务读取 TV 状态、完整树和截图，不发送按键；
唯一的写操作是 set_default_device 修改 config.json 的默认设备。
与 CLI 共用应用层采集、观察摘要和截图绘制。
"""
```

导入改为：

```python
from tvuitree.application.connection import (
    connection_options, connect_device, update_default_device,
)
```

文件末尾追加：

```python
@mcp.tool()
def set_default_device(TV_IP_Address: str, port: Optional[int] = None) -> dict:
    """修改 config.json 的默认 TV 地址（可选端口）；之后不传地址的调用都连新设备。只写配置，不连接设备。"""
    with tool_timing("set_default_device") as timer:
        try:
            with timer.stage("save"):
                return update_default_device(TV_IP_Address=TV_IP_Address, port=port)
        except Exception as exc:
            return {"error": str(exc), "error_type": type(exc).__name__}
```

- [ ] **Step 4: 更新 README**

1. MCP 启动段落里"客户端应能列出 … `get_focus_screenshot`"改为"… `get_focus_screenshot` 和 `set_default_device`"。
2. 工具表追加一行：

   ```markdown
   | `set_default_device` | 修改 `config.json` 的默认设备，返回切换前后的目标 | `TV_IP_Address`（必填）、`port` |
   ```

3. "五个工具都从仓库根目录的 `config.json` 读取默认设备参数……以下参数对五个工具都适用"改为"五个读取工具……"，保持原义（这组参数不适用于 `set_default_device`）。
4. 在"MCP 工具参数"小节末尾加一段：

   ```markdown
   `set_default_device` 把 `TV_IP_Address` 写进 `config.json`；传入 `port` 时一并修改，省略时保留原端口，`adb` 等其他字段不变。校验规则与连接参数相同，非法值不会写入。写入是原子的，失败时原文件保持不变。配置在每次连接时重新读取，切换后无需重启 MCP 服务。工具只改配置、不执行 `adb connect`；成功返回 `previous`、`current` 和 `config_path`，失败返回 `error` 与 `error_type`。`config.json` 受 git 跟踪，切换后不要把本机设备地址提交进仓库。
   ```

- [ ] **Step 5: 全量检查**

Run（仓库根目录）：

```powershell
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile $pythonFiles
.\.venv\Scripts\python.exe -m pyflakes $pythonFiles
.\.venv\Scripts\python.exe tests/selftest_tree.py
git diff --check
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe main.py tree --prune-list
git diff --stat -- config.json
```

Expected: 全部通过，退出码 0；最后一条无输出（真实 `config.json` 未被自检改动）。

- [ ] **Step 6: 真机验证（有可用 TV 时）**

在 MCP Inspector（`.\scripts\start_mcp_inspector.ps1`）中调用 `set_default_device`，参数设为另一台 TV 的地址，再调用 `get_current_focus` 且不传参，确认连到新设备；最后用 `set_default_device` 切回原地址，确认 `git diff -- config.json` 为空。无 TV 时在交付说明中写明跳过。

- [ ] **Step 7: Commit**

```powershell
git add tvuitree/interfaces/mcp.py README.md tests/selftest_tree.py
git commit -m "Add MCP tool to switch the default TV device"
```
