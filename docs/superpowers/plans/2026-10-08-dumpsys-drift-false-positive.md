# dumpsys 漂移误报修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. 本计划建议在当前会话顺序执行，无需拆分子代理。

**Goal:** 排除消息队列等非 View 日志引起的漂移误报，同时保留真实 View 层次变化的检测。

**Architecture:** 复用 `parse_dumpsys_top(raw)` 与解析节点已有的 `lineno`，从原文提取实际消费的 View 行。`hierarchy_drift(raw_a, raw_b)` 继续比较行数、顺序和原始内容，不改变采集流程与返回结构。

**Tech Stack:** Python 3.10+、项目 `.venv`、现有纯 Python dumpsys 解析器与 `tests/selftest_tree.py`；不新增依赖。

**Spec:** [2026-10-08 真机验证报告](../../reports/2026-10-08-real-tv-data-validation.md)，尤其是“确认缺陷：漂移误报（P2）”及其原始证据。

## Global Constraints

- 计划编写时仅输出方案；后续按用户“执行”指令完成实施与验收。提交、推送和发布未执行。
- 实施前重新检查 `git status`，保留原有 `config.json`、验收报告及索引修改；不覆盖旧真机证据。
- 使用 Python 3.10+、四空格缩进、UTF-8；新增实现保留类型提示，函数说明使用中文。
- domain 不访问设备或文件；复用现有解析能力，不创建新解析器、模块、缓存或配置开关。
- 保持 `hierarchy_drift(raw_a: str, raw_b: str) -> tuple` 调用方式，以及 `drift`、`detail`、`note`、`warnings` 的字段形状不变。
- 保持真实 View 原文的缩进、顺序、flags、实例标识和坐标，不做容差或“忽略真实变化”的归一化。
- 保持当前对所有已解析 Activity 段的比较范围；本次不改成仅比较前台窗口，不更改 R0–R3、可见筛选或截图坐标。
- MCP stdout 仅承载协议；计时仍写 stderr。
- 持久回归写入现有脚本，真机原始数据、日志及临时脚本留在忽略目录 `_temp/`；正式文档不包含设备地址或敏感运行输出。
- 只有后续明确请求提交时才提交；只暂存任务相关文件，使用带模块范围的 Conventional Commits。推送另按明确授权执行。

## Review Focus

以下五类实际边界全部纳入任务 1 的回归，不新增产品要求：

1. 消息队列行增删或内容变化、层次外带花括号的日志，不应产生 View 漂移。
2. 真实 View 的坐标、flags、增删变化，仍应产生漂移。
3. 无花括号的旧格式 DecorView，以及 Android 16 名称在实例块后的根节点，都应参与比较。
4. View 顺序或缩进层级变化，仍应产生漂移。
5. 多 Activity 段保持原有比较范围；空输入相同不漂移，有层次与无层次之间变化仍应漂移。

---

## 修改文件

| 文件 | 修改内容 |
|---|---|
| `tvuitree/domain/tree/capture.py` | 导入并复用 `parse_dumpsys_top`，替换 `_hierarchy_lines` 的花括号筛选 |
| `tests/selftest_tree.py` | 修正第 6 节中的错误漂移断言，补充真实输入格式的回归 |
| `docs/README.md` | 添加计划链接；实施后添加修复验收链接并更新当前状态 |
| `docs/reports/2026-10-08-dumpsys-drift-fix-validation.md` | 实施完成后创建，记录修复、验证和实际限制 |

历史真机报告保留原结论；通过新报告说明后续修复状态。

## Task 1：最小修复与离线回归

**Files:** Modify `tvuitree/domain/tree/capture.py:6-19`；Test `tests/selftest_tree.py:900-910` 附近的漂移断言。

**Interfaces:**
- Consumes: `parse_dumpsys_top(raw: str, anomalies: Optional[list] = None) -> list`；每个 `Block.all_nodes` 的节点已有从 1 开始的 `Node.lineno`。
- Produces: `_hierarchy_lines(raw: str) -> list[str]`；保持 `hierarchy_drift` 的 `(bool, detail)` 返回形式和现有文案格式。
- Caller: `tvuitree/infrastructure/snapshot.py`；应用层、CLI 和 MCP 均通过该快照流程得到一致性结果，无需分别修改。

- [x] **Step 1：补充会失败的回归，并保留真实变化的断言。**

在现有漂移测试段使用已有 `_dumpsys()` 脱敏夹具。原来的 `多出来的一行{x}` 是非 View 日志，应改为不漂移；“真实 View 增删”用合法节点行另外覆盖。以下断言加入同一测试段：

```python
base = _dumpsys()
queue = (
    "    Looper:\n"
    "      Message 1: { when=+25ms what=40 "
    "target=android.view.ViewRootImpl$ViewRootHandler }\n"
)
t.eq(capture.hierarchy_drift(base + queue, base), (False, None),
     "消息队列行消失不算 View 漂移")
t.eq(capture.hierarchy_drift(base, base + queue), (False, None),
     "消息队列行新增不算 View 漂移")
t.eq(capture.hierarchy_drift(base + queue, base + queue.replace("+25ms", "+99ms")),
     (False, None), "消息队列内容变化不算 View 漂移")
t.eq(capture.hierarchy_drift(base, base + "\n  多出来的一行{x}"),
     (False, None), "非 View 花括号日志不算漂移")

outside_view = (
    "    Looper:\n"
    "      android.widget.TextView{aabbcc V.E...... ......ID 0,0-10,10}\n"
)
t.eq(capture.hierarchy_drift(base, base + outside_view), (False, None),
     "层次段外形似 View 的日志也不参与比较")

extra = (
    "          android.widget.TextView{aabbcc V.E...... ......ID "
    "20,20-100,100 app:id/extra}\n"
)
added = base.replace("          com.demo.Gamma", extra + "          com.demo.Gamma", 1)
t.eq(capture.hierarchy_drift(base, added)[0], True, "真实 View 新增仍算漂移")
t.eq(capture.hierarchy_drift(added, base)[0], True, "真实 View 删除仍算漂移")
t.eq(capture.hierarchy_drift(base, base.replace(".F....ID", "......ID", 1))[0],
     True, "真实焦点 flags 变化仍算漂移")

t.eq(capture.hierarchy_drift(base, base.replace("[MainActivity]", "[OtherTitle]", 1))[0],
     True, "无花括号的 DecorView 根行变化仍算漂移")
post_name = base.replace(
    "DecorView@6e60694[MainActivity]",
    "DecorView{6e60694 V.E...... ......ID 0,0-1920,1080}[MainActivity]", 1)
t.eq(capture.hierarchy_drift(post_name, post_name)[0], False,
     "Android 16 根节点后置名称可正常比较")
t.eq(capture.hierarchy_drift(post_name, post_name.replace("[MainActivity]", "[OtherTitle]", 1))[0],
     True, "Android 16 根节点名称变化仍算漂移")

ordered = base.splitlines()
alpha_index = next(i for i, line in enumerate(ordered) if "{f4a126d " in line)
beta_index = next(i for i, line in enumerate(ordered) if "{de6fd27 " in line)
ordered[alpha_index], ordered[beta_index] = ordered[beta_index], ordered[alpha_index]
t.eq(capture.hierarchy_drift(base, "\n".join(ordered))[0], True,
     "真实兄弟顺序变化仍算漂移")
t.eq(capture.hierarchy_drift(base, base.replace("          com.demo.Gamma", "        com.demo.Gamma", 1))[0],
     True, "真实节点缩进层级变化仍算漂移")

second = base.replace("com.demo/.MainActivity", "com.demo/.SecondActivity", 1).replace("pid=100", "pid=101", 1)
t.eq(capture.hierarchy_drift(base + second, base + second + queue), (False, None),
     "多 Activity 段外的消息队列变化不算漂移")
t.eq(capture.hierarchy_drift(base + second, base + second.replace("480,0-960,200", "480,0-961,200", 1))[0],
     True, "第二个 Activity 的真实 View 变化仍算漂移")
t.eq(capture.hierarchy_drift(base, "")[0], True, "真实 View 层次消失仍算漂移")
```

保留现有“相同输入”“单调时钟变化”“真实布局坐标变化”“两边无层次”及差异说明的断言，不通过删除有效测试取得通过。

- [x] **Step 2：执行完整自检，确认 RED。**

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe tests/selftest_tree.py
```

预期新增非 View 日志和无花括号根行断言失败，退出码为 1；逐项阅读失败，确认原因是当前花括号筛选。该脚本没有单测试选择器，不使用 pytest。

- [x] **Step 3：修改共享函数，复用现有解析器。**

在 `capture.py` 的 parsing 导入中增加 `parse_dumpsys_top`；`_hierarchy_lines` 替换为：

```python
def _hierarchy_lines(raw: str) -> list[str]:
    """只比较现有解析器实际消费的 View 行，保留原始顺序和缩进。"""
    lines = raw.splitlines()
    return [lines[node.lineno - 1].rstrip()
            for block in parse_dumpsys_top(raw)
            for node in block.all_nodes]
```

不修改 `snapshot.py`、协议层或摘要层，不添加消息日志黑名单，不过滤真实 View 的 flags、实例标识或布局变化。原有解析器继续负责 ACTIVITY 段、View Hierarchy 边界及两种根节点格式。

- [x] **Step 4：执行项目检查，确认 GREEN。**

```powershell
$env:PYTHONUTF8 = '1'
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile $pythonFiles
.\.venv\Scripts\python.exe -m pyflakes $pythonFiles
.\.venv\Scripts\python.exe tests/selftest_tree.py
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe main.py tree --prune-list
git diff --check
```

检查每条命令的实际退出码；自检必须全部通过，记录新增后的真实断言数，不沿用 1140 作为新结果。

- [x] **Step 5：回放本轮保存的真实输入。**

```powershell
.\.venv\Scripts\python.exe _temp/tv_validation_20261008/drift_repro.py
```

修复前该脚本 4 项失败、退出码 1；修复后 9 项均通过、退出码 0。旧 full JSON 与旧警告是历史记录，不修改它们，也不要求修改代码后历史 JSON 自动更新。原始日志保留，复现脚本运行会重新生成 `drift_findings.json`，应先复制旧结果到新的 `_temp/` 验证目录留证，再运行。

若本地原始证据缺失，永久离线回归仍须通过；报告中明确记录真实输入回放未执行及文件缺失原因，不伪称通过。

## Task 2：真机验收与交付文档

**Files:** 实施后 Create `docs/reports/2026-10-08-dumpsys-drift-fix-validation.md`；Modify `docs/README.md`。新原始证据写入 `_temp/tv_validation_20261008_drift_fix/`。

**Interfaces:** 使用既有 `collect_full_json`、`collect_observation` 及五个 MCP 读取工具；期望改变的字段仅是误报快照的 `source_consistency` 及由其产生的警告。

- [x] **Step 1：重新检查设备是否可用，建立新的证据目录。**

设备地址读取现有配置或使用会话授权目标，不写入正式文档。以当次有唯一焦点的画面为基准；记录原焦点和选中状态，不把历史控件文案或坐标当作所有页面的固定要求。

- [x] **Step 2：重复真实采集，核对一致性判断。**

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe main.py tree --mode full --save-raw _temp/tv_validation_20261008_drift_fix/stable/raw --out _temp/tv_validation_20261008_drift_fix/stable/full.json
.\.venv\Scripts\python.exe main.py observe --from-json _temp/tv_validation_20261008_drift_fix/stable/full.json --out _temp/tv_validation_20261008_drift_fix/stable/observe.json
```

在稳定页面及一次方向键移动后的页面分别采集，方向键后以当次前后原始 View 行为判断依据：行一致时必须 `drift=false`、`detail=null`；行确实不同则必须 `drift=true`，不得为了通过测试强行隐藏真实动画或布局变化。

真实 View 增删、坐标、顺序、flags、根节点和层级变化的确定性验证由任务 1 的回归负责，不强求真机在恰好两次抓取之间出现变化。

- [x] **Step 3：复核真实 MCP 结果与其他观察字段。**

启动实际 stdio MCP，使用现有公开客户端 API，依次调用 `get_full_tree`、`observe_tv`、`get_visible`、`get_current_focus`、`get_focus_screenshot`，保存协议结果和 stderr。以当次原始 XML 与截图核对文字、唯一焦点、状态和矩形；检查 PNG、Base64、原生 MCP Image 一致性及单次计时块。复用本轮临时验证脚本中已有检查，新输出写入新证据目录。

不另造错误回退或后台重试机制，不用历史字段的完全相等比较否定真实界面变化。若使用已有 `validate_mcp.py`，需将其输出目录切换到新目录，并移除固定 `Tuner Mode / Antenna` 文案断言；保留与当次 baseline full 的焦点信息比较。

- [x] **Step 4：恢复画面并记录实际结果。**

恢复原焦点，检查原选中项和开关状态；确认 `config.json` 字节未改写。无可用 TV 时完成离线修复，但明确标记新版本真机验收尚未执行。

- [x] **Step 5：更新交付报告与索引。**

新报告列出：根因、最小变更、RED/GREEN 结果、新自检条数、9 份真实输入回放结果、实际 MCP 与真机验证，以及未完成事项。旧报告保留误报历史；索引改为“已修复”必须以本轮验证证据为前提。

- [x] **Step 6：检查交付范围。**

```powershell
git diff --check
git diff --stat
git status --short
```

确认差异仅含任务文件，未暂存或改写配置、旧原始日志等无关数据。若用户后续要求提交，可将已验证代码和永久回归提交为 `fix(tree): 排除非 View 日志导致的漂移误报`，验收文档另以 `docs(validation): 记录漂移误报修复验收` 提交；不默认推送。

## 验收标准

- 非 View 日志变化不再触发漂移；本轮 4 份历史误报输入恢复正确判断。
- 所有真实 View 变化的回归通过，检测能力没有被“始终返回 false”等做法削弱。
- 已有 CLI/MCP 字段、R0–R3、可见投影、焦点和截图坐标契约保持一致。
- 静态检查及完整自检通过；真实输入回放和真机/MCP 各自报告实际执行结果。
- 保留原配置和历史证据；报告明确区分修复完成与真机未执行，不用离线通过替代真机验收。

## 计划自检与当前状态

两个任务均已实施。按 RED→GREEN 顺序完成最小修复，1155 条自检通过；9 份历史原始输入回放通过，新真机数据与截图 20 项检查、真实 MCP 36 项检查通过。五项 Review Focus 均有永久回归。

复用原虚拟环境，在受管隔离 worktree 实施并验证后，将相关文件交付原工作区。旧配置和原始证据保留，未提交或推送。最终独立审查和交付记录见[修复验收报告](../../reports/2026-10-08-dumpsys-drift-fix-validation.md)。
