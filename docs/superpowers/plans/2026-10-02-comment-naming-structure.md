# 注释、命名与结构规范 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按仓库现有习惯把注释语言、公开命名和分层边界收齐，不改 JSON 字段、CLI 退出码、MCP schema，也不改配对 / 剪枝 / 画框的业务语义。

**Architecture:** 先修复 JSON 错误处理、缺依赖提示和解析默认路径的共享状态，再整理公开命名、结构和注释；行为修复与纯整理分别验证、提交。CLI 的 `shot` 经 interfaces 的 JSON 读取入口读树，infrastructure 不反向依赖 interfaces；跨模块 `_` 名和未用参数按调用点一起迁移，对外契约和业务判定保持原样。顺序自检的失败阶段只允许断言记失败，不能因缺少新属性、TypeError 或 SystemExit 中断；纯文案修改用审查与现有回归，不新增逐字措辞断言。

**Tech Stack:** Python 3.10+；离线自检 `tests/selftest_tree.py`（普通脚本，不是 pytest）；项目 venv `.\.venv\Scripts\python.exe`。

**Spec:** 延续 Claude Code 的 2026-10-02 仓库整理方案；本次修订依据用户确认的 Review：修复 Task 5 失败测试中断，覆盖 shot 缺文件/损坏 JSON 的 SystemExit 路径，保护金样基线，纠正现有 MCP 告警隔离的描述，减少纯文案断言，并在每个提交前执行完整检查。没有新增产品功能或业务规则。

## Global Constraints

- 不改变 JSON 字段名、字段口径、CLI 退出码（2/3/1）、MCP 工具名、输入 schema、返回键集合。
- 不把 `TV_IP_Address`（CLI 旗标、MCP 参数、`config.json` 键、`ConnectionOptions` 字段）改成 PEP8 名字。
- 不把 `full JSON` 的 `generator` 从 `tv_tree.py` 改掉。
- 不改 R0–R3、剪枝认领顺序、画框「逐像素对齐、不加偏移」的判定。
- 依赖只向内：domain 不碰设备、文件、终端、MCP、Pillow、uiautomator2。
- `collect_full_json` 必须继续在函数体内 `from tvuitree.infrastructure.snapshot import snapshot`，测试第 8 节在调用时 monkeypatch `snapshot.snapshot`。
- 模块文档一行英文；函数 / 类文档和行内注释用中文。较长的模块职责说明写在后续中文注释中，不把多行英文模块文档作为例外。用户可见字符串保持中文。
- Python 3.10+、四空格、UTF-8、新代码带类型注解。
- 检查命令用 `.\.venv\Scripts\python.exe`。自检是 `python tests/selftest_tree.py`，没有单测选择器。
- 原方案的执行目标仍是 `main`，不开分支、不提 PR。每个已完成阶段先通过完整检查，再精确暂存该阶段文件并审查 staged diff；不要把 `config.json` 的本机地址提交进去。计划修订后，用户已明确请求执行；实际执行记录见文末。
- `_temp/golden/` 是 gitignore 的真机金样，不作为本计划的必改文件；若本地有 `golden.py`，`pick_block_ex` 重命名后它已有 `getattr(..., "pick_block")` 回退。

## Review Focus

- `shot --json` 遇到缺文件、损坏 JSON、数组、null、缺 tree 或 tree 非列表：当前缺文件/损坏 JSON 在 load_tree 中抛 SystemExit，数组/null 在 obj.get 处抛 AttributeError。期望库读取抛 OSError/ValueError，CLI 退出码 1、stderr 有说明、无 traceback、不访问设备且不输出 PNG（Task 4）。
- `parse_dumpsys_top` 不传 anomalies 时仍使用模块级 PARSE_ANOMALIES。当前 collect_full_json 已为每次 CLI/MCP 调用创建独立列表，因此不声称现有 MCP 发生告警竞争；清理的是默认解析入口的共享状态。期望不同解析调用的告警互不改写，省略参数时只用局部列表（Task 3）。
- `clip_to_chain` 去掉未使用的 `screen` 后，漏改某个只传位置参数的调用方会 `TypeError`。期望：生产代码与自检全部改成单参数（Task 3）；`_temp/golden/golden.py` 不调用它。
- `emit_json` 把 `len(text)` 说成「字节」，中文 JSON 会少报。期望：按 UTF-8 字节数打印（Task 4）。
- interfaces/mcp.py 的 pydantic 导入在 try 外。只缺 mcp 时现有安装提示已经有效；缺 pydantic 时才会先抛未处理的 ImportError。期望模拟缺 pydantic 和缺 mcp 时都给统一安装提示、无 traceback；不卸载实际依赖（Task 4）。
- Task 5 的新 FOCUS_NODE_FIELDS 尚不存在时，测试必须通过 getattr(..., None) 记录失败，不能在调用 t.eq 前抛 AttributeError。金样任何 JSON/PNG 或非预期诊断差异都须失败，不能以整体 make 覆盖（Task 5 和金样审查步骤）。

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

## 实施顺序与基线

任务编号沿用原方案，实际按 **4 → 3 → 2 → 5 → 1 → 6** 执行，前两次提交处理行为问题，之后才提交命名、结构和文案整理。任务依赖按此顺序改写：Task 4 暂时使用 `_emit` / `_load_full`，Task 3 暂时使用 `_anomaly`；Task 2 再统一公开名并同步测试调用点。Task 4 先创建第 12 节及 `_read`，其他任务只往该节追加，不重复创建测试组。

- [x] **开始前记录状态并运行现有完整检查**

```powershell
git status --short
git branch --show-current
git log -1 --oneline
```

执行下一节完整检查。若基线已失败，记录实际失败并先定位，不把它算作新增失败测试。本次 Review 的基线是 main / 44f8c90、638 条断言通过；执行时必须重新核对，不能把历史结果当作当前结果。有可用金样时在任何生产代码修改前运行金样 check，保留 base 原件；已有基线失败须先解释。

## 每次提交前的完整检查

每个 Task 的提交步骤前都执行以下整块；每条外部命令后立即检查退出码，失败时停止，禁止只依据块末尾 git diff 的退出码提交。任务中的失败测试只运行自检，预期退出码 1；完成阶段才运行本块并要求全部为 0。

```powershell
$py = '.\.venv\Scripts\python.exe'
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
& $py -m py_compile $pythonFiles
if ($LASTEXITCODE -ne 0) { throw 'py_compile failed' }
& $py -m pyflakes $pythonFiles
if ($LASTEXITCODE -ne 0) { throw 'pyflakes failed' }
& $py tests/selftest_tree.py
if ($LASTEXITCODE -ne 0) { throw 'selftest failed' }
& $py main.py --help
if ($LASTEXITCODE -ne 0) { throw 'CLI help failed' }
& $py main.py tree --prune-list
if ($LASTEXITCODE -ne 0) { throw 'prune list failed' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
```

每个任务的 git add 只列本任务文件；随后执行 `git diff --cached --check`、`git diff --cached --stat`、`git diff --cached`。staged diff 不得混入 config、本计划的其他改动或下一任务的半成品；若已有其他暂存内容，先报告并保留，不擅自清空。原提交作者信息只保留在实际对应贡献的提交中。

---

### Task 1: 注释语言约定与腐烂注释

**Files:**
- Modify: `tvuitree/domain/observation.py`、`component.py`、`screenshot.py`、`tree/models.py`、`visible.py`
- Modify: `tvuitree/infrastructure/adb.py`、`image.py`、`device_config.py`、`snapshot.py`
- Modify: `tvuitree/application/connection.py`、`observation.py`、`screenshot.py`
- Modify: `tvuitree/interfaces/mcp.py`
- Validation: 现有完整检查及文案 diff 审查；不新增注释措辞测试

**Interfaces:**
- Consumes: 无
- Produces: 约定生效——模块文档英文一行；函数/类文档和注释中文；库模块无 shebang / coding 声明；不再出现「本脚本」「设计原则第 N 条」和空的分段标题。

- [x] **Step 1: 审查文案清理范围**

```powershell
rg -n '本脚本|设计原则第|^#!|coding: utf-8|CLI 公共参数|component 字符串处理' tvuitree
```

逐处核对是否为过时说明；不是运行时行为，不新增逐字措辞断言，不为翻译单独制造失败测试。清理后 rg 无匹配时退出码 1 是正常搜索结果；模块职责、采集顺序和证据限制由文案 diff 审查确认。

- [x] **Step 2: 改生产注释（最小集合，按下表逐条替换）**

`tvuitree/domain/observation.py` 删掉第 1–2 行 shebang 和 coding，模块文档改成：

```python
"""Page observation summaries for language models."""
```

`tvuitree/interfaces/mcp.py` 删掉 shebang 和 coding，模块文档改成：

```python
"""MCP tools for TV observation started with main.py mcp over stdio."""

# 服务读取 TV 状态、完整树和截图，不发送按键。
# 唯一的写操作是 set_default_device 修改 config.json 的默认设备。
# CLI 和 MCP 共用应用层的观察与截图服务。
```

`tvuitree/infrastructure/adb.py` 删掉 shebang 和 coding；删掉文件末尾空的 `# ---- component 字符串处理 ----`（约第 186 行，下面没有代码）。

`tvuitree/domain/component.py` 删掉文件末尾空的 `# ---- CLI 公共参数 ----`（约第 37 行）。

`tvuitree/domain/tree/models.py` 把 `Node` 上「原因见文件头设计原则第 6 条」改成：

```python
    # 注意：这里**没有** text / desc 字段。
    # `dumpsys activity top` 的 View 树不携带文字（ViewDebug 不调 getText()），
    # 本工具也不做跨源回填：文字只以 a11y 读数为准，避免两个来源的读数被静默合成。
```

同文件 `NODE_RE_POST_NAME` 上方英文注释改成：

```python
# Android 16 的 ViewDebug 可能把可选的外部 name 放在实例块后面，
# 例如 DecorView{abc ...}[MainSettings]。
```

`tvuitree/domain/screenshot.py` 两处「本脚本」改为「本工具」：`compare_focus` 文档和 `scale_factors` 文档（按实施顺序，Task 2 已将 `_scale_factors` 改名）。`walk` 文档保持中文。

`tvuitree/infrastructure/snapshot.py` 的 `snapshot()` 文档改为：

```python
    """连续采集两种来源：dumpsys → a11y → dumpsys，间隔尽量短，并记录前后层次的一致性。"""
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

`image.py` 的混合语言模块文档同步改成英文一行，画框约定仍保留在文件头中文注释中，既符合约定，也保留现有职责边界断言依赖的语义短语：

```python
"""PNG capture and drawing backed by Pillow."""

# 画框约定：框 = 读数，逐像素对齐、不加偏移。
```

将 draw_boxes 文档里的「几何约定见模块文档」改为「几何约定见文件头注释」。

`tests/selftest_tree.py` 和 `scripts/` 保留 shebang / coding（它们是入口脚本）。测试正文里提到「本脚本」指自检自己，保留。

- [x] **Step 3: 运行完整检查并审查文案 diff**

Run: 本计划「每次提交前的完整检查」中的整块命令。

Expected: 所有检查退出码 0；原有业务断言保持通过，diff 仅涉及注释、文档字符串和空标题。`mcp.py`、`observation.py`、`adb.py` 都去掉 shebang 和 coding。

- [x] **Step 4: 精确暂存并 Commit**

```powershell
git add tvuitree/domain/observation.py tvuitree/domain/component.py tvuitree/domain/screenshot.py tvuitree/domain/tree/models.py tvuitree/domain/visible.py tvuitree/infrastructure/adb.py tvuitree/infrastructure/image.py tvuitree/infrastructure/device_config.py tvuitree/infrastructure/snapshot.py tvuitree/application/connection.py tvuitree/application/observation.py tvuitree/application/screenshot.py tvuitree/interfaces/mcp.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'staged stat failed' }
git diff --cached
if ($LASTEXITCODE -ne 0) { throw 'staged diff review failed' }
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
- Modify: `tvuitree/interfaces/json_io.py`、`observe.py`、`tree.py`、`visible.py`、`shot.py`
- Test: `tests/selftest_tree.py` 第 12 节追加断言

**Interfaces:**
- Consumes: Task 4 创建的第 12 节测试组、Task 3 保留的 `_anomaly(..., anomalies)` 必传列表签名
- Produces: 上表「旧 → 新」中除 `pick_block` / `clip_to_chain` / `run_align` / `build_unified` / `JsonNode` 以外的重命名（那些在 Task 3–5）

- [x] **Step 1: 追加会失败的导入断言**

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

- [x] **Step 2: 跑自检，确认新断言失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1；失败信息为 record_anomaly / node_summary / to_pixel / emit_json 不存在；Task 3–4 的行为测试仍通过，汇总正常输出。

- [x] **Step 3: 重命名（只改名字，不改逻辑）**

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

不要改 `interfaces/timing.py` 的 `_emit`。本任务还要同步 Task 4 已写入测试的 `json_io._emit(...)` → `json_io.emit_json(...)`，及 shot 里的读取入口：

```python
from .json_io import load_full_json
```

将 run_shot 的 `_load_full(args.json_path)` 改为 `load_full_json(args.json_path)`；`image.load_tree` 不依赖任何 interfaces 导入。不要遗留仅测试还在调用旧 JSON 名字的情况。

- [x] **Step 4: 执行完整检查**

Run: 本计划「每次提交前的完整检查」中的整块命令。

Expected: 退出码 0。`pyflakes` 无未定义名。

- [x] **Step 5: 精确暂存并 Commit**

```powershell
git add tvuitree/domain/tree/models.py tvuitree/domain/tree/parsing.py tvuitree/domain/observation.py tvuitree/domain/visible.py tvuitree/domain/screenshot.py tvuitree/infrastructure/image.py tvuitree/interfaces/json_io.py tvuitree/interfaces/observe.py tvuitree/interfaces/tree.py tvuitree/interfaces/visible.py tvuitree/interfaces/shot.py tests/selftest_tree.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'staged stat failed' }
git diff --cached
if ($LASTEXITCODE -ne 0) { throw 'staged diff review failed' }
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
- Consumes: Task 4 创建的第 12 节；现有 `_anomaly` 暂不重命名（Task 2 统一迁移）
- Produces:
  - `clip_to_chain(node: Node) -> Optional[tuple]`
  - `run_align(snap: dict) -> tuple`
  - `build_unified(u2_roots: list, view_roots: list, screen: Optional[tuple]) -> list`
  - `parse_dumpsys_top(raw: str, anomalies: Optional[list] = None) -> list`：不传 `anomalies` 时用**局部**空列表，不写模块全局
  - 不再有 `models.PARSE_ANOMALIES`
  - `send_sequence(...) -> Iterator[tuple[str, str | None]]`

- [x] **Step 1: 先写第 12 节的签名断言（调用点先不要改）**

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

在 clean_anom 测试之后追加真实隔离检查。两条显式路径当前已经隔离，这是已有正确行为，不能宣称这些用例会变红；默认全局删除和旧签名断言才是本任务的失败信号。

```python
first_anomalies: list = []
second_anomalies: list = []
parsing.parse_dumpsys_top(BAD, first_anomalies)
first_saved = list(first_anomalies)
parsing.parse_dumpsys_top(DUMPSYS, second_anomalies)
t.ok(bool(first_saved), "畸形输入产生告警")
t.eq(second_anomalies, [], "另一调用的正常输入没有告警")
t.eq(first_anomalies, first_saved, "第二次显式解析不改写第一次告警")
parsing.parse_dumpsys_top(BAD)
parsing.parse_dumpsys_top(DUMPSYS)
t.eq(first_anomalies, first_saved, "默认解析入口也不改写显式告警列表")
```

当前 collect_full_json 的 anomalies 已经是每次调用新建的列表，保留这一行为；不增加为证明不存在的 MCP 竞争而写的并发测试。

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

- [x] **Step 2: 跑自检，确认失败原因是旧签名 / 全局仍在**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1。第 1 节已绿（局部列表）。第 12 节失败：`PARSE_ANOMALIES` 仍在、`clip_to_chain` 参数含 `screen`、`run_align` 参数含 `quiet`、`build_unified` 参数含 `st`、`send_sequence` 返回类型仍是 `list`。第 2 / 4 节仍按旧签名调用，不能 TypeError。不要在这一步改生产代码去让测试“凑绿”。

- [x] **Step 3: 改生产代码**

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

`models.py`：删除 `PARSE_ANOMALIES: list = []`。`_anomaly` 改为必须传入列表：

```python
def _anomaly(lineno: int, text: str, why: str, anomalies: list) -> None:
    if len(anomalies) < 50:
        anomalies.append((lineno, text.strip()[:160], why))
```

`parsing.py`：去掉对 `PARSE_ANOMALIES` 的导入。`parse_dumpsys_top`：

```python
    target: list = [] if anomalies is None else anomalies
    target.clear()
```

`parse_node_line` 签名仍是 `anomalies: Optional[list] = None`（第 1 节 `parse_node_line(...)` 不传列表）。只在 `anomalies is not None` 时调用 `_anomaly`：

```python
        if n.bounds is None:
            if anomalies is not None:
                _anomaly(lineno, text, f"该行有字段但没解析出 bounds：{rest!r}", anomalies)
    elif m.group("vhash"):
        if anomalies is not None:
            _anomaly(lineno, text, "有 {hash} 但后面没有任何字段", anomalies)
```

`application/input.py` 已有 `from __future__ import annotations`，把返回类型改成 `Iterator`：

```python
from collections.abc import Iterator

def send_sequence(adb, keys: list[str], *, delay: float = 0.5, repeat: int = 1,
                  sleep=time.sleep) -> Iterator[tuple[str, str | None]]:
```

不要从 `typing` 再导一次 `Iterator`（3.10 里 `typing.Iterator` 仍可用，但本仓库新代码用 `collections.abc`）。

- [x] **Step 4: 执行完整检查**

Run: 本计划「每次提交前的完整检查」中的整块命令。

Expected: 退出码 0。第 1 节畸形 dump 仍报 bounds / 缩进告警。

- [x] **Step 5: 精确暂存并 Commit**

```powershell
git add tvuitree/domain/tree/matching.py tvuitree/domain/tree/capture.py tvuitree/domain/tree/parsing.py tvuitree/domain/tree/models.py tvuitree/domain/tree/output.py tvuitree/application/observation.py tvuitree/application/input.py tests/selftest_tree.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'staged stat failed' }
git diff --cached
if ($LASTEXITCODE -ne 0) { throw 'staged diff review failed' }
git commit -m "Drop unused parameters and the mutable parse-anomaly global"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 4: JSON 错误处理、字节计数与缺依赖提示（先执行）

**Files:**
- Modify: `tvuitree/infrastructure/image.py`
- Modify: `tvuitree/interfaces/json_io.py`、`shot.py`、`mcp.py`
- Test: `tests/selftest_tree.py` 第 7 节及新增第 12 节

**Interfaces:**
- Consumes: 当前 `_emit` / `_load_full`（Task 2 尚未执行）
- Produces:
  - `_load_full(path: str) -> dict`：保留现有校验，非对象/缺 tree/tree 非列表抛 ValueError，文件错误抛 OSError。
  - `image.load_tree(path: str) -> dict`：同样校验，抛 ValueError/OSError，不抛 SystemExit，不从 infrastructure 导入 interfaces。
  - `run_shot` 使用 `_load_full`，错误返回 1；Task 2 后入口名变为 load_full_json。
  - `_emit` 按 UTF-8 字节数报告文件大小，含末尾 LF；Task 2 后名为 emit_json。
  - pydantic 与 mcp 的导入在同一 try 内，缺任一个依赖时给相同安装提示。

- [x] **Step 1: 添加库异常契约和 CLI 错误路径测试**

在第 7 节已有 load_tree 成功读取断言之后插入下列完整用例。SystemExit 只在测试中显式捕获，生产代码不通过捕获 BaseException 来掩盖问题。CLI 用子进程隔离退出行为，并提供 --image，因此不会进入设备连接路径。

```python
import subprocess

bad_json_cases = [
    ("missing", None, OSError),
    ("malformed", "{", ValueError),
    ("array", "[1, 2, 3]", ValueError),
    ("null", "null", ValueError),
    ("no_tree", "{}", ValueError),
    ("wrong_tree", '{"tree": {}}', ValueError),
]
for label, contents, expected_error in bad_json_cases:
    source_path = os.path.join(TD, f"shot_{label}.json")
    if contents is not None:
        with open(source_path, "w", encoding="utf-8") as source:
            source.write(contents)
    raised = None
    try:
        image.load_tree(source_path)
    except (Exception, SystemExit) as error:
        raised = error
    t.ok(isinstance(raised, expected_error),
         f"load_tree 的 {label} 输入抛 {expected_error.__name__}",
         f"实际 {type(raised).__name__}: {raised}")
    if label in ("array", "null", "no_tree", "wrong_tree"):
        t.ok("tree" in str(raised), f"{label} 错误说明树结构不合法")
    out_path = os.path.join(TD, f"shot_{label}.png")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "main.py"), "shot",
         "--json", source_path,
         "--image", os.path.join(TD, "must_not_be_read.png"),
         "--out", out_path, "--no-connect", "--quiet", "--no-color"],
        cwd=HERE, capture_output=True, timeout=15,
    )
    t.eq(proc.returncode, 1, f"shot 的 {label} 输入退出码为 1")
    t.ok(bool(proc.stderr.strip()), f"shot 的 {label} 输入在 stderr 给出说明")
    t.ok(b"Traceback" not in proc.stderr,
         f"shot 的 {label} 输入无 traceback", repr(proc.stderr))
    t.eq(proc.stdout, b"", f"shot 的 {label} 输入不输出成功结果")
    t.ok(not os.path.exists(out_path), f"shot 的 {label} 输入不生成 PNG")
```

将新增的 `import subprocess` 放到文件顶部标准库导入区，`sys` / `os` 已存在；不新增 argparse，也不直接构造容易漏字段的 Namespace。缺文件/损坏 JSON 的旧 CLI 已可能返回 1；库异常类型测试仍会捕获到 SystemExit 并记失败，不能把这些 CLI 已绿用例误认为失败信号。

在第 11 节之后、收尾之前创建第 12 节；后续任务复用该组和 `_read`。字节计数直接读二进制文件验证，不受文本读取的换行归一化影响。

```python
# ================================================================== 12. 接口契约与整理回归

t.group("12. JSON 错误处理、接口命名和结构回归")

def _read(rel: str) -> str:
    with open(os.path.join(HERE, rel), "r", encoding="utf-8") as source:
        return source.read()

from tvuitree.interfaces import json_io
_buf = io.StringIO()
_out = os.path.join(TD, "emit_zh.json")
with contextlib.redirect_stderr(_buf):
    json_io._emit({"tree": [], "note": "中文"}, _out)
with open(_out, "rb") as source:
    payload = source.read()
t.ok(f"（{len(payload)} 字节）" in _buf.getvalue(),
     "JSON 文件提示按实际 UTF-8 字节数计数（含末尾 LF）", repr(_buf.getvalue()))
t.ok(payload.endswith(b"\n") and b"\r\n" not in payload,
     "JSON 文件保留现有 LF 写入约定")
```

- [x] **Step 2: 用子进程模拟两种缺依赖条件**

在第 12 节追加。只拦截测试子进程的 import；不卸载依赖，不启动 MCP 服务，不连接设备。

```python
blocked_import_script = r"""
import builtins
import sys
original_import = builtins.__import__
blocked = sys.argv[1]
def isolated_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == blocked or name.startswith(blocked + "."):
        raise ModuleNotFoundError(f"No module named '{blocked}'", name=blocked)
    return original_import(name, globals, locals, fromlist, level)
builtins.__import__ = isolated_import
from tvuitree.interfaces import mcp
"""
for blocked_dependency in ("pydantic", "mcp"):
    proc = subprocess.run(
        [sys.executable, "-c", blocked_import_script, blocked_dependency],
        cwd=HERE, capture_output=True, timeout=15,
    )
    t.eq(proc.returncode, 1, f"缺 {blocked_dependency} 时退出码为 1")
    t.ok(b"pip install" in proc.stderr and b"mcp>=1.28,<2" in proc.stderr,
         f"缺 {blocked_dependency} 时给统一安装提示", repr(proc.stderr))
    t.ok(b"Traceback" not in proc.stderr,
         f"缺 {blocked_dependency} 时无 traceback", repr(proc.stderr))
    t.eq(proc.stdout, b"", f"缺 {blocked_dependency} 时 stdout 保持空")
```

- [x] **Step 3: 跑自检确认新增失败来自目标缺陷**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1，最终汇总正常出现；库缺文件/损坏 JSON 捕获到 SystemExit，数组/null 捕获到 AttributeError，数组/null CLI 有 traceback，UTF-8 字节计数和缺 pydantic 提示断言失败。缺 mcp 的提示和 JSON 对象形状校验当前就可能通过。不得出现未捕获 AttributeError/TypeError/SystemExit 使整场中断。

- [x] **Step 4: 最小修复生产入口**

`json_io._emit` 保持 open 的 `encoding="utf-8", newline="\n"` 与写入内容，将计数表达式改为：

```python
len((text + "\n").encode("utf-8"))
```

`image.py` 保留 json 导入，将 load_tree 改为：

```python
def load_tree(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as source:
        obj = json.load(source)
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError(f"{path} 里没有 tree，不像是本工具输出的控件树 JSON。")
    return obj
```

`shot.py` 的函数体局部 import 改为下列两个入口，删除 load_tree 导入；try 内读取使用 `_load_full`，继续保留原有 except (OSError, ValueError, TypeError) 和 stderr/return 1 行为：

```python
from .json_io import _load_full
from tvuitree.infrastructure.image import capture
```

对应读取语句改为：

```python
obj = _load_full(args.json_path)
```

`mcp.py` 删除 try 外的 `from pydantic import Field`，合并到现有 MCP 导入块：

```python
try:
    from pydantic import Field
    from mcp.server.fastmcp import FastMCP, Image
except ImportError as exc:
    raise SystemExit(
        "缺少 MCP 依赖，请在仓库环境执行：python -m pip install 'mcp>=1.28,<2'"
    ) from exc
```

此阶段不重命名 JSON 入口、不改变截图坐标、MCP schema 或调用时序；Task 2 再同步公开名。

- [x] **Step 5: 执行完整检查并审查金样差异**

Run: 本计划「每次提交前的完整检查」中的整块命令。有现成金样时执行末尾「金样审查」步骤，默认保留旧 base，允许的差异只有 JSON 输出提示里的实际字节数。

Expected: 所有检查退出码 0；六类无效 JSON 输入和两类缺依赖条件均通过；正常 JSON/PNG 金样逐字节一致。

- [x] **Step 6: 精确暂存并 Commit**

```powershell
git add tvuitree/infrastructure/image.py tvuitree/interfaces/json_io.py tvuitree/interfaces/shot.py tvuitree/interfaces/mcp.py tests/selftest_tree.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'staged stat failed' }
git diff --cached
if ($LASTEXITCODE -ne 0) { throw 'staged diff review failed' }
git commit -m "Fix shot JSON errors, UTF-8 size reporting, and MCP dependency hints"
```

本阶段通过完整检查后再提交。保留原方案实际贡献对应的 Co-Authored-By 信息。

---

### Task 5: 结构整理（JsonNode、pick_block、共享常量）

**Files:**
- Modify: `tvuitree/domain/screenshot.py`、`tree/parsing.py`、`tree/models.py`、`tree/output.py`
- Modify: `tvuitree/infrastructure/snapshot.py`
- Modify: `tvuitree/interfaces/mcp.py`、`cli.py`、`tree.py`
- Create: `tvuitree/domain/__init__.py`
- Test: `tests/selftest_tree.py` 第 7 节（`screenshot.Node` 构造）和第 12 节

**Interfaces:**
- Consumes: Task 2 的公开名、Task 3 的新签名、Task 4 已验证的缺依赖提示（本任务不再重复实现导入修复）
- Produces:
  - `screenshot.JsonNode`（不再有 `screenshot.Node`）
  - `parsing.pick_block(blocks, component) -> tuple`
  - 不再有 `pick_block_ex`
  - `models.Node.drawn` / `models.Node.context_clickable` 只读属性
  - `mcp.FOCUS_NODE_FIELDS = ("class", "resource_id", "package", "bounds", "bounds_kind", "source")`
  - CLI `--max-nodes` 与 MCP `max_nodes` 默认都是 `DEFAULT_MAX_NODES`
  - `interfaces/tree.py` 用一个递归函数数节点
  - 保留 Task 4 的 pydantic/mcp 共同 try 与缺依赖行为测试

- [x] **Step 1: 写失败断言**

第 12 节追加（`inspect` 在 Task 3 已导入则不要重复；`mcp as mcp_interface` 已在第 8 节导入，这里用它或再 `from tvuitree.interfaces import mcp as mcp_mod` 一次均可，不要混用两个别名）：

```python
import inspect
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
t.eq(getattr(mcp_mod, "FOCUS_NODE_FIELDS", None),
     ("class", "resource_id", "package", "bounds", "bounds_kind", "source"),
     "焦点压缩字段只定义一次")
```

FOCUS_NODE_FIELDS 用 getattr(..., None)：属性不存在时得到 None，由 t.eq 记一条失败，不抛 AttributeError。缺依赖提示由 Task 4 的子进程测试验证，不以导入语句的位置字符串代替行为测试。

这一步**不要**改第 7 节 `screenshot.Node(...)`：`JsonNode` 还不存在，裸改构造名会 `AttributeError` 整场退出。调用点留到 Step 3。

- [x] **Step 2: 跑自检，确认失败**

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`

Expected: 退出码 1，JsonNode / pick_block / drawn 尚不存在，FOCUS_NODE_FIELDS 的实际值是 None，失败均进入最终汇总，不出现未捕获 AttributeError。CLI 与 MCP 尚未引用 DEFAULT_MAX_NODES；默认数值等于 80 的断言当前就会绿，不能单独当变红信号。

- [x] **Step 3: 实现**

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

pydantic/mcp 的共同 try 已由 Task 4 修复并通过行为测试，此处保持，不重复移动导入。

`cli.py`：

```python
from tvuitree.domain.observation import DEFAULT_MAX_NODES
```

在 build_parser 的 observe 参数区替换现有 --max-nodes 定义，保持函数内缩进：

```python
observe.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES, metavar="N",
                     help=f"页面摘要节点上限（默认 {DEFAULT_MAX_NODES}）")
```

`mcp.py` 顶部把 `from tvuitree.domain.observation import error_observation` 改成 `from tvuitree.domain.observation import DEFAULT_MAX_NODES, error_observation`。`observe_tv` 的默认值：

```text
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

- [x] **Step 4: 执行完整检查**

Run: 本计划「每次提交前的完整检查」中的整块命令。

Expected: 退出码 0。第 8 节 MCP schema 仍含 `TV_IP_Address`，`max_nodes` 不在连接参数 schema 里（它是 observe_tv 自己的参数，本任务不改 schema 形状）。

- [x] **Step 5: 精确暂存并 Commit**

```powershell
git add tvuitree/domain/screenshot.py tvuitree/domain/tree/parsing.py tvuitree/domain/tree/models.py tvuitree/domain/tree/output.py tvuitree/infrastructure/snapshot.py tvuitree/interfaces/mcp.py tvuitree/interfaces/cli.py tvuitree/interfaces/tree.py tvuitree/domain/__init__.py tests/selftest_tree.py
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'staged stat failed' }
git diff --cached
if ($LASTEXITCODE -ne 0) { throw 'staged diff review failed' }
git commit -m "Disambiguate Node types and share observation defaults"
```

提交说明末尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 6: 文档与测试里的旧脚本名

**Files:**
- Modify: `tests/selftest_tree.py`（仅第 7 节职责边界断言的说明文字、夹具注释）
- Modify: `AGENTS.md`（Structure 段补注释约定）
- README 的旧命令迁移表保留历史入口 tv_shot.py / tv_input.py

**Interfaces:**
- Consumes: 现有 infrastructure/image.py、application/input.py；Task 1 已整理的注释习惯
- Produces: 测试说明与 AGENTS 和代码分层一致；既有职责边界断言的条件保持原样，不新增 AGENTS 精确句子断言

- [x] **Step 1: 更新现有测试说明与夹具注释**

将原说明字符串换成当前模块路径，比较的条件不变：

```python
t.ok("screencap" not in tree_src and "screencap" not in core_src,
     "树采集实现绝不截图（截图是 infrastructure/image.py 的事）")
t.ok("input keyevent" not in tree_src and "input keyevent" not in core_src,
     "树采集实现绝不发按键（按键是 application/input.py 的事）")
t.ok("fetch_u2" not in shot_src and "parse_dumpsys_top" not in shot_src,
     "infrastructure/image.py 不自己取树（它只读 JSON）")
t.ok("build_full_json" not in input_src, "application/input.py 与取树无关")
```

夹具注释 tv_shot「祖先链溢出容器」改为画框「祖先链溢出容器」；captured_at 的说明改为「要有采集时刻（shot 靠它判断截图与取树是否同时刻）」。这些是测试消息，不制造失败断言。

- [x] **Step 2: 更新 AGENTS.md 的注释约定**

在 Structure 第一段之后插入：

```markdown
Comment language: module docstrings are one English line; function/class docstrings and inline comments are Chinese. Longer module responsibility notes belong in subsequent Chinese comments. User-facing CLI/MCP strings stay Chinese. Do not leave empty section banners or comments that refer to a deleted file-header principle list. Library modules under `tvuitree/` do not use shebangs or coding cookies; `main.py`, `tests/selftest_tree.py`, and `scripts/` may.
```

只更新共享源 AGENTS.md，CLAUDE.md 继续导入它；generator 的 tv_tree.py 与 README 历史迁移表不动。

- [x] **Step 3: 完整检查与最终 diff 审查**

Run: 本计划「每次提交前的完整检查」整块命令。第 12 节不添加注释翻译/AGENTS 措辞断言；完整检查保持通过，既有测试条件不变，仅说明文字变化。

有 `_temp/e2e/full.json` 时追加以下离线检查，每条命令立即检查退出码：

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py main.py observe --from-json _temp/e2e/full.json --out NUL
if ($LASTEXITCODE -ne 0) { throw 'offline observe failed' }
& $py main.py visible --from-json _temp/e2e/full.json --out NUL
if ($LASTEXITCODE -ne 0) { throw 'offline visible failed' }
& $py main.py tree --from-json _temp/e2e/full.json --mode slim --out NUL
if ($LASTEXITCODE -ne 0) { throw 'offline slim failed' }
```

有可用设备时执行一次只读 TV observe 检查，并报告采集证据与漂移状态；设备不可用不阻塞离线验收。最后按下一节复核已有金样，任何非预期差异都必须解释，不能覆盖。

- [x] **Step 4: 精确暂存并 Commit**

```powershell
git add tests/selftest_tree.py AGENTS.md
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw 'staged stat failed' }
git diff --cached
if ($LASTEXITCODE -ne 0) { throw 'staged diff review failed' }
git commit -m "Document comment language and replace legacy script names in tests"
```

本次计划修订不混入产品阶段提交；其他文件或配置改动留在原状态。保留实际贡献对应的提交作者信息。

---

## 金样审查：先比对，保留旧基线

仅在 golden.py、base/ 及 full.json、shot_a11y.png、原始 dumpsys/a11y 夹具齐备时执行；缺任何一个，报告缺项并以完整离线自检验收，不现场造新的真机数据。现有 golden.py 会把 check 的新输出写到 now/，make 会重建整个 base/；本计划不以 make 接受差异。

- [x] **Step 1: 修改生产代码前检查原基线；修改后生成 now 并列出差异**

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py _temp/golden/golden.py check
$goldenExitCode = $LASTEXITCODE
if ($goldenExitCode -notin @(0, 1)) { throw 'golden runner failed' }
```

退出码 1 只表示有差异，不能当成通过。修改前已经有差异时先定位，不能把旧问题归到本任务。修改后允许的变化只有 Task 4 修正 JSON 输出诊断的字节数；不要运行 make。Task 4 修复计数后的差异应在本阶段解释，后续纯整理不能增加新的差异。

- [x] **Step 2: 严格检查全部文件；只在指定 stderr 行归一化字节数**

以下命令只读 base/ 与 now/；所有 JSON、PNG、其余文本逐字节比较。仅 slim/keep_all/keep_gone/observe/visible 的 stderr `[out] 已写入` 行允许数字变化，并验证 now 的数字确为相应 JSON 文件的实际字节数。新文件、缺文件、stdout、返回码或其他 stderr 内容不同均失败。编码只为解析已有诊断，仍按同一编码逐处比较内容。

```powershell
@'
from pathlib import Path
import re

root = Path('_temp/golden')
base, now = root / 'base', root / 'now'
base_names = {item.name for item in base.iterdir() if item.is_file()}
now_names = {item.name for item in now.iterdir() if item.is_file()}
required = {'rebuilt_full.json', 'shot_focus.png', 'observe.json', 'visible.json'}
if not required.issubset(base_names):
    raise SystemExit(f'Incomplete golden baseline: {required - base_names}')
if base_names != now_names:
    raise SystemExit(f'Golden file set changed: {base_names ^ now_names}')
allowed_text = {'slim.txt', 'keep_all.txt', 'keep_gone.txt', 'observe.txt', 'visible.txt'}
separator = b'\n--- stderr ---\n'
pattern = re.compile(r'(?m)^(\x1b\[[0-9;]*m)?(\[out\] 已写入 [^\r\n]*?（)\d+( 字节）)')
changed = []
for name in sorted(base_names):
    old = (base / name).read_bytes()
    new = (now / name).read_bytes()
    if old == new:
        continue
    if name not in allowed_text:
        raise SystemExit(f'Unexpected golden change: {name}')
    old_stdout, old_sep, old_tail = old.partition(separator)
    new_stdout, new_sep, new_tail = new.partition(separator)
    if not old_sep or not new_sep or old_stdout != new_stdout:
        raise SystemExit(f'Unexpected stdout/separator change: {name}')
    for encoding in ('utf-8', 'gb18030'):
        try:
            old_text = old_tail.decode(encoding)
            new_text = new_tail.decode(encoding)
        except UnicodeDecodeError:
            continue
        if pattern.search(old_text) and pattern.search(new_text):
            break
    else:
        raise SystemExit(f'Cannot identify byte-count diagnostic: {name}')
    old_matches = list(pattern.finditer(old_text))
    new_matches = list(pattern.finditer(new_text))
    if len(old_matches) != 1 or len(new_matches) != 1:
        raise SystemExit(f'Ambiguous byte-count diagnostic: {name}')
    match = new_matches[0]
    json_path = now / Path(name).with_suffix('.json').name
    expected_size = len(json_path.read_bytes())
    expected_line = (match.group(1) or '') + match.group(2) + str(expected_size) + match.group(3)
    if match.group(0) != expected_line:
        raise SystemExit(f'Incorrect UTF-8 byte count: {name}')
    if pattern.sub(r'\1\2<BYTE_COUNT>\3', old_text) != pattern.sub(r'\1\2<BYTE_COUNT>\3', new_text):
        raise SystemExit(f'Unexpected stderr/return-code change: {name}')
    changed.append(name)
print('All JSON/PNG and other output bytes unchanged; reviewed count diagnostics:', changed)
'@ | & .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw 'golden difference review failed' }
```

默认保留 base 原件，记录允许变化的文件列表与验证结果即可，不为消除预期差异刷新整套基线。若另有基线维护需求，先备份 base，再仅替换逐个审查过的诊断文本文件；JSON/PNG 不在本计划更新范围内。

## Plan self-review（修订时）

1. **Spec coverage:** 保留原六项整理范围；本次三个 P2 问题分别由 Task 5 的安全属性读取、Task 4 的六类 JSON 错误测试、金样只读差异检查处理。共享告警与缺依赖问题的描述按当前代码纠正。
2. **Failure-phase safety:** Task 5 新属性通过 getattr(..., None) 读取；Task 3 签名和 Task 5 JsonNode 的旧调用只在生产改动同一步迁移；Task 4 库测试显式捕获 SystemExit，CLI/MCP 缺依赖测试使用隔离子进程，全部失败能到达最终汇总。
3. **Execution and types:** 顺序 4 → 3 → 2 → 5 → 1 → 6；Task 4 使用旧 JSON 名，Task 3 使用旧 _anomaly 名，Task 2 再统一重命名生产与测试调用。第 12 节由 Task 4 创建，_read/inspect/json_io 的来源明确；timing._emit 不变。
4. **Validation:** 每次提交前均运行 py_compile、pyflakes、完整自检、--help、--prune-list、diff --check，并检查每条退出码。精确暂存并审查 staged diff；纯注释/文案不添加逐字源码断言。638 是修订前基线，不是实施后的预计断言数。
5. **Golden contract:** check 生成 now，base 保留；JSON/PNG/其余输出逐字节一致，仅明确的 stderr 字节计数允许变化且核对实际文件长度。不存在以 make 消除未知差异的步骤。golden.py 的 pick_block/getattr 回退已可兼容 Task 5，无须改其业务逻辑。
6. **Scope:** 修订计划阶段只修改本文件；随后经用户明确授权实施下列六个阶段。config、设备地址、外部 push/merge 未进入改动范围，金样 base 未覆盖。


## Execution record — 2026-10-02

执行顺序 4 → 3 → 2 → 5 → 1 → 6；当前 main 原地执行。计划修订检查点：`396feac`。

| Task | 提交 | 完整自检断言 | 验证 |
|---|---|---:|---|
| 4 JSON 错误、字节计数、缺依赖提示 | `958b035` | 688 | RED → GREEN；完整检查全部 exit 0 |
| 3 参数与解析默认状态 | `7e81718` | 697 | RED → GREEN；完整检查全部 exit 0 |
| 2 跨模块公开命名 | `4318eb5` | 705 | RED → GREEN；完整检查全部 exit 0 |
| 5 类型、属性、默认值和计数 | `436f924` | 714 | RED → GREEN；完整检查全部 exit 0 |
| 1 注释整理 | `6059a6a` | 714 | 排除文档字符串后的 AST 相同；完整检查全部 exit 0 |
| 6 文档与旧名称说明 | `fe3e2a1` | 714 | 测试条件保持原样；完整检查全部 exit 0 |

每阶段完整检查包括项目虚拟环境的 py_compile、pyflakes、selftest_tree.py、main.py --help、tree --prune-list 和 git diff --check。提交前精确暂存并检查 staged diff。

离线 observe、visible、slim 入口均 exit 0。原始金样基线预检 19/19 完全一致；最终全部 JSON/PNG 逐字节一致，五个文本诊断文件 keep_all.txt、keep_gone.txt、observe.txt、slim.txt、visible.txt 只出现预期的 UTF-8 字节计数差异，且逐个验证等于实际 JSON 文件长度（含末尾 LF）。其他 stdout、stderr、返回码与文件集合不变；base 原件保留，没有运行 make。

真机：使用既有配置执行只读 observe，因无法连接设备返回 2；未取得当前 TV 采集结果，不声称验证了当前设备的焦点或漂移状态。本机地址及采集产物未提交。

执行裁决（按发生顺序）：

1. 按用户批准计划在 main 原地执行，不建立工作树；代价是本地 main 直接包含阶段提交，仍可通过 Git 恢复。没有推送或合并。
2. 文档给定的 Bash 不可用，使用本计划忽略目录内的 Python 等价脚本生成 brief、记录 BASE、台账和完整校验；风险是辅助流程可移植性，任务范围和验证内容保持原样。
3. Task 4 追加 README 中的 shot 错误与字节计数说明，满足 AGENTS 的接口变化文档要求；错误说明可能误导用户，已用新增边界测试核对。
4. task-done 使用源文件 SHA256 确认成功的提交前完整校验仍对应相同文件，避免只因 commit 元数据改变重复测试；风险是漏掉源变化，因此指纹变化立即拒绝完成记录并要求重新校验。
5. Task 6 同步清理第 7 节相邻的另外两处旧 tv_shot 标签；仅注释/断言消息变化，断言条件不变，风险限于测试说明准确性。

最终独立 Review：由一次全新上下文的 reviewer 审查 `396feac..fe3e2a1` 全部 28 个文件、实际调用点、计划与台账。Critical / Important / Minor 均无；判定可以交付。审查独立核对 40 个校验指纹全部匹配最终完整检查，Task 1 的 13 个文件去除 docstring 后 AST 相同，原金样严格比对通过；纯内存边界检查确认六类 shot 输入错误均在访问设备、图片或 render 前返回 1，短 flag 字符串的新属性与原判定一致。未重复派发审查。

对 reviewer 的 Declined to judge 项逐项裁决（延续上述顺序）：

6. 当前真机采集与漂移状态暂不作结论：无法连接设备，用户得到的是明确的离线验收而非未证实的现场结论；错误地外推到真机会漏掉设备特有问题。
7. 不把本次六类文件/根结构错误修复扩大为深层非法节点、异常 captured_at 的完整 schema 容错：这些路径未由本次新增或改变，shot 仍要求工具生成的 full JSON；代价是人为篡改深层数据时现有异常风险仍在，不能据此声称任意 JSON 均安全。
8. 不保留仓库外对旧内部函数名和死参数签名的兼容层：批准计划要求统一公开名并删除死参数，仓内生产、测试、脚本和金样调用点已核对；代价是第三方若直接调用这些内部入口须同步迁移。
9. 不扩展配置追踪策略、依赖拆分/版本固定、pytest 迁移：批准计划明确列为另行任务，现有差异未触及；代价是原有维护限制仍在，后续需求需单独处理。

Deferred minors：无。最终没有遗留 Critical / Important 修复项。按批准范围保留当前 main 本地提交，无 push/merge；只清理本计划的忽略临时执行目录，其他计划及原金样保留。
