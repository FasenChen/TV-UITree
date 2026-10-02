# 注释、命名与结构规范 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按仓库现有习惯把注释语言、公开命名和分层边界收齐，不改 JSON 字段、CLI 退出码、MCP schema，也不改配对 / 剪枝 / 画框的业务语义。

**Architecture:** 先用自检锁住「禁止残留」和「新公开名可导入」，再按任务改生产代码。跨模块的 `_` 前缀函数改成公开名；无调用的参数和死分支删掉。CLI 的 `shot` 经 `json_io.load_full_json` 读树；`image.load_tree` 保留给测试，校验口径相同，但抛 `ValueError`/`OSError` 而不是 `SystemExit`，避免 infrastructure 依赖 interfaces。`TV_IP_Address`、`generator: tv_tree.py`、MCP 工具名等对外契约一律不动。自检是一条顺序脚本、断言失败不中断、**未捕获的 TypeError 会整场退出**，因此改函数签名时：第 12 节用 `inspect.signature` / `hasattr` 先变红，调用点与生产代码在同一步一起改。

**Tech Stack:** Python 3.10+；离线自检 `tests/selftest_tree.py`（普通脚本，不是 pytest）；项目 venv `.\.venv\Scripts\python.exe`。

**Spec:** 没有单独 spec 文件。需求来自 2026-10-02 的仓库审核：用户不放心先前由多个代理写成的注释、命名和项目结构，要求全面规范；明确不改业务语义。

## Global Constraints

- 不改变 JSON 字段名、字段口径、CLI 退出码（2/3/1）、MCP 工具名、输入 schema、返回键集合。
- 不把 `TV_IP_Address`（CLI 旗标、MCP 参数、`config.json` 键、`ConnectionOptions` 字段）改成 PEP8 名字。
- 不把 `full JSON` 的 `generator` 从 `tv_tree.py` 改掉。
- 不改 R0–R3、剪枝认领顺序、画框「逐像素对齐、不加偏移」的判定。
- 依赖只向内：domain 不碰设备、文件、终端、MCP、Pillow、uiautomator2。
- `collect_full_json` 必须继续在函数体内 `from tvuitree.infrastructure.snapshot import snapshot`，测试第 8 节在调用时 monkeypatch `snapshot.snapshot`。
- 模块文档一行英文；函数 / 类文档和行内注释用中文。用户可见字符串保持中文。
- Python 3.10+、四空格、UTF-8、新代码带类型注解。
- 检查命令用 `.\.venv\Scripts\python.exe`。自检是 `python tests/selftest_tree.py`，没有单测选择器。
- 直接在 `main` 上提交，不开分支、不提 PR。不要把 `config.json` 的本机地址提交进去。
- `_temp/golden/` 是 gitignore 的真机金样，不作为本计划的必改文件；若本地有 `golden.py`，`pick_block_ex` 重命名后它已有 `getattr(..., "pick_block")` 回退。

## Review Focus

- `shot --json` 读到 JSON 数组或非对象时，当前 `image.load_tree` 对 `obj.get` 抛 `AttributeError` 或 `SystemExit`，`run_shot` 接不住。期望：退出码 1，stderr 有说明，无 traceback（Task 4）。
- `parse_dumpsys_top` 不传 `anomalies` 时写入模块级 `PARSE_ANOMALIES`；MCP 并发两次解析会互相 `clear()`。期望：每次解析用调用方传入的列表，模块不再有可变全局（Task 3）。
- `clip_to_chain` 去掉未使用的 `screen` 后，漏改某个只传位置参数的调用方会 `TypeError`。期望：生产代码与自检全部改成单参数（Task 3）；`_temp/golden/golden.py` 不调用它。
- `emit_json` 把 `len(text)` 说成「字节」，中文 JSON 会少报。期望：按 UTF-8 字节数打印（Task 4）。
- `interfaces/mcp.py` 在 `try: from mcp...` 之前先 `from pydantic import Field`；只缺 `mcp` 时错误信息变成 pydantic 的 ImportError，而不是「请 pip install mcp」。期望：两个导入都在同一个 `try` 里（Task 5）。

## Out of scope（需用户另开任务）

- 把已跟踪的 `config.json` 改成 `config.example.json` + gitignore 的本地文件。
- 拆 `requirements.txt` / 钉版本 / 去掉未引用的 `uiautodev`。
- 把 `snapshot()` 的字符串键 dict 改成 dataclass（第 8 节夹具按键名构造）。
- 把测试迁到 pytest；重命名终端 `C` / `c()`（约 58 处）。
- 合并 `observation._path_text` 与 `visible` 里的 path 格式化（根节点一个是 `"root"`，一个是 `""`）。

## File Structure

- Modify: `tvuitree/domain/tree/models.py`、`parsing.py`、`matching.py`、`capture.py`、`output.py`
- Modify: `tvuitree/domain/observation.py`、`visible.py`、`screenshot.py`、`component.py`
- Modify: `tvuitree/application/observation.py`、`input.py`、`connection.py`、`screenshot.py`
- Modify: `tvuitree/infrastructure/image.py`、`snapshot.py`、`adb.py`、`device_config.py`
- Modify: `tvuitree/interfaces/json_io.py`、`observe.py`、`tree.py`、`visible.py`、`shot.py`、`mcp.py`、`cli.py`
- Create: `tvuitree/domain/__init__.py`（与 `tree/__init__.py` 对齐的一层包文档）
- Modify: `tests/selftest_tree.py`、`AGENTS.md`
- README「旧命令迁移」表里的 `tv_shot.py` / `tv_input.py` 是历史入口名，保留不改。

检查命令（仓库根目录）：

```powershell
$py = '.\.venv\Scripts\python.exe'
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
& $py -m py_compile $pythonFiles
& $py -m pyflakes $pythonFiles
& $py tests/selftest_tree.py
git diff --check
```

公开名对照（后续任务必须用这些名字，不要另起）：

| 旧 | 新 | 所在 |
|---|---|---|
| `_anomaly` | `record_anomaly` | `domain/tree/models.py` |
| `_node_summary` | `node_summary` | `domain/observation.py` |
| `_px` | `to_pixel` | `domain/screenshot.py` |
| `_scale_factors` | `scale_factors` | `domain/screenshot.py` |
| `_emit`（json_io） | `emit_json` | `interfaces/json_io.py` |
| `_load_full` | `load_full_json` | `interfaces/json_io.py` |
| `pick_block_ex` | `pick_block` | `domain/tree/parsing.py` |
| `screenshot.Node` | `JsonNode` | `domain/screenshot.py` |
| `clip_to_chain(node, screen)` | `clip_to_chain(node)` | `domain/tree/matching.py` |
| `run_align(snap, quiet=False)` | `run_align(snap)` | `domain/tree/capture.py` |
| `build_unified(u, v, st, screen)` | `build_unified(u, v, screen)` | `domain/tree/matching.py` |

`timing._emit` 保持私有，不要改名，避免和 `emit_json` 抢含义。

---

### Task 1: 注释语言约定与腐烂注释

**Files:**
- Modify: `tvuitree/domain/observation.py`、`component.py`、`screenshot.py`、`tree/models.py`、`visible.py`
- Modify: `tvuitree/infrastructure/adb.py`、`image.py`、`device_config.py`、`snapshot.py`
- Modify: `tvuitree/application/connection.py`、`observation.py`、`screenshot.py`
- Modify: `tvuitree/interfaces/mcp.py`
- Test: `tests/selftest_tree.py`（新增第 12 节，放在第 11 节之后、收尾之前）

**Interfaces:**
- Consumes: 无
- Produces: 约定生效——模块文档英文一行；函数/类文档和注释中文；库模块无 shebang / coding 声明；不再出现「本脚本」「设计原则第 N 条」和空的分段标题。

- [ ] **Step 1: 写会失败的第 12 节**

在 `tests/selftest_tree.py` 最后一组测试之后、打印汇总之前插入：

```python
# ================================================================== 12. 注释与命名约定

t.group("12. 注释语言、腐烂标记和跨模块公开名")

def _read(rel: str) -> str:
    return open(os.path.join(HERE, rel), "r", encoding="utf-8").read()

_lib_files = []
for _dir, _names, _files in os.walk(os.path.join(HERE, "tvuitree")):
    for _name in _files:
        if _name.endswith(".py"):
            _lib_files.append(os.path.join(_dir, _name))

for path in _lib_files:
    rel = os.path.relpath(path, HERE).replace("\\", "/")
    src = open(path, "r", encoding="utf-8").read()
    t.ok("本脚本" not in src, f"{rel} 用「本工具」而不是「本脚本」")
    t.ok("设计原则第" not in src, f"{rel} 不引用已经不存在的文件头设计原则")
    t.ok(not src.startswith("#!/usr/bin/env python3"),
         f"{rel} 不是入口脚本，去掉 shebang")
    t.ok("# -*- coding: utf-8 -*-" not in src, f"{rel} 不写冗余 coding 声明")

t.ok("# ---- CLI 公共参数 ----" not in _read("tvuitree/domain/component.py"),
     "component.py 不再留空的 CLI 分段标题")
t.ok("# ---- component 字符串处理 ----" not in _read("tvuitree/infrastructure/adb.py"),
     "adb.py 不再留空的 component 分段标题")
obs_doc = (domain_observation.__doc__ or "")
t.ok("Page observation" in obs_doc, "observation 模块文档是英文一行")
t.ok("采集接口" not in obs_doc, "domain/observation 不声称自己负责采集")
mcp_src = _read("tvuitree/interfaces/mcp.py")
t.ok("宿主通过 stdio 启动本文件" not in mcp_src,
     "mcp 模块文档不再说直接用本文件启动")
t.ok("main.py mcp" in mcp_src, "mcp 模块文档写明由 main.py mcp 启动")
snap_src = _read("tvuitree/infrastructure/snapshot.py")
t.ok("dumpsys → a11y → dumpsys" in snap_src or "先 dumpsys、再 a11y、再 dumpsys" in snap_src,
     "snapshot() 文档写清三次读取顺序")
```

第 12 节先只放上面这些断言。Task 2 再往同一组补公开名断言。

- [ ] **Step 2: 跑自检，确认第 12 节失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1；第 12 节出现「本脚本」「设计原则」「shebang」「采集接口」「宿主通过 stdio」等失败。第 0–11 节仍通过。

- [ ] **Step 3: 改生产注释（最小集合，按下表逐条替换）**

`tvuitree/domain/observation.py` 删掉第 1–2 行 shebang 和 coding，模块文档改成：

```python
"""Page observation summaries for language models."""
```

`tvuitree/interfaces/mcp.py` 删掉 shebang 和 coding，模块文档改成：

```python
"""MCP tools for TV observation.

Host starts the server with `main.py mcp` over stdio. Tools read TV state,
the full tree and screenshots; they do not send keys. The only write is
`set_default_device` updating config.json. CLI and MCP share the application
observation and screenshot services.
"""
```

`tvuitree/infrastructure/adb.py` 删掉 shebang 和 coding；删掉文件末尾空的 `# ---- component 字符串处理 ----`（约第 186 行，下面没有代码）。

`tvuitree/domain/component.py` 删掉文件末尾空的 `# ---- CLI 公共参数 ----`（约第 37 行）。

`tvuitree/domain/tree/models.py` 把 `Node` 上「原因见文件头设计原则第 6 条」改成：

```python
    # 注意：这里**没有** text / desc 字段。
    # `dumpsys activity top` 的 View 树不携带文字（ViewDebug 不调 getText()），
    # 本工具也不做跨源回填：文字只以 a11y 读数为准，避免两个来源 silently 合成。
```

同文件 `NODE_RE_POST_NAME` 上方英文注释改成：

```python
# Android 16 的 ViewDebug 可能把可选的外部 name 放在实例块后面，
# 例如 DecorView{abc ...}[MainSettings]。
```

`tvuitree/domain/screenshot.py` 两处「本脚本」改为「本工具」：`compare_focus` 文档（约第 131 行）和 `_scale_factors` 文档（约第 220 行，Task 2 会把它改名为 `scale_factors`）。`walk` 文档保持中文。

`tvuitree/infrastructure/snapshot.py` 的 `snapshot()` 文档改为：

```python
    """抓同一时刻的两棵树：dumpsys → a11y → dumpsys，间隔尽量短，并记录前后一致性。"""
```

把下列英文函数/类文档译成中文（内容不变，只换语言）：

| 位置 | 新文档 |
|---|---|
| `domain/visible.py` `select_visible` | `"""按当前屏幕坐标证据给出可见控件摘要，保留焦点和可操作信息。路径仍指向原始全量树；只有 a11y 屏幕读数能主张可见，dumpsys 几何不得冒充屏幕读数。"""` |
| `application/observation.py` `collect_visible` | `"""从实时采集或已保存的全量 JSON 得到可见树投影。"""` |
| `application/screenshot.py` `render_focus_png` | `"""画一个红色 a11y 焦点框；焦点不唯一时原样返回 PNG。"""` |
| `application/connection.py` `connection_options` | `"""显式参数覆盖 config 默认值，供 CLI 与 MCP 共用。"""` |
| `application/connection.py` `update_default_device` | `"""校验并写入新的默认目标；config 里其他字段保持原样。"""` |
| `application/connection.py` `connect_device` | `"""返回已连接设备或 None；文案属于 interfaces。"""` |
| `infrastructure/device_config.py` `load_device_config` | `"""每次连接都重新读配置，使文件改动对下一次调用生效。"""` |
| `infrastructure/device_config.py` `save_device_config` | `"""原子替换配置文件，写入失败时保留旧文件。"""` |
| `infrastructure/image.py` `focus_border_width` | `"""按 PNG 高度缩放 MCP 焦点线宽（1080p 时为 6 像素）。"""` |
| `infrastructure/image.py` `draw_boxes_png` | `"""用同一套画框逻辑渲染，返回 PNG 字节，不留下成品文件。"""` |
| `interfaces/mcp.py` `_raw_node` | `"""把观察结果里的 path 解析回全量树节点。"""` |
| `interfaces/mcp.py` `_focus_labels` | `"""从焦点控件子树挑一个短标题和可选副标题。"""` |
| `interfaces/mcp.py` `_focus_info` | `"""返回焦点节点及其可见语义标签，不含树上下文。"""` |

`tests/selftest_tree.py` 和 `scripts/` 保留 shebang / coding（它们是入口脚本）。测试正文里提到「本脚本」指自检自己，保留。

- [ ] **Step 4: 再跑自检**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 第 12 节通过；全文退出码 0。`mcp.py`、`observation.py`、`adb.py` 都去掉 shebang 和 coding。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree tests/selftest_tree.py
git commit -m "Normalize comment language and remove stale section markers"
```

提交说明末尾加：

```
Co-Authored-By: Claude Code <noreply@anthropic.com>
```

---

### Task 2: 跨模块私有名改为公开名

**Files:**
- Modify: `tvuitree/domain/tree/models.py`、`parsing.py`
- Modify: `tvuitree/domain/observation.py`、`visible.py`、`screenshot.py`
- Modify: `tvuitree/infrastructure/image.py`
- Modify: `tvuitree/interfaces/json_io.py`、`observe.py`、`tree.py`、`visible.py`
- Test: `tests/selftest_tree.py` 第 12 节追加断言

**Interfaces:**
- Consumes: Task 1 的第 12 节测试组
- Produces: 上表「旧 → 新」中除 `pick_block` / `clip_to_chain` / `run_align` / `build_unified` / `JsonNode` 以外的重命名（那些在 Task 3–5）

- [ ] **Step 1: 追加会失败的导入断言**

在第 12 节末尾加：

```python
t.ok(hasattr(models, "record_anomaly"), "跨模块的解析告警入口叫 record_anomaly")
t.ok(not hasattr(models, "_anomaly"), "不再导出 _anomaly")
t.ok(hasattr(domain_observation, "node_summary"), "节点摘要是公开函数")
t.ok(not hasattr(domain_observation, "_node_summary"), "不再导出 _node_summary")
t.ok(hasattr(screenshot, "to_pixel") and hasattr(screenshot, "scale_factors"),
     "像素换算是公开函数")
t.ok(not hasattr(screenshot, "_px") and not hasattr(screenshot, "_scale_factors"),
     "不再导出 _px / _scale_factors")
from tvuitree.interfaces import json_io
t.ok(hasattr(json_io, "emit_json") and hasattr(json_io, "load_full_json"),
     "JSON 读写是公开函数")
t.ok(not hasattr(json_io, "_emit") and not hasattr(json_io, "_load_full"),
     "json_io 不再导出 _emit / _load_full")
```

- [ ] **Step 2: 跑自检，确认新断言失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1；失败信息为 `record_anomaly` / `node_summary` / `to_pixel` / `emit_json` 不存在。第 12 节 Task 1 的断言仍通过。

- [ ] **Step 3: 重命名（只改名字，不改逻辑）**

`models.py`：`def _anomaly(...)` 改为 `def record_anomaly(...)`。

`parsing.py` 的 import 和全部 `_anomaly(` 调用改为 `record_anomaly(`。

`observation.py`：`def _node_summary` 改为 `def node_summary`；文件内全部调用一起改。

`visible.py`：

```python
from tvuitree.domain.observation import node_summary
```

并把 `_node_summary(` 调用改为 `node_summary(`。

`screenshot.py`：`_px` → `to_pixel`，`_scale_factors` → `scale_factors`。

`infrastructure/image.py`：

```python
from tvuitree.domain.screenshot import to_pixel, scale_factors
```

所有 `_px(` / `_scale_factors(` 改为新名。

`json_io.py`：`_emit` → `emit_json`，`_load_full` → `load_full_json`。

`observe.py` / `tree.py` / `visible.py`：

```python
from .json_io import emit_json, load_full_json
```

并把 `_emit(` / `_load_full(` 改为新名。

不要改 `interfaces/timing.py` 的 `_emit`。

- [ ] **Step 4: 再跑自检**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 0。`pyflakes` 无未定义名。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree tests/selftest_tree.py
git commit -m "Rename cross-module helpers to public names"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 3: 去掉死参数、死分支和模块级可变告警表

**Files:**
- Modify: `tvuitree/domain/tree/matching.py`、`capture.py`、`parsing.py`、`models.py`、`output.py`
- Modify: `tvuitree/application/observation.py`、`input.py`
- Test: `tests/selftest_tree.py` 第 1、2、4、12 节（`run_align(..., True)` 在第 4 节，约 675、707 行）

**Interfaces:**
- Consumes: Task 2 的 `record_anomaly`
- Produces:
  - `clip_to_chain(node: Node) -> Optional[tuple]`
  - `run_align(snap: dict) -> tuple`
  - `build_unified(u2_roots: list, view_roots: list, screen: Optional[tuple]) -> list`
  - `parse_dumpsys_top(raw: str, anomalies: Optional[list] = None) -> list`：不传 `anomalies` 时用**局部**空列表，不写模块全局
  - 不再有 `models.PARSE_ANOMALIES`
  - `send_sequence(...) -> Iterator[tuple[str, str | None]]`

- [ ] **Step 1: 先写第 12 节的签名断言（调用点先不要改）**

自检是顺序脚本：断言失败只记一笔，**未捕获的 TypeError 会让整场退出、第 12 节跑不到**。所以这一步只改第 12 节和**不改变调用参数个数**的第 1 节。`clip_to_chain` / `run_align` / `build_unified` 的调用点留到 Step 3 和生产代码一起改。

第 1 节把三处 `models.PARSE_ANOMALIES` 改成局部列表（`parse_dumpsys_top` 已经接受可选第二参，这一步立刻变绿，用来钉死「调用方传入列表」；模块全局仍在，第 12 节会抓它）：

```python
bad_anom: list = []
bad_blocks = parsing.parse_dumpsys_top(BAD, bad_anom)
t.eq(len(bad_blocks), 1, "畸形 dump 仍能出段（不因个别行放弃整棵树）")
t.ok(any("bounds" in w for _, _, w in bad_anom),
     "「有字段却没解析出 bounds」要记成解析告警", f"实际告警 {bad_anom}")
BAD2 = "\n".join([
    "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0",
    "    View Hierarchy:",
    "      DecorView@a1[X]",
    "         com.demo.T{bbb V.E...... ......ID 0,0-10,10}",
    "",
])
indent_anom: list = []
parsing.parse_dumpsys_top(BAD2, indent_anom)
t.ok(any("整数倍" in w for _, _, w in indent_anom),
     "缩进不是 2 的倍数要记成解析告警（层级可能错位，不能默默吞掉）",
     f"实际告警 {indent_anom}")
clean_anom: list = []
parsing.parse_dumpsys_top(DUMPSYS, clean_anom)
t.eq(clean_anom, [], "正常 dump 不该产生任何解析告警")
```

第 12 节追加：

```python
t.ok(not hasattr(models, "PARSE_ANOMALIES"),
     "解析告警列表由调用方传入，不再放模块全局")
import inspect
t.eq(list(inspect.signature(matching.clip_to_chain).parameters), ["node"],
     "clip_to_chain 不再接收未使用的 screen")
t.eq(list(inspect.signature(capture.run_align).parameters), ["snap"],
     "run_align 不再接收未使用的 quiet")
t.eq(list(inspect.signature(matching.build_unified).parameters),
     ["u2_roots", "view_roots", "screen"],
     "build_unified 不再接收未使用的 AlignStats")
from typing import get_type_hints
from collections.abc import Iterator
hints = get_type_hints(remote_input.send_sequence)
t.ok(hints.get("return") == Iterator[tuple[str, str | None]]
     or str(hints.get("return")).startswith("collections.abc.Iterator"),
     "send_sequence 的返回类型是 Iterator，不是 list")
```

顶部已有 `from tvuitree.application import input as remote_input`，不要再导一次。`get_type_hints` 会求值注解；`Iterator[tuple[str, str | None]]` 与现在的 `list[...]` 不相等即可。

- [ ] **Step 2: 跑自检，确认失败原因是旧签名 / 全局仍在**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1。第 1 节已绿（局部列表）。第 12 节失败：`PARSE_ANOMALIES` 仍在、`clip_to_chain` 参数含 `screen`、`run_align` 参数含 `quiet`、`build_unified` 参数含 `st`、`send_sequence` 返回类型仍是 `list`。第 2 / 4 节仍按旧签名调用，不能 TypeError。不要在这一步改生产代码去让测试“凑绿”。

- [ ] **Step 3: 改生产代码**

`matching.py` `clip_to_chain`：

```python
def clip_to_chain(node: Node) -> Optional[tuple]:
    return _clip_ancestors(node)
```

所有 `clip_to_chain(x, None)` 改为 `clip_to_chain(x)`（`matching.py` 约 188、360 行；`output.py` 约 82、94 行；`tests/selftest_tree.py` 约 445 行）。

`matching.py` `_align_children` 里 `if ways[m][n] != 1:` 块删掉内层 `if U and V:`（外层已保证两者非空），直接：

```python
    if ways[m][n] != 1:
        st.seq_refused.append((v, u, "无解" if ways[m][n] == 0 else "多解（歧义）"))
        return
```

`matching.py` `build_unified` 去掉 `st` 参数：

```python
def build_unified(u2_roots: list, view_roots: list,
                  screen: Optional[tuple]) -> list:
```

`output.py` 两处调用改为 `build_unified(u2_roots, view_roots, _scr)` 和 `build_unified(u2_roots, [], None)`。`tests/selftest_tree.py` 第 4 节（约 555 行）改为：

```python
uni = matching.build_unified(FX["u2_roots"], FX["view_roots"], SCR)
```

`capture.py`：删掉 `_flat`；`run_align` 改为只接收 `snap`；把 `u_nodes, v_nodes = u2_all(u2_roots), _flat(view_roots)` 改成 `u_nodes, v_nodes = u2_all(u2_roots), list(iter_nodes(view_roots))`。删掉 `quiet` 形参（当前函数体从未读这个参数）。

`application/observation.py`：`run_align(snap, quiet)` 改为 `run_align(snap)`。`tests/selftest_tree.py` 第 4 节两处 `capture.run_align(mm_snap, True)` / `capture.run_align(nest_snap, True)`（约 675、707 行）改为单参数。

`capture.py` `hierarchy_drift`：`la == lb` 已返回；长度不同已返回；等长且 `zip` 穷尽后两序列必然相等，最后的 `return True, "内容不同（顺序差异）"` 不可达。循环后改成：

```python
    raise AssertionError("hierarchy_drift: equal-length lists compared unequal")
```

`models.py`：删除 `PARSE_ANOMALIES: list = []`。`record_anomaly` 改为必须传入列表：

```python
def record_anomaly(lineno: int, text: str, why: str, anomalies: list) -> None:
    if len(anomalies) < 50:
        anomalies.append((lineno, text.strip()[:160], why))
```

`parsing.py`：去掉对 `PARSE_ANOMALIES` 的导入。`parse_dumpsys_top`：

```python
    target: list = [] if anomalies is None else anomalies
    target.clear()
```

`parse_node_line` 签名仍是 `anomalies: Optional[list] = None`（第 1 节 `parse_node_line(...)` 不传列表）。只在 `anomalies is not None` 时调用 `record_anomaly`：

```python
        if n.bounds is None:
            if anomalies is not None:
                record_anomaly(lineno, text, f"该行有字段但没解析出 bounds：{rest!r}", anomalies)
    elif m.group("vhash"):
        if anomalies is not None:
            record_anomaly(lineno, text, "有 {hash} 但后面没有任何字段", anomalies)
```

`application/input.py` 已有 `from __future__ import annotations`，把返回类型改成 `Iterator`：

```python
from collections.abc import Iterator

def send_sequence(adb, keys: list[str], *, delay: float = 0.5, repeat: int = 1,
                  sleep=time.sleep) -> Iterator[tuple[str, str | None]]:
```

不要从 `typing` 再导一次 `Iterator`（3.10 里 `typing.Iterator` 仍可用，但本仓库新代码用 `collections.abc`）。

- [ ] **Step 4: 再跑自检**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 0。第 1 节畸形 dump 仍报 bounds / 缩进告警。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree tests/selftest_tree.py
git commit -m "Drop unused parameters and the mutable parse-anomaly global"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 4: JSON 读取分层与字节计数

**Files:**
- Modify: `tvuitree/infrastructure/image.py`
- Modify: `tvuitree/interfaces/json_io.py`、`shot.py`
- Test: `tests/selftest_tree.py` 第 7 节附近（`load_tree` 断言处）和第 12 节

**Interfaces:**
- Consumes: Task 2 的 `emit_json` / `load_full_json`
- Produces:
  - `load_full_json(path: str) -> dict`：文件错误抛 `OSError` 子类，内容不对抛 `ValueError`（含非 dict）
  - `image.load_tree(path)` 内联同一段校验，抛 `ValueError`/`OSError`，不再 `raise SystemExit`，也不从 infrastructure 导入 interfaces
  - `run_shot` 改用 `load_full_json`，继续 `except (OSError, ValueError, TypeError)`
  - `emit_json` 提示里的数字是写入文件的 UTF-8 字节数，含末尾换行：`len((text + "\n").encode("utf-8"))`

- [ ] **Step 1: 写失败测试**

在现有 `t.eq(image.load_tree(FULL_PATH)["mode"], "full", ...)` 之后插入。文件顶部没有 `import argparse`，这一步加上。`run_shot` 的 Namespace 必须带 `add_conn_args` 的字段，否则后面若走到 `connect_for_cli` 会 `AttributeError`：

```python
import argparse
from tvuitree.interfaces.shot import run_shot

array_json = os.path.join(TD, "array.json")
with open(array_json, "w", encoding="utf-8") as f:
    f.write("[1, 2, 3]")
raised = None
try:
    image.load_tree(array_json)
except Exception as error:
    raised = error
t.ok(isinstance(raised, ValueError),
     "非对象 JSON 由 load_tree 变成 ValueError，不是 SystemExit/AttributeError",
     f"实际 {type(raised).__name__}: {raised}")
t.ok("tree" in str(raised), "错误要说明缺少 tree")

shot_rc = None
shot_error = None
try:
    shot_rc = run_shot(argparse.Namespace(
        json_path=array_json, image=None, out=os.path.join(TD, "no.png"),
        draw="focus", source="a11y", width=1, quiet=True, no_color=True,
        TV_IP_Address=None, port=None, adb=None, no_connect=True,
    ))
except Exception as error:
    shot_error = error
t.ok(shot_rc == 1 and shot_error is None,
     "shot 遇到非对象 JSON 退出码 1，不 traceback",
     f"rc={shot_rc} error={type(shot_error).__name__ if shot_error else None}: {shot_error}")
```

`run_shot` 必须包在 `try` 里：当前 `load_tree` 对数组抛 `AttributeError`，而 `run_shot` 只接 `OSError/ValueError/TypeError`，裸调用会让整场自检退出、第 12 节跑不到。

第 12 节追加（`TD` 在第 6 节创建，`shutil.rmtree(TD)` 在第 12 节之后的收尾，可以直接用；`json_io` 在 Task 2 已导入则不要重复）：

```python
from tvuitree.interfaces import json_io
_buf = io.StringIO()
_out = os.path.join(TD, "emit_zh.json")
with contextlib.redirect_stderr(_buf):
    json_io.emit_json({"tree": [], "note": "中文"}, _out)
err = _buf.getvalue()
payload = open(_out, "r", encoding="utf-8").read()
t.ok(f"（{len(payload.encode('utf-8'))} 字节）" in err,
     "emit_json 按写入文件的 UTF-8 字节数提示（含末尾换行）", repr(err))
```

- [ ] **Step 2: 跑自检，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: `load_tree` 断言失败（`raised` 是 `AttributeError` 或 `SystemExit`，不是 `ValueError`）；`run_shot` 断言失败（捕获到 `AttributeError`，`shot_rc is None`）；`emit_json` 的 stderr 数字等于字符数而不是 UTF-8 字节数。整场不要 TypeError 退出。

- [ ] **Step 3: 实现**

`json_io.py` 的 `emit_json` 把 `len(text)` 改成 `len((text + "\n").encode("utf-8"))`（与写入内容一致）。`load_full_json` 保持现有校验，已经对非 dict 抛 `ValueError`。

`image.load_tree` 去掉外层 `except Exception: raise SystemExit`，并在 `obj.get` 之前先确认是 dict：

```python
def load_tree(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError(f"{path} 里没有 tree，不像是本工具输出的控件树 JSON。")
    return obj
```

`shot.py` 改用 `load_full_json`，与 observe/tree/visible 一致：

```python
from .json_io import load_full_json
from tvuitree.infrastructure.image import capture
...
        obj = load_full_json(args.json_path)
```

测试里 `image.load_tree(FULL_PATH)` 和新建的数组用例继续有效。`image.py` 仍 `import json`，不要删。

- [ ] **Step 4: 再跑自检**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 0。`pyflakes` 无未使用导入。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree tests/selftest_tree.py
git commit -m "Load tree JSON without SystemExit and report UTF-8 byte size"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 5: 结构整理（JsonNode、pick_block、共享常量）

**Files:**
- Modify: `tvuitree/domain/screenshot.py`、`tree/parsing.py`、`tree/models.py`、`tree/output.py`
- Modify: `tvuitree/infrastructure/snapshot.py`
- Modify: `tvuitree/interfaces/mcp.py`、`cli.py`、`tree.py`
- Create: `tvuitree/domain/__init__.py`
- Test: `tests/selftest_tree.py` 第 7 节（`screenshot.Node` 构造）和第 12 节

**Interfaces:**
- Consumes: Task 2–4 的公开名
- Produces:
  - `screenshot.JsonNode`（不再有 `screenshot.Node`）
  - `parsing.pick_block(blocks, component) -> tuple`
  - 不再有 `pick_block_ex`
  - `models.Node.drawn` / `models.Node.context_clickable` 只读属性
  - `mcp.FOCUS_NODE_FIELDS = ("class", "resource_id", "package", "bounds", "bounds_kind", "source")`
  - CLI `--max-nodes` 与 MCP `max_nodes` 默认都是 `DEFAULT_MAX_NODES`
  - `interfaces/tree.py` 用一个递归函数数节点
  - pydantic 与 mcp 在同一 `try`

- [ ] **Step 1: 写失败断言**

第 12 节追加（`inspect` 在 Task 3 已导入则不要重复；`mcp as mcp_interface` 已在第 8 节导入，这里用它或再 `from tvuitree.interfaces import mcp as mcp_mod` 一次均可，不要混用两个别名）：

```python
from tvuitree.domain.observation import DEFAULT_MAX_NODES
from tvuitree.interfaces.cli import build_parser
from tvuitree.interfaces import mcp as mcp_mod

mcp_src = _read("tvuitree/interfaces/mcp.py")
t.ok(hasattr(screenshot, "JsonNode"), "JSON 树包装类叫 JsonNode")
t.ok(not hasattr(screenshot, "Node"), "screenshot 不再导出与 dumpsys Node 撞名的 Node")
t.ok(hasattr(parsing, "pick_block") and not hasattr(parsing, "pick_block_ex"),
     "选 ACTIVITY 段的函数叫 pick_block")
t.ok(hasattr(models.Node, "drawn") and hasattr(models.Node, "context_clickable"),
     "drawn / context_clickable 是 dumpsys Node 的派生属性")
cli_src = _read("tvuitree/interfaces/cli.py")
t.ok("DEFAULT_MAX_NODES" in cli_src,
     "CLI --max-nodes 默认值引用 DEFAULT_MAX_NODES，不另写 80")
t.ok("max_nodes: int = DEFAULT_MAX_NODES" in mcp_src,
     "MCP observe_tv.max_nodes 默认值引用同一常量")
t.eq(build_parser().parse_args(["observe"]).max_nodes, DEFAULT_MAX_NODES,
     "解析后的 CLI 默认值等于 DEFAULT_MAX_NODES")
t.eq(inspect.signature(mcp_mod.observe_tv).parameters["max_nodes"].default,
     DEFAULT_MAX_NODES, "运行时 MCP 默认值等于同一常量")
t.eq(mcp_mod.FOCUS_NODE_FIELDS,
     ("class", "resource_id", "package", "bounds", "bounds_kind", "source"),
     "焦点压缩字段只定义一次")
pyd = mcp_src.find("from pydantic import Field")
mcp_imp = mcp_src.find("from mcp.server.fastmcp")
try_pos = mcp_src.find("try:")
t.ok(try_pos != -1 and pyd > try_pos and mcp_imp > try_pos,
     "pydantic 和 mcp 都在 try 里导入，缺依赖时同一条安装提示")
```

这一步**不要**改第 7 节 `screenshot.Node(...)`：`JsonNode` 还不存在，裸改构造名会 `AttributeError` 整场退出。调用点留到 Step 3。

- [ ] **Step 2: 跑自检，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: `JsonNode` / `pick_block` / `FOCUS_NODE_FIELDS` / `drawn` 属性不存在；CLI 与 MCP 源码里还没有 `DEFAULT_MAX_NODES`。数值断言（默认值等于 80）当前就会绿，不能单独当变红信号。

- [ ] **Step 3: 实现**

`screenshot.py`：`class Node` 改名为 `class JsonNode`；`collect` / `compare_focus` / `flatten` / `is_actionable` 的类型和构造全部改用 `JsonNode`。`walk` 保持，它遍历的是 dict。同一提交里把 `tests/selftest_tree.py` 约 915 行 `screenshot.Node` 改成 `screenshot.JsonNode`。

`parsing.py`：`def pick_block_ex` 改名为 `def pick_block`。

`snapshot.py`：`from tvuitree.domain.tree.parsing import parse_dumpsys_top, pick_block`，调用 `pick_block(...)`。

`models.py` 在 `clickable` 附近增加：

```python
    @property
    def drawn(self) -> bool:
        return bool(self.flags1) and len(self.flags1) > 3 and self.flags1[3] == "D"

    @property
    def context_clickable(self) -> bool:
        return bool(self.flags1) and len(self.flags1) > 8 and self.flags1[8] == "X"
```

`output.py` 两处手写 `bool(v.flags1 and len(v.flags1) > 3 ...)` 改为 `v.drawn` / `v.context_clickable`（`view_extra` 和 `view_fields`）。

`interfaces/mcp.py` 在 `FOCUS_SCREENSHOT_DIR = ...` 后：

```python
FOCUS_NODE_FIELDS = (
    "class", "resource_id", "package", "bounds",
    "bounds_kind", "source",
)
```

`_focus_info` 里两处 `fields = (...)` 改为使用 `FOCUS_NODE_FIELDS`。

把

```python
from pydantic import Field
...
try:
    from mcp.server.fastmcp import FastMCP, Image
except ImportError as exc:
    raise SystemExit(...) from exc
```

改成：

```python
try:
    from pydantic import Field
    from mcp.server.fastmcp import FastMCP, Image
except ImportError as exc:
    raise SystemExit(
        "缺少 MCP 依赖，请在仓库环境执行：python -m pip install 'mcp>=1.28,<2'"
    ) from exc
```

`cli.py`：

```python
from tvuitree.domain.observation import DEFAULT_MAX_NODES
...
    observe.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES, metavar="N",
                         help=f"页面摘要节点上限（默认 {DEFAULT_MAX_NODES}）")
```

`mcp.py` 顶部把 `from tvuitree.domain.observation import error_observation` 改成 `from tvuitree.domain.observation import DEFAULT_MAX_NODES, error_observation`。`observe_tv` 的默认值：

```python
    max_nodes: int = DEFAULT_MAX_NODES,
```

`interfaces/tree.py` 把 `_tree_size` / `_desc_count` 收成：

```python
def _tree_size(nodes: list) -> int:
    """整棵树的节点数（含后代）。"""
    return sum(1 + _tree_size(n.get("children") or []) for n in nodes)
```

删掉 `_desc_count`。

Create `tvuitree/domain/__init__.py`：

```python
"""TV UI observation domain layer."""
```

- [ ] **Step 4: 再跑自检**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 0。第 8 节 MCP schema 仍含 `TV_IP_Address`，`max_nodes` 不在连接参数 schema 里（它是 observe_tv 自己的参数，本任务不改 schema 形状）。

- [ ] **Step 5: Commit**

```powershell
git add tvuitree tests/selftest_tree.py
git commit -m "Disambiguate Node types and share observation defaults"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 6: 文档与测试里的旧脚本名

**Files:**
- Modify: `tests/selftest_tree.py`（第 7 节职责边界断言的说明文字、夹具注释）
- Modify: `AGENTS.md`（Structure 段补注释约定）
- 不改 `README.md`「旧命令迁移」表（`python tv_shot.py` 是历史入口，不是当前路径）

**Interfaces:**
- Consumes: 现有路径 `infrastructure/image.py`、`application/input.py`
- Produces: 测试说明与 AGENTS 和代码分层一致；断言比较的源字符串不变（仍检查 `screencap` 只出现在 `image.py`）

- [ ] **Step 1: 写失败断言（说明文字，不是行为）**

把第 7 节这些断言的**说明字符串**改成现分层名字（比较的源码条件不变）：

```python
t.ok("screencap" not in tree_src and "screencap" not in core_src,
     "树采集实现绝不截图（截图是 infrastructure/image.py 的事）")
t.ok("input keyevent" not in tree_src and "input keyevent" not in core_src,
     "树采集实现绝不发按键（按键是 application/input.py 的事）")
t.ok("fetch_u2" not in shot_src and "parse_dumpsys_top" not in shot_src,
     "infrastructure/image.py 不自己取树（它只读 JSON）")
t.ok("build_full_json" not in input_src, "application/input.py 与取树无关")
```

夹具注释 `tv_shot「祖先链溢出容器」` 改为 `画框「祖先链溢出容器」`。

`t.has(OBJ, "captured_at", "要有采集时刻（tv_shot 靠它判断截图与取树是否同时刻）")` 改为 `要有采集时刻（shot 靠它判断截图与取树是否同时刻）`。

第 12 节追加（用英文短语，与 AGENTS.md 现有语言一致）：

```python
agents = _read("AGENTS.md")
t.ok("module docstrings are one English line" in agents
     and "function/class docstrings and inline comments are Chinese" in agents,
     "AGENTS.md 写明注释语言约定")
```

这一步会失败，因为 AGENTS 还没有这两句。第 7 节说明字符串的改动本身不会让断言变红（它们是失败消息，不是被比较的源码）。

- [ ] **Step 2: 跑自检，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 第 12 节因 AGENTS 缺少约定句失败。

- [ ] **Step 3: 改 AGENTS.md**

在 `## Structure` 第一段之后插入：

```markdown
Comment language: module docstrings are one English line; function/class docstrings and inline comments are Chinese. User-facing CLI/MCP strings stay Chinese. Do not leave empty section banners or comments that refer to a deleted file-header principle list. Library modules under `tvuitree/` do not use shebangs or coding cookies; `main.py`, `tests/selftest_tree.py`, and `scripts/` may.
```

`generator` 字段值 `tv_tree.py` 不要改。README 迁移表保留 `python tv_shot.py` / `python tv_input.py`。

- [ ] **Step 4: 再跑完整检查**

Run:

```powershell
$py = '.\.venv\Scripts\python.exe'
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
& $py -m py_compile $pythonFiles
& $py -m pyflakes $pythonFiles
& $py tests/selftest_tree.py
& $py main.py --help
& $py main.py tree --prune-list
git diff --check
```

Expected: 全部退出码 0；`--help` / `--prune-list` 输出与改前同一套开关名。

可选（有 `_temp/e2e/full.json` 时，不作为任务通过条件）：

```powershell
& $py main.py observe --from-json _temp/e2e/full.json --out NUL
& $py main.py visible --from-json _temp/e2e/full.json --out NUL
& $py main.py tree --from-json _temp/e2e/full.json --mode slim --out NUL
```

Expected: 退出码 0。若存在 `_temp/golden/golden.py`，可跑 `python _temp/golden/golden.py check`；金样 stderr 里的「字节」数字若因 Task 4 变化，用 `python _temp/golden/golden.py make` 重建基线（该目录 gitignore，不提交）。

- [ ] **Step 5: Commit**

```powershell
git add tests/selftest_tree.py AGENTS.md
git commit -m "Document comment language and replace legacy script names in tests"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。计划文档在开始实现前已经单独提交，这一步不要再 `git add` 本文件。

---

## Self-review

1. **Spec coverage:** 审核里要做的项都有任务：语言约定与腐烂注释（1），跨模块 `_` 名（2），死参数 / 全局告警表 / 错误类型注解（3），`SystemExit` 分层与「字节」口误（4），撞名 `Node`、`pick_block_ex`、重复常量、mcp 导入顺序（5），文档与测试文案（6）。明确不做的项写在 Out of scope。
2. **Placeholder scan:** 无 TBD / 占位计算。Task 5 用 `inspect.signature` 锁 `max_nodes` 默认值。
3. **Type consistency:** 公开名对照表与 Task 2–5 的 Produces 一致；`timing._emit` 不改。
4. **Review Focus:** 五条都挂到了 Task 3–5 的测试。`run_align` 的测试调用在第 4 节（不是第 3 节）。`golden.py` 已用 `getattr(parsing, "pick_block") or getattr(..., "pick_block_ex")`，Task 5 重命名后不必改它。签名变更和 `screenshot.JsonNode` 构造都留到与生产代码同一步，避免自检 TypeError 整场退出。`run_shot` 的数组用例在变红阶段用 `try` 接住当前的 `AttributeError`。
