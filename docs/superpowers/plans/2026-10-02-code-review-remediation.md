# code-review-remediation - Work Plan

## TL;DR (For humans)

**What you'll get:** 8 项已核实的代码缺陷被逐个修复并各自锁进离线回归，外加 1 项本次评审新发现的退出码违约（GAP-11）。修复集中在「静默给出错数据」和「产物可能损坏」两类失败模式上——这正是本仓库自己在注释里定义为最伤信任的那一类。

**Why this approach:** 每条缺陷都有 file:line 证据，且**全部可离线验证**（不需要 TV、ADB 或网络），符合 AGENTS.md「不把设备可用性当作离线验证前提」。任务按风险从低到高排序：纯 domain 正则 → 画框 → JSON 输出 → ADB 属性 → ADB 连接语义 → 依赖卫生 → 文档核对。每个任务沿用仓库既有的 RED→GREEN 逐任务锁，与上一份计划 6 个 Task 的实际执行方式一致（断言数 688→714）。

**What it will NOT do:** 不改任何 JSON 字段名/口径、CLI 退出码语义、MCP 工具名/入参 schema/返回键集合；不改 `generator` 的 `tv_tree.py`；不动 R0–R3 配对规则、剪枝认领顺序、「逐像素对齐、不加偏移」画框约定；**不动 `config.json` 的 git 追踪策略**（按你的决定写进 Out of scope）；不迁移到 pytest；不做 MCP 整体超时或 u2 连接复用（上一轮评审的 M2/M3，属独立设计任务）。

**Effort:** Large

**Risk:** Medium。最高风险点是 T4/T5 要新建 ADB 假件——`tests/selftest_tree.py` 是**顺序脚本**（`sys.exit(t.summary())` 在 `:2149`），未捕获的 TypeError/AttributeError/IndexError 会让整场提前退出、后面的段跑不到（上一份计划 Task 3/5 Step 1 明确踩过）。本计划用 5 条硬性 RED 规则封死它（见 Verification strategy）。次高风险是 T3 的原子写：`--out NUL` 是本仓库既有的离线检查写法，`os.replace` 打到设备名会失败，必须特判。

**Decisions:**
- 你选定：修 GAP-1..8；`config.json` 追踪策略（GAP-9/IS-9）单列进 Out of scope，本计划刻意不关闭它。
- 你选定：沿用仓库既有 RED→GREEN 逐任务锁。
- `props()` 串位改为抛 **`AdbError`**（不是 ValueError）——唯一调用方 `snapshot.py:19-22` 只捕 `AdbError` 并降级为 `dev={}`，换别的异常类型会让整轮采集失败，破坏既有降级设计。
- `connect()` 多设备且未指定 serial 时**返回 False 且不改写 `self.serial`**，绝不抛异常——`interfaces/connection.py:34` 调用处没有 try/except，抛出会变成 traceback + 退出码 1，违反 AGENTS.md:17 的「连接错误 → 退出码 2 + 友好诊断」契约。
- **Metis 的一条指令经实测被推翻**：它主张只收紧 `component.py:15` 的回退正则。实测证明 `Window{abc u0 uid/1000}` 是被 **`:12` 的严格正则**先命中的，只改回退正则修不好；且候选修法里的 `(?:\.[\w]+)*` 因为是「零或多个」而**根本没要求点号**。两条正则都要改成 `+`。详见 Scope 里的实测验证表。

---

## Scope

### Affected user and ideal state

**谁会被这份产出碰到：**

1. **调用 MCP 工具的模型 / Agent** —— 消费 `observe_tv` / `get_visible` / `get_current_focus` / `get_focus_screenshot`，把 `device.*`、焦点标签、notes 当作判断证据。
2. **跑 CLI 的开发者 / 测试工程师** —— 用 `observe` / `tree` / `visible` / `shot` / `input`，读 stderr 诊断，复用 `--from-json` 采集结果。
3. **仓库维护者** —— 跑 `tests/selftest_tree.py`，提交代码，必须避免把本机设备地址带进仓库。
4. **后续贡献者** —— 读 AGENTS.md / README / `docs/superpowers/plans/` 下的既有计划。
5. **`Adb` 类的外部库使用者** —— `Adb` 是可公开构造的类；仓内调用方到不了空 serial 分支，外部使用者到得了。
6. **`--out NUL` / `/dev/null` 的使用者** —— 这是本仓库既有的离线检查写法，上一份计划 940-944 行就在用。

**理想状态（IS 行，一行一条性质）：**

| ID | 理想状态 | 理由 |
|---|---|---|
| IS-1 | full JSON 里每个 `device.*` 字段的值就是它声称的那个 prop 的值，绝不静默串位到相邻键 | `device` 是模型和人的共同证据；model/manufacturer 串位是「静默错数据」，正是本仓库定义为最伤的失败模式 |
| IS-2 | 磁盘上的 `--out` JSON 要么是完整新内容、要么是完整旧内容，绝无截断半成品 | `--from-json` 消费者把「文件能读」当作「采集有效」，截断会把人引向错误排查方向 |
| IS-3 | ADB 采集中途掉线并触发自动重连时，只有设备真的重新可用才报「已重连」 | 误报会让重试继续打向已死设备，把错误推迟成更难懂的下游异常 |
| IS-4 | 截图上的框标签画不出来时，notes 里说明 | `shot` 的用途就是拿读数核对画面；静默缺标签与「本就不该有标签」无法区分 |
| IS-5 | `component_from_window` 绝不把非 component 子串（如 `uid/1000`）当成前台组件返回 | 伪组件会让 `pick_block` 回退到最后一个 ACTIVITY 段——可能是另一个页面的树，正是它 docstring 警告的陷阱 |
| IS-6 | 全新 clone 只安装代码真正 import 的依赖 | `uiautodev` 是死重量兼供应链面 |
| IS-7 | `resolve_adb` 的探测列表不含任何个人机器路径 | 它把某个开发者的磁盘布局编码进了共享代码 |
| IS-8 | `Adb` 不可能静默操作一个调用方从未指定的设备 | 本机另挂模拟器/手机时，所有读写会打到未知设备且无告警 |
| IS-10 | 存在一份针对上述风险的、决策完备的修改计划，放在 `docs/` 下并符合仓库既有计划格式 | 用户要求的交付物 |
| IS-11 | `observe`/`tree`/`visible` 的 `--out` 写失败以文档规定的退出码 2 结束、stderr 给中文原因、不吐 traceback | AGENTS.md:17 定义文件错误用退出码 2；吐 traceback 违反仓库既有约定，且把真因藏起来 |

> IS-9（`config.json` 不再可能被误提交）**本计划刻意不关闭**——按你的决定推迟，理由见 Out of scope。

**差距行（今天 vs 理想，每条带已核实证据）：**

| ID | 关闭 | 证据（file:line，均已直接读取核实） |
|---|---|---|
| GAP-1 | IS-1 | `infrastructure/adb.py:142` 用 `;` 拼 8 个 getprop；`:143` `[ln.strip() for ln in out.splitlines() if ln.strip()]` **过滤空行**；`:144` `dict(zip(keys, vals + [""] * len(keys)))` —— 无行数校验、zip 永不抛、多余行静默丢弃。唯一调用方 `infrastructure/snapshot.py:18-22` 只捕 `AdbError`，串位 dict 被无告警消费。`props` 零测试覆盖 |
| GAP-2 | IS-2 | `interfaces/json_io.py:14-16` 裸 `open(out_path, "w", ...)` 直写目标。对照 `infrastructure/device_config.py:32` mkstemp + `:36` os.replace 的原子模式。唯一 `emit_json` 测试是 `tests/selftest_tree.py:2056-2065`（只验字节数与 LF），无失败原子性覆盖 |
| GAP-3 | IS-3 | `infrastructure/adb.py:96` `ok = "connected" in msg.lower() and "cannot" not in msg.lower()`——靠回显措辞猜。对照 `:128-130` `connect()` 用的更强判据。`_reconnect` 零测试覆盖 |
| GAP-4 | IS-4 | `infrastructure/image.py:162-165` `try: dr.text(...) except Exception: pass`——notes 未追加任何内容。返回元组 `(drawn, skipped, notes)` 在 `:175`；`interfaces/shot.py:69-72` 会打印 notes，通道现成只是没用 |
| GAP-5 | IS-5 | `domain/component.py:12` 严格正则与 `:15` 回退正则**都**允许无点号的包名组（`[A-Za-z][\w.]*`）。实测 `Window{abc u0 uid/1000}` 由**严格正则**命中并返回 `uid/1000`。下游 `domain/tree/parsing.py:131-146` 容忍伪组件，返回 `blocks[-1]` + note |
| GAP-6 | IS-6 | `requirements.txt:4` `uiautodev`；全库 grep 仅该行 + 旧计划 `2026-10-02-comment-naming-structure.md:39` 的备注。所有 .py/.ps1 零引用 |
| GAP-7 | IS-7 | `infrastructure/adb.py:15-22`；个人路径为 `D:\platform-tools\adb.exe` 与 `D:\SoftwareInstalled\Android\android_sdk\platform-tools\adb.exe` |
| GAP-8 | IS-8 | `infrastructure/adb.py:131-134` serial 为空时自动选 `targets[0]` 并**改写 `self.serial`**。仓内不可达（`application/connection.py:20-21` target 恒为 `ip:port`、`:24-31` 拒空串与含 `:`；`scripts/bench_screencap.py:56-61` 恒返回 `ip:port`；`tvuitree/__init__.py:3,5` 只导出接收已建好 Adb 的两个函数）。属外部库 API 隐患，零测试覆盖 |
| GAP-11 | IS-11 | 三个 CLI 调用点都在 try/except **之外**调 `emit_json`：`interfaces/observe.py:40`（try 覆盖 `:28-39`）、`interfaces/tree.py:118`（try 覆盖 `:104-114`）、`interfaces/visible.py:38`（try 覆盖 `:27-37`）。故 `--out` 写失败会以未捕获 OSError → traceback → 退出码 1 结束，违反 AGENTS.md:17 的「文件错误 → 2」 |
| GAP-10 | IS-10 | 计划文档即本文件 |

**GAP-5 的实测验证表**（用项目 venv `.\.venv\Scripts\python.exe` 执行，Python 3.14.3；这一节推翻了 Metis 的原始指令）：

| 输入 | 严格正则 `:12` | 回退正则 `:15` | `component_from_window` 实返 |
|---|---|---|---|
| `Window{689d118 u0 com.android.tv.settings/com.android.tv.settings.MainSettings}` | 命中 | 命中 | 正确 |
| `  mFocusedWindow=Window{abc u0 com.demo/.MainActivity}` | 命中 | 命中 | 正确 |
| **`Window{abc u0 uid/1000}`** | **`uid/1000`** | `uid/1000` | **`uid/1000`（伪）** |
| `mCurrentFocus=uid/1000`（无右括号） | None | `uid/1000` | `uid/1000`（伪） |
| `Window{1a2b u0 uid/1000 com.foo/com.foo.Bar}` | `com.foo/com.foo.Bar` | `uid/1000` | 正确（严格正则先胜） |
| `ActivityRecord{4b5c200 u0 com.android.tv.settings/.MainSettings t339}` | None | 命中 | 正确 |

真实设备串取自 `_temp/e2e/full.json:50-51`。结论：缺陷在**两条**正则里；修法两处的点号组都必须是 `+`（一个或多个），`*` 不要求点号因而无效。

### Must have

- 8 项 GAP（1,2,3,4,5,6,7,8）+ 1 项新发现（11）全部关闭，每项都有离线可执行的回归断言（GAP-6 除外，见 T6）。
- 每个任务提交前跑完整检查块，**每条命令独立检查退出码**（PowerShell 不会为一个块自动做这件事）。
- 新增测试写进**新的编号 `t.group` 段**（T1→13、T2→14、T3→15、T4→16、T5→17、T6→18），第 0–12 段保持逐字节不变。
- 所有新代码：Python 3.10+、四空格、UTF-8、带类型注解；模块文档一行英文，函数/类文档与行内注释中文，用户可见串中文；`tvuitree/` 下库模块不加 shebang/coding cookie。
- 每个任务的 `git add` 只列本任务文件；提交前跑 `git diff --cached --check` / `--stat` / 全量 `git diff --cached` 审查。

### Must NOT have（护栏，防未请求的扩张；不是范围缩减）

- 不得改 JSON 字段名/口径、CLI 退出码语义、MCP 工具名/入参 schema/返回键集合。
- 不得改 `generator` 的 `tv_tree.py` 值。
- 不得改 R0–R3 配对规则、剪枝 `OWNER_PRIORITY` 认领顺序、`merge_children`/`geom_of` 单一判据来源。
- 不得改 `infrastructure/image.py` 的「框 = 读数、逐像素对齐、不加偏移、不补偿」约定，不得引入容差启发式。
- 不得让 domain 层访问设备/文件/终端/MCP/Pillow/uiautomator2（GAP-5 的修复必须保持纯正则）。
- 不得把 `emit_json` 描述成「缺 UTF-8/LF 处理」——它 `:15` 已经有 `encoding="utf-8", newline="\n"`，**只缺原子性**。
- 不得让 `props()` 抛 `AdbError` 以外的异常类型。
- 不得让 `connect()` 为多设备情形抛异常（必须返回 False）。
- 不得把 `json_io.emit_json` 搬到 infrastructure——`selftest_tree.py:2116-2120` 断言它存在于 `tvuitree.interfaces.json_io`，搬家会破坏既有断言且属范围外重构。
- 不得改 `component_from_activity_record`（`component.py:19-24`，独立函数，其测试在 `:333-335`）。
- 不得改 `connect()` 对**已指定 serial** 的 `adb devices` 成员判据（`:130`）——只有 `_reconnect` 升级为状态判据。
- 不得 `git add` `.omo/`、`config.json`、`_temp/` 下任何东西。
- 不得对 golden 跑 `make`（重建基线）；只跑 `check`，且要求零差异。
- 不得为 T7 的 README 句子新建文本 grep 断言（README 已被机器检查）。
- 不得迁移到 pytest、不得重构 `snapshot()` 的字符串键 dict、不得重命名终端 `C`/`c()`。

### Out of scope（需用户另开任务）

- **GAP-9 / IS-9：`config.json` 的 git 追踪策略。** 按你的明确决定，本计划不动。它当前受 git 跟踪且含真实内网地址 `192.168.1.147` 与个人 adb 路径 `D:\platform-tools\adb.exe`。旧计划 `2026-10-02-comment-naming-structure.md:38` 已把它列为「需用户另开任务」。
  **为什么这不是「顺手就能做」**：`tests/selftest_tree.py:339-346`（第 0 段）**打开仓库真实的 `config.json`** 并断言 `connection.options_from_args(...).target == f"{cfg['TV_IP_Address']}:{cfg['port']}"` 与 `.adb == cfg['adb']`。取消追踪会直接打断离线自检，必须同时重写第 0 段。这是不可逆的跨切面仓库策略变更，会改动所有贡献者的 clone 流程、README 快速开始段、`device_config.CONFIG_PATH` 的缺失报错文案、以及 `set_default_device` 的 `config_path` 返回语义。
- 拆 `requirements.txt` / 钉版本（GAP-6 只删 `uiautodev` 一行）。
- 把 `snapshot()` 的字符串键 dict 改成 dataclass。
- 迁移到 pytest；重命名终端 `C` / `c()`（约 58 处）。
- 合并 `observation._path_text` 与 `visible._path_text`（根节点一个返回 `"root"`、一个返回 `""`，语义不同）。
- MCP 采集的整体超时与取消机制（上一轮评审的 M2）。
- u2 设备对象按 serial 缓存复用（上一轮评审的 M3）：会引入缓存失效语义（`set_default_device` 切换后必须失效）。
- 把 `_temp/golden/` 提升为受版本控制的金样：`_temp/` 是 gitignore 的调查产物，本计划只**读**它做验证。

---

## Verification strategy

**测试策略：沿用仓库既有的 RED→GREEN 逐任务锁（你选定）。** 每个任务：先往 `tests/selftest_tree.py` 追加失败断言 → 跑自检确认退出码 1 且失败文本正是目标缺陷 → 最小实现 → 跑完整检查块要求退出码 0 → 精确暂存 + staged diff 审查 + 提交。**全部离线，不需要 TV/ADB/网络。**

**顺序脚本的中止防护（5 条硬性 RED 规则，Metis 提出、本计划采纳并已核实可行性）：** `tests/selftest_tree.py` 是顺序脚本，`sys.exit(t.summary())` 在 `:2149`；未捕获的 TypeError/AttributeError/IndexError 会让整场提前退出、后面的段跑不到（旧计划 Task 3/5 Step 1 踩过）。因此：

1. 任何断言**新异常类型**的测试必须 `try: ... except Exception as exc:` 然后 `isinstance(exc, ...)`；**禁止** `t.eq(type(exc), X)`——GREEN 阶段若类型不符会直接中止整场，而不是记一条失败。
2. ADB 假件必须重写 **`_popen`**，不是 `shell`——`connect()` 在 `adb.py:128` 直接调 `self._popen(["devices"])`。
3. 假件必须**按命令名分派**（`connect`/`devices`/`shell`/`exec-out`），不是位置响应队列——GAP-3 的 GREEN 会在 `_reconnect` **内部**新增一次 `devices` 调用，位置队列会失同步并抛 IndexError 中止整场。
4. 新测试追加为**新的编号段**（T1→13、T2→14、T3→15、T4→16、T5→17、T6→18），第 0–12 段不动。
5. RED 断言里读取任何**尚不存在**的模块属性必须用 `getattr(mod, "name", None)`（先例：`selftest_tree.py:2142`）。

**既有硬约束（改这些文件时必须保住，全部已核实）：**

- `selftest_tree.py:1108-1111`：`draw_boxes(..., show_details 默认 True, label="")` 后断言 `(okX, skX, notesX) == (1, 0, [])`——**notes 必须恰好是空列表**。故 GAP-4 只允许在 `except` 分支追加 note，正常路径不得追加任何 note。
- `:1167` `"screencap"` 必须留在 `infrastructure/image.py`；`:1173` `"逐像素对齐"` 与 `"不加偏移"` 必须留在其中；`:1175-1178` 禁止子串 `abs(sx - 1.0) > 0.01`、`0.9 <= kx`、`<= 1.2`；`:1179` 禁止 `cl - w` / `ct - w`；`:1169` 禁止 `fetch_u2` / `parse_dumpsys_top`。
- `:1159-1162` `"screencap"` / `"input keyevent"` 不得出现在 `application/observation.py` 与 6 个 `domain/tree/*` 模块中；`:1168` `"input keyevent"` 必须在 `application/input.py`；`:1181` `"build_full_json"` 不得在 `application/input.py`。
- `:1183-1195` README 必须含全部剪枝开关名、`main.py`/`tvuitree/`/`domain/`/`application/`/`infrastructure/`/`interfaces/`/`tests/`、以及 `画框约定`/`--width`/`不加偏移`/`逐像素`/`不补偿`。
- `:2056-2065` `emit_json` 的 stderr 必须按真实 UTF-8 字节数（含末尾 LF）报数，且输出为 LF 不含 CRLF。
- `:339-346` 第 0 段读**真实** `config.json`——故本计划不得改动 `config.json`。
- `:1313-1315` `get_focus_screenshot` 的返回键集合固定为 `{focus_found, screenshot_captured, focus_marked, image_path, image_base64}`。GAP-4 不得影响它：`dr.text` 只在 `show_details=True` 时执行（`image.py:160-163`），而 MCP 走 `show_details=False`（`application/screenshot.py:34`），所以 MCP 路径天然不受影响。
- `infrastructure/adb.py` **不在**任何源文本断言的覆盖范围内（`:1148-1170` 只覆盖 observation/tree 六模块/domain observation/interfaces observe/image/input），故 T4/T5/T6 可自由编辑 adb.py。
- 画框测试在未装 Pillow 时被跳过（`:1145`）——T2 的 QA 必须声明「需要 Pillow，否则该断言不执行」。

**完整检查块（每个任务提交前跑，逐条检查退出码）：**

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
# 离线 --from-json 三条（AGENTS.md 推荐；_temp/e2e/full.json 存在时可跑）
if (Test-Path _temp/e2e/full.json) {
  & $py main.py observe --from-json _temp/e2e/full.json --out NUL
  if ($LASTEXITCODE -ne 0) { throw 'offline observe failed' }
  & $py main.py visible --from-json _temp/e2e/full.json --out NUL
  if ($LASTEXITCODE -ne 0) { throw 'offline visible failed' }
  & $py main.py tree --from-json _temp/e2e/full.json --mode slim --out NUL
  if ($LASTEXITCODE -ne 0) { throw 'offline slim failed' }
} else { Write-Warning '_temp/e2e/full.json 缺失，跳过离线 --from-json 检查' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
```

> `--out NUL` 依赖 T3 的 Windows 设备名特判，所以 T3 之后这个块才真正安全；T1/T2 阶段它走的是现有裸 `open` 路径，也能通过。

**金样检查（本地证据，绝不入库）：** `_temp/golden/golden.py`（`make` 生成基线 / `check` 重生成到 `now/` 并比对）与 `_temp/golden/base/` 的 19 个文件**本地存在**（含 `shot_focus.png`/`shot_all.png`/`shot_actionable.png` 及其 `.txt`，`observe.txt`/`slim.txt`/`visible.txt`/`keep_all.txt`/`keep_gone.txt`、全部 `.json`、`rebuilt_full.json`、`prune_list.txt`、`input_list.txt`），`_temp/e2e/full.json` 也存在。`_temp/` 被 gitignore，故金样是**本地验证证据，永不暂存或提交**。

```powershell
if (Test-Path _temp/golden/golden.py) {
  & $py _temp/golden/golden.py check
  $g = $LASTEXITCODE
  if ($g -notin @(0,1)) { throw 'golden runner failed' }
  if ($g -eq 1) { throw 'golden 有差异：必须先解释，禁止 make 重建基线' }
} else { Write-Warning '_temp/golden/ 缺失，跳过金样检查' }
```

在**第一次生产代码修改之前**跑一次确立基线，之后在 T1/T2/T3 各跑一次（这三个任务碰到金样捕获的输出：`[out] ... 字节` stderr 行、shot notes/PNG）。**预期零差异**；出现差异必须解释，绝不用 `make` 消除。GAP-2 的临时文件若不清理，会触发金样的「新文件」失败——这是 T3 必须 unlink 临时文件的原因之一。

**基线（本次评审已实测）：** `py_compile` 通过、`pyflakes` 退出码 0、`selftest_tree.py` **714 条断言全部通过**、`git status` 干净（仅未跟踪的 `.omo/`）。当前 13 个编号段（0–12）。

**QA 证据路径约定：** 每个任务的 QA 输出写进 `_temp/plan-evidence/code-review-remediation/T<happy|fail>.txt`（`_temp/` 已 gitignore，仅本地留证）。终验波的审查者按这些路径取证。

---

## Execution strategy

**单一顺序链，7 个实现任务 + 1 个终验波。** 不做并行，原因是硬性的：7 个任务全部要追加到同一个 `tests/selftest_tree.py`，且每个任务都必须以「全量自检绿」收尾——并行会在测试文件上冲突，也会让「谁的断言失败了」无法归因。

**执行顺序与理由**（风险从低到高；纯函数在前，需要假件的在后；共享假件者相邻）：

| 序 | 任务 | 关闭 | 依赖 | 理由 |
|---|---|---|---|---|
| T1 | component 双正则收紧 | GAP-5 | 无 | 纯 domain 函数，无需假件；正则形态已实测确定，风险最低，先落地建立新段 13 的写法范式 |
| T2 | 画框标签失败留 note | GAP-4 | 无 | 单文件、单 `except` 分支；需 Pillow；受既有 notes==[] 约束最多，早做早发现 |
| T3 | `emit_json` 原子写 + 写失败退出码 | GAP-2, GAP-11 | 无 | 触及 4 个文件但逻辑独立；`--out NUL` 特判是后续检查块的前提 |
| T4 | `props()` 行数校验 | GAP-1 | 无 | **在此建立 ADB 假件**（重写 `_popen`、按命令名分派） |
| T5 | `_reconnect` 状态判据 + 空 serial 防御 | GAP-3, GAP-8 | **T4 的假件** | 复用 T4 假件，故必须紧随其后 |
| T6 | 依赖与探测路径卫生 | GAP-6, GAP-7 | 无 | 纯删除，零逻辑风险，放在行为修复之后 |
| T7 | 文档核对（预期近零改动） | IS-10 | T1–T6 | 最后跑，此时才知道有没有真的改了用户可见接口 |

**任务结构统一为：** Files → Interfaces（Consumes/Produces）→ Step 1 写失败断言（RED）→ Step 2 跑自检确认退出码 1 且失败原因正确 → Step 3 最小实现（GREEN）→ Step 4 完整检查块（含金样，退出码 0）→ Step 5 精确暂存 + staged diff 审查 + 提交。

**失败即停：** 任何一步退出码非预期就停下定位，不把它算作「新增失败测试」，也不带着红提交。

**任务依赖矩阵：** 7 个任务构成「T4 → T5」一条硬链 + 5 个独立任务 + 1 个收尾任务。矩阵列出每个任务依赖谁、产出什么给谁用、以及在哪一步共享同一测试段。

| 任务 | 依赖（必须先完成） | 被谁依赖 | 共享测试段 | 产出给下游用的东西 | 可并行 |
|---|---|---|---|---|---|
| T1 component 正则 | 无 | 无 | 新增第 13 段（独占） | 无（终点任务） | 与 T2/T3/T4/T6 可并行，但**不建议**（见下） |
| T2 画框 note | 无 | 无 | 新增第 14 段（独占） | 无（终点任务） | 同上 |
| T3 原子写 + 退出码 | 无 | 无 | 新增第 15 段（独占） | `--out NUL` 特判 → 使完整检查块的离线三条安全 | 同上 |
| T4 props() + ADB 假件 | 无 | **T5** | 新增第 16 段（**定义 `_FakeAdbPopen` / `_fake_adb`，T5 复用**） | `_FakeAdbPopen`、`_fake_adb` 测试假件 | 同上 |
| T5 _reconnect + connect | **T4**（假件） | 无 | **追加进第 16 段之后的第 17 段**，import T4 的假件 | 无（终点任务） | **不可**与 T4 并行 |
| T6 依赖/路径卫生 | 无 | 无 | 新增第 18 段（独占，仅源文本断言） | 无（终点任务） | 同上 |
| T7 文档核对 | T1–T6 全部 | 无 | 不新增段（只读核对 + 可能的 README 一句话） | 计划交付 | **不可**提前 |

依赖边只有两条：
1. **T4 → T5（硬）**：T5 的 RED 断言直接引用 T4 在第 16 段定义的 `_FakeAdbPopen` / `_fake_adb`；T5 先跑则 NameError 中止整场（违反规则 4 的精神）。T5 必须排在 T4 之后，且**不重复定义**假件。
2. **T1–T6 → T7（软，顺序性）**：T7 只有在全部行为任务落地后才能判断「有没有真的改了用户可见接口」，提前跑会得出错误结论（README 句子该不该加取决于 T3 的实际行为）。

**为什么其余任务仍按顺序跑而不并行**：7 个任务都要追加到同一个 `tests/selftest_tree.py`，且每个都必须以「全量自检绿」收尾；并行编辑同一文件会冲突，且失败断言无法归因到具体任务。矩阵确认它们**无数据依赖**，因此顺序执行不引入额外等待；若未来要在 worktree 里并行，只能按 {T1, T2, T3, T4, T6} 五个独立任务并行、T5 串在 T4 后、T7 收尾，且每个 worktree 各自跑完整检查块。

每个任务的「Step 5 精确暂存」列出的文件就是它的**输出边界**；跨任务文件（`tests/selftest_tree.py`）由每个任务各自追加自己的段，互不重叠（第 13/14/15/16+17/18 段各归其主）。

**分支策略：** 沿用上一份计划的做法——在 `main` 原地执行，不开分支、不提 PR、不 push/merge（`2026-10-02-comment-naming-structure.md:24` 与文末执行裁决第 1 条）。若你要 PR 流程，用 `/ulw-execute --make-pr`。

---

## Todos

- [ ] 1. T1 `domain/component.py`：两条正则都要求包名含点号，钉死 `uid/1000` 不再被当成 component

  **关闭：** GAP-5 / IS-5

  **References（执行者没有访谈上下文，以下全部要读）：**
  - `tvuitree/domain/component.py:8-16` —— `component_from_window` 全文；`:12` 严格正则 `r"\s([A-Za-z][\w.]*)/([\w.$]+)\}"`，`:15` 回退正则 `r"([A-Za-z][\w.]*)/([\w.$]+)"`。
  - `tvuitree/domain/component.py:19-24` —— `component_from_activity_record`，**独立函数，本任务不得改动**。
  - `tvuitree/domain/tree/parsing.py:123-146` —— `pick_block`：精确匹配失败时返回 `blocks[-1]` + note（`:139-142` 有 want、`:143-145` 无 want）。这是伪组件的下游后果，本任务不改它，但要理解为什么 IS-5 重要。
  - `tests/selftest_tree.py:326-338` —— 现有 component 断言（`normalize_component` ×3、`component_from_activity_record` ×1、`component_from_window` ×1 用 `Window{abc u0 com.demo/.MainActivity}`）。**必须全部继续通过。**
  - `_temp/e2e/full.json:50-52` —— 真机串：`mCurrentFocus` = `Window{689d118 u0 com.android.tv.settings/com.android.tv.settings.MainSettings}`，`mFocusedApp` = `ActivityRecord{4b5c200 u0 com.android.tv.settings/.MainSettings t339}`。
  - `tvuitree/infrastructure/adb.py:169-181` —— `window_focus()` 是 `component_from_window` 的唯一生产调用方（喂 `mCurrentFocus` / `mFocusedApp`）。
  - `tvuitree/domain/tree/models.py:37-46` —— `NODE_RE_POST_NAME`：Android 16 的 `DecorView{...}[MainSettings]` 是**节点行**解析，与 `component_from_window` 无关，本任务不得以「兼容 Android 16」为由放宽正则。
  - 本计划 Scope 里的「GAP-5 实测验证表」——那是已执行过的真实输出，直接作为断言语料与修法依据。

  **Interfaces：**
  - Consumes: 无。
  - Produces: `component_from_window(text)` 对包名不含点号的输入返回 `None`；对全部真机格式保持原返回值。签名与返回类型不变。

  **Step 1（RED）：** 在 `tests/selftest_tree.py` 第 12 段之后、收尾（`shutil.rmtree(TD, ...)` / `sys.exit(t.summary())`，约 `:2146-2149`）之前，新增第 13 段：

  ```python
  # ================================================================== 13. component 解析加固

  t.group("13. component_from_window 拒绝非 component 子串")

  # 真机格式（取自 _temp/e2e/full.json）必须继续解析出正确 component
  t.eq(component.component_from_window(
      "Window{689d118 u0 com.android.tv.settings/com.android.tv.settings.MainSettings}"),
      "com.android.tv.settings/com.android.tv.settings.MainSettings",
      "真机 mCurrentFocus 的全限定类名格式仍解析正确")
  t.eq(component.component_from_window("  mFocusedWindow=Window{abc u0 com.demo/.MainActivity}"),
      "com.demo/.MainActivity", "短类名 .Cls 格式仍解析正确（包名有点号）")
  t.eq(component.component_from_window("mCurrentFocus=com.demo/.MainActivity"),
      "com.demo/.MainActivity", "无右括号但包名有点号时仍走回退解析")
  # 同一串里既有伪 token 又有真 component：严格正则应先命中真的那个
  t.eq(component.component_from_window("Window{1a2b u0 uid/1000 com.foo/com.foo.Bar}"),
      "com.foo/com.foo.Bar", "串里同时有 uid/1000 与真 component 时取真 component")
  # 核心回归：uid/1000 不是 component，两种形状都必须返回 None
  t.eq(component.component_from_window("Window{abc u0 uid/1000}"), None,
      "有右括号的 uid/1000 不再被严格正则当成 component")
  t.eq(component.component_from_window("mCurrentFocus=uid/1000"), None,
      "无右括号的 uid/1000 不再被回退正则当成 component")
  t.eq(component.component_from_window("uid/1000"), None, "裸 uid/1000 返回 None")
  t.eq(component.component_from_window(None), None, "None 输入仍返回 None")
  t.eq(component.component_from_window(""), None, "空串仍返回 None")
  # 独立函数不得被牵连
  t.eq(component.component_from_activity_record(
      "  ACTIVITY com.demo/.MainActivity deadbeef pid=100 userId=0"),
      "com.demo/.MainActivity", "component_from_activity_record 不受本任务影响")
  ```

  > 顶部 `:58` 已有 `from tvuitree.domain import component, ...`，不要重复导入。

  **Step 2：** 跑 `& $py tests/selftest_tree.py`。**期望退出码 1**，汇总块正常打印（证明没中止），失败项恰好是三条 `uid/1000 → None` 断言（当前实返 `'uid/1000'`），其余全绿。**不得**在这一步改生产代码去凑绿。

  **Step 3（GREEN）：** 改 `tvuitree/domain/component.py` 的两条正则，包名组改为「至少含一个点号」。已实测确定的最终形态：

  ```python
  def component_from_window(text: Optional[str]) -> Optional[str]:
      """`Window{... u0 com.pkg/.Cls}` → `com.pkg/.Cls`

      包名组要求至少含一个点号：真机 component 的包名恒为反向域名，
      而 `uid/1000` 这类窗口字段没有点号。不收紧就会把 `uid/1000` 当成
      前台 component，进而让 pick_block 回退到最后一个 ACTIVITY 段——
      那可能是另一个页面的树。
      """
      if not text:
          return None
      m = re.search(r"\s([A-Za-z][\w]*(?:\.[\w]+)+)/([\w.$]+)\}", text)
      if m:
          return f"{m.group(1)}/{m.group(2)}"
      m = re.search(r"\b([A-Za-z][\w]*(?:\.[\w]+)+)/([\w.$]+)", text)
      return f"{m.group(1)}/{m.group(2)}" if m else None
  ```

  **关键点：两处的点号组都必须是 `+`（一个或多个），不能是 `*`。** 实测 `(?:\.[\w]+)*` 因为是「零或多个」而根本没要求点号，`Window{abc u0 uid/1000}` 仍会返回 `uid/1000`。`component_from_activity_record` 与 `normalize_component` 保持原样。domain 层必须保持纯正则、不碰设备/文件。

  **Acceptance criteria（代理可执行）：**
  - `component_from_window("Window{abc u0 uid/1000}") is None`
  - `component_from_window("mCurrentFocus=uid/1000") is None`
  - `component_from_window("Window{689d118 u0 com.android.tv.settings/com.android.tv.settings.MainSettings}") == "com.android.tv.settings/com.android.tv.settings.MainSettings"`
  - `component_from_window("  mFocusedWindow=Window{abc u0 com.demo/.MainActivity}") == "com.demo/.MainActivity"`
  - `component_from_window("Window{1a2b u0 uid/1000 com.foo/com.foo.Bar}") == "com.foo/com.foo.Bar"`
  - `component.py` 中 `(?:\.[\w]+)+` 出现 2 次，`(?:\.[\w]+)*` 出现 0 次
  - `component_from_activity_record` 与 `normalize_component` 的源码逐字节未变

  **QA — happy path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.domain import component as c; print(c.component_from_window('Window{689d118 u0 com.android.tv.settings/com.android.tv.settings.MainSettings}')); print(c.component_from_window('Window{abc u0 uid/1000}'))"
  ```
  期望 stdout 第一行是真机 component、第二行是 `None`。证据写入 `_temp/plan-evidence/code-review-remediation/T1-happy.txt`。

  **QA — failure path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.domain import component as c; print([c.component_from_window(s) for s in ('Window{a u0 uid/1000}','uid/1000','mCurrentFocus=uid/1000',None,'')])"
  ```
  期望输出 `[None, None, None, None, None]`——五种非 component 输入全部拒绝，无一被猜成组件。证据写入 `_temp/plan-evidence/code-review-remediation/T1-fail.txt`。

  **Step 4：** 跑完整检查块 + 金样 check。期望全部退出码 0、金样零差异、自检断言数 > 714 且全绿。

  **Step 5（提交）：**
  ```powershell
  git add tvuitree/domain/component.py tests/selftest_tree.py
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
  git diff --cached --stat
  git diff --cached
  git commit -m "fix(component): 拒绝窗口焦点解析中的非 component 子串"
  ```
  staged diff 不得混入 `config.json`、`.omo/`、`_temp/` 或其他任务改动。

  Recommended task executor category: `quick` — 单个纯函数、正则形态已实测确定、断言语料已给全，属机械替换。

- [ ] 2. T2 `infrastructure/image.py`：`dr.text` 失败时把原因写进 notes，不再静默吞掉

  **关闭：** GAP-4 / IS-4

  **References：**
  - `tvuitree/infrastructure/image.py:160-165` —— `if show_details:` 块内 `_cross(...)` 与 `try: dr.text(...) except Exception: pass`。
  - `tvuitree/infrastructure/image.py:88-175` —— `draw_boxes` 全文；返回 `(drawn, skipped, notes)` 在 `:175`；`notes` 的既有追加风格见 `:109-125`（换算说明）、`:134-141`（零面积/完全屏外）、`:151-154`（真越界）、`:169-173`（压外沿汇总，用 `notes.insert(0, ...)`）。
  - `tvuitree/infrastructure/image.py:1-3` —— 文件头「画框约定：框 = 读数，逐像素对齐、不加偏移。」**必须保留**。
  - `tvuitree/application/screenshot.py:24-35` —— `render_focus_png` 用 `show_details=False`，故 MCP 焦点截图不走 `dr.text`。
  - `tvuitree/interfaces/shot.py:69-72` —— 打印 notes（上限 20 条 + 溢出汇总行）。
  - `tests/selftest_tree.py:1108-1111` —— **硬约束**：`draw_boxes(..., [(100,120,200,180,"","reading")], ..., canvas)` 后断言 `(okX, skX, notesX) == (1, 0, [])`，`show_details` 用默认 True 所以 `dr.text` 会被调用（空标签）。正常路径**绝不能**追加 note。
  - `tests/selftest_tree.py:1126-1133` —— 带标签 `"标签"` 的画框，只断言像素不断言 notes。
  - `tests/selftest_tree.py:1145` —— 未装 Pillow 时画框测试整段跳过（`has_pil` 守卫，另见 `:1303`）。
  - `tests/selftest_tree.py:1159-1181` —— `image.py` 的源文本断言全集（见 Verification strategy 的既有硬约束清单）。
  - `tests/selftest_tree.py:1313-1315` —— `get_focus_screenshot` 返回键集合固定，本任务不得影响。

  **Interfaces：**
  - Consumes: 无。
  - Produces: `draw_boxes` / `draw_boxes_png` 的签名与返回元组形状**不变**；仅当 `dr.text` 抛异常时，`notes` 多一条中文说明。

  **Step 1（RED）：** 新增第 14 段。用 monkeypatch 让 `ImageDraw` 的 `text` 方法抛异常，验证 notes 会记录；并在 `finally` 中还原。必须 `has_pil` 守卫。

  ```python
  # ================================================================== 14. 画框标签失败要留痕

  t.group("14. draw_boxes 标签绘制失败时写进 notes")

  if has_pil:
      from PIL import ImageDraw as _ImageDraw
      _orig_text = _ImageDraw.ImageDraw.text

      def _raise_text(self, xy, text, fill=None, *a, **k):
          raise OSError("fixture: font unavailable")

      _label_png = os.path.join(TD, "label_fail.png")
      _blank = io.BytesIO()
      Image.new("RGB", (400, 300), (0, 0, 0)).save(_blank, format="PNG")
      _canvas = {"width": 400, "height": 300}
      _boxes = [(100, 120, 200, 180, "A11Y 读数 | TextView#title", "reading")]

      # 正常路径：标签能画，notes 不含标签失败说明（钉死 :1108-1111 的约定）
      _ok, _sk, _notes = image.draw_boxes(_blank.getvalue(), _boxes, _label_png, _canvas)
      t.eq((_ok, _sk), (1, 0), "正常画框仍然画出 1 个、跳过 0 个")
      t.ok(not any("标签绘制失败" in n for n in _notes),
           "标签画得出来时不得追加失败说明", repr(_notes))

      # 失败路径：text 抛异常 → 框照画，但 notes 必须说明标签丢了
      _ImageDraw.ImageDraw.text = _raise_text
      try:
          _ok2, _sk2, _notes2 = image.draw_boxes(_blank.getvalue(), _boxes, _label_png, _canvas)
      finally:
          _ImageDraw.ImageDraw.text = _orig_text
      t.eq((_ok2, _sk2), (1, 0), "标签画不出来不影响框本身：仍算画出 1 个")
      t.ok(any("标签绘制失败" in n for n in _notes2),
           "标签绘制失败必须在 notes 里说明，不能静默吞掉", repr(_notes2))
      t.ok(any("TextView#title" in n for n in _notes2),
           "失败说明要带上是哪个标签", repr(_notes2))
      _im2 = Image.open(_label_png).convert("RGB")
      t.eq(_im2.getpixel((100, 150)), image.COLOR_READING,
           "标签失败时框线仍严格落在读数上（几何不受影响）")
  else:
      print("  （跳过标签失败测试：未安装 Pillow）")
  ```

  > `Image` / `io` / `os` / `TD` / `has_pil` / `image` 均已在前文导入或定义（`has_pil` 守卫见 `:1145`、`:1303`）。若 `has_pil` 变量名与实际不符，以文件里真实的守卫变量为准，不要另造。

  **Step 2：** 跑自检。**期望退出码 1**，失败项是「标签绘制失败必须在 notes 里说明」与「失败说明要带上是哪个标签」两条（当前 `except: pass` 什么都不留），汇总块正常打印。`:1108-1111` 与正常路径断言应保持绿。

  **Step 3（GREEN）：** 只改 `image.py:162-165` 的 `except` 分支：

  ```python
          if show_details:
              _cross(dr, rect, color)
              try:
                  dr.text((rect[0] + 2, max(0, rect[1] - 13)), label, fill=color)
              except Exception as error:
                  # 标签画不出来时框线仍然有效，但「图上没有文字」必须可解释：
                  # 否则与「本来就没有标签」无法区分，而 shot 的用途正是拿读数核对画面。
                  notes.append(f"框标签绘制失败，图上只有框线没有文字：{label}"
                               f"（{type(error).__name__}: {error}）")
  ```

  不得改 `_stroke_rect` / `_band` / `_cross` / `to_pixel` / `scale_factors` 的任何几何；不得改文件头画框约定注释；不得引入容差。

  **Acceptance criteria：**
  - `dr.text` 抛异常时，`draw_boxes` 返回的 `notes` 含一条以「框标签绘制失败」开头、且含该框 label 的中文说明
  - `dr.text` 正常时，`notes` 不含任何「标签绘制失败」字样（`:1108-1111` 的 `notesX == []` 继续成立）
  - 返回元组仍为 `(drawn, skipped, notes)`，`drawn`/`skipped` 计数不因标签失败而改变
  - `image.py` 仍含 `screencap`、`逐像素对齐`、`不加偏移`；仍不含 `fetch_u2`、`parse_dumpsys_top`、`abs(sx - 1.0) > 0.01`、`0.9 <= kx`、`<= 1.2`、`cl - w`、`ct - w`
  - `get_focus_screenshot` 返回键集合不变

  **QA — happy path：**（需要 Pillow）
  ```powershell
  & $py -c "import sys,io,os,tempfile; sys.path.insert(0,'.'); from PIL import Image; from tvuitree.infrastructure import image; b=io.BytesIO(); Image.new('RGB',(400,300),(0,0,0)).save(b,format='PNG'); d=tempfile.mkdtemp(); p=os.path.join(d,'h.png'); print(image.draw_boxes(b.getvalue(),[(100,120,200,180,'lbl','reading')],p,{'width':400,'height':300}))"
  ```
  期望输出 `(1, 0, [])`——正常路径 notes 为空。证据写入 `_temp/plan-evidence/code-review-remediation/T2-happy.txt`。

  **QA — failure path：** 用 T2 RED 里同一个 monkeypatch 片段（`ImageDraw.ImageDraw.text` 抛 `OSError`）跑一次，期望 `notes` 含「框标签绘制失败」且 `drawn` 仍为 1。证据写入 `_temp/plan-evidence/code-review-remediation/T2-fail.txt`。若环境未装 Pillow，本 QA 记为「跳过」并在证据文件里写明原因，不得伪报通过。

  **Step 4：** 完整检查块 + 金样 check。金样含 `shot_focus.png` / `shot_all.png` / `shot_actionable.png` 及其 `.txt`，**期望零差异**（本改动只在异常分支追加 note，正常路径输出不变）。

  **Step 5（提交）：**
  ```powershell
  git add tvuitree/infrastructure/image.py tests/selftest_tree.py
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
  git diff --cached --stat
  git diff --cached
  git commit -m "fix(image): 截图标签绘制失败时写入 notes 而非静默吞掉"
  ```

  Recommended task executor category: `quick` — 单文件单 `except` 分支，几何与约定全部冻结，断言已给全。

- [ ] 3. T3 `interfaces/json_io.py` 原子写 + 三个 CLI 调用点的写失败退出码

  **关闭：** GAP-2 / IS-2，GAP-11 / IS-11

  **References：**
  - `tvuitree/interfaces/json_io.py:1-28` —— 全文。`:12-20` `emit_json`（**注意 `:15` 已有 `encoding="utf-8", newline="\n"`，只缺原子性**）；`:23-28` `load_full_json`（不改）。
  - `tvuitree/infrastructure/device_config.py:28-42` —— 要复用的原子写模式：`tempfile.mkstemp(prefix=..., suffix=".tmp", dir=target.parent)` → `os.fdopen(fd, "w", encoding="utf-8", newline="\n")` → `os.replace(temp_name, target)`，`except OSError` 里 `os.unlink(temp_name)`（再套一层 `except OSError: pass`）后抛出。
  - `tvuitree/interfaces/observe.py:40-42` —— `emit_json(result, args.out)` 在 try/except（`:28-39`）**之外**，其后是 `[observe] 已生成模型观察 JSON`。
  - `tvuitree/interfaces/tree.py:116-120` —— `emit_json(result, args.out)`（`:118`）在 try/except（`:104-114`）**之外**，其后是 `_summary(result, args.out)`（`:119`）。
  - `tvuitree/interfaces/visible.py:38-41` —— `emit_json(result, args.out)`（`:38`）在 try/except（`:27-37`）**之外**，其后是可见项计数打印。
  - `tvuitree/interfaces/shot.py:20-24, 35-41` —— 既有的文件错误处理范式：`except (OSError, ValueError, TypeError) as error:` → `print(c(str(error), C.RED), file=sys.stderr)` → `return 1`。README:353 记录了 shot 的文件错误用退出码 1。**本任务不改 shot。**
  - `AGENTS.md:17` —— 「Exit codes are `2` for usage, file, or connection errors and `3` for capture failures, while `shot` and `input` return `1` for their own failures.」→ observe/tree/visible 的 `--out` 写失败属**文件错误 → 2**。
  - `tests/selftest_tree.py:2056-2065` —— **必须继续通过**：`emit_json({"tree": [], "note": "中文"}, _out)` 后断言 stderr 含 `（{len(payload)} 字节）`（payload 为二进制读回，含末尾 LF），且 `payload.endswith(b"\n") and b"\r\n" not in payload`。
  - `tests/selftest_tree.py:1940-1941, 1958-1966, 2023-2030` —— 要复用的 `os.replace` 失败注入范式：`_replace_failure(src, dst)` 抛 `PermissionError("fixture locked")`；把 `device_config.os.replace` 换成它，`finally` 还原；断言原文件字节不变、目录里不残留临时文件（`sorted(p.name for p in _config_dir.iterdir()) == ["config.json"]`）。
  - `docs/superpowers/plans/2026-10-02-comment-naming-structure.md:940-944` —— `--out NUL` 是本仓库既有的离线检查写法，原子写必须兼容它。
  - `_temp/golden/golden.py:84-88` —— 金样用真实路径 `--out out/{name}.json|.png`，会走原子分支。
  - `tvuitree/interfaces/tree.py:33-56` —— `_summary(result, args.out)` 只读 obj 打印诊断，不写文件；`--out NUL` 的 stdout 提示与它无关。

  **Interfaces：**
  - Consumes: 无。
  - Produces:
    - `emit_json(obj, out_path)` 签名与 stderr 提示格式**完全不变**（字节数按 UTF-8、含末尾 LF）；写入变为原子；目标是 Windows 保留设备名或 `os.devnull` 时退回普通直写；失败时清理临时文件并让 `OSError` 传播。
    - 新增 `_is_device_target(out_path) -> bool`（私有辅助，json_io 内部）。
    - 新增 `emit_json_checked(obj, out_path) -> Optional[int]`：成功返回 `None`，`OSError` 时打印中文红字到 stderr 并返回 `2`。
    - `observe`/`tree`/`visible` 三个命令在 `--out` 写失败时返回 `2`、stderr 有中文原因、无 traceback、且不打印各自的成功提示行。

  **Step 1（RED）：** 新增第 15 段。两部分：(a) 原子性——注入 `os.replace` 失败，断言目标文件不存在且无临时文件残留；(b) 退出码——用子进程跑真实 CLI，`--out` 指向不可写路径，断言退出码 2、stderr 有说明、无 traceback。

  ```python
  # ================================================================== 15. JSON 输出原子性与写失败退出码

  t.group("15. emit_json 原子写与 --out 写失败的退出码")

  # (a) 原子性：os.replace 失败时不得留下半成品，也不得残留临时文件
  _atomic_dir = Path(TD) / "atomic_out"
  _atomic_dir.mkdir(exist_ok=True)
  _atomic_target = _atomic_dir / "full.json"

  def _replace_failure_jsonio(src, dst):
      raise PermissionError("fixture locked")

  _orig_jsonio_replace = json_io.os.replace
  json_io.os.replace = _replace_failure_jsonio
  try:
      _raised = None
      try:
          json_io.emit_json({"tree": [], "note": "中文"}, str(_atomic_target))
      except Exception as error:          # 宽捕获后 isinstance，避免中止整场
          _raised = error
      t.ok(isinstance(_raised, OSError),
           "os.replace 失败时 emit_json 让 OSError 传播", f"实际 {type(_raised).__name__}")
  finally:
      json_io.os.replace = _orig_jsonio_replace
  t.ok(not _atomic_target.exists(), "写入失败时目标文件不存在（不留半成品）")
  t.eq(sorted(p.name for p in _atomic_dir.iterdir()), [],
       "写入失败时不残留临时文件", str(sorted(p.name for p in _atomic_dir.iterdir())))

  # 成功路径仍按真实 UTF-8 字节数报数、仍是 LF
  _ok_out = _atomic_dir / "ok.json"
  _buf2 = io.StringIO()
  with contextlib.redirect_stderr(_buf2):
      json_io.emit_json({"tree": [], "note": "中文"}, str(_ok_out))
  _payload2 = _ok_out.read_bytes()
  t.ok(f"（{len(_payload2)} 字节）" in _buf2.getvalue(),
       "原子写之后字节数提示仍按实际 UTF-8 长度（含末尾 LF）", repr(_buf2.getvalue()))
  t.ok(_payload2.endswith(b"\n") and b"\r\n" not in _payload2, "仍是 LF，无 CRLF")
  t.eq(json.loads(_payload2.decode("utf-8")), {"tree": [], "note": "中文"}, "内容完整可解析")

  # Windows 设备名 / devnull 必须退回普通直写，不能走 os.replace
  _is_dev = getattr(json_io, "_is_device_target", lambda _p: False)
  for _dev in ([os.devnull] if os.devnull else []) + ["NUL", "CON", "PRN", "AUX", "COM1", "LPT1"]:
      t.ok(_is_dev(_dev), f"{_dev} 被识别为设备目标（走普通直写）")
  t.ok(not _is_dev("full.json"), "普通文件名不是设备目标")
  t.ok(not _is_dev(str(_ok_out)), "绝对路径的普通文件不是设备目标")

  # (b) 退出码：--out 不可写时，observe/tree/visible 都返回 2、有说明、无 traceback
  _blocked_file = Path(TD) / "blocked_out.txt"
  _blocked_file.write_text("x", encoding="utf-8")      # 上级是普通文件 → 写不进去
  _bad_out = str(_blocked_file / "sub" / "out.json")
  for _cmd in ([["observe"], str(_ok_out)],
               [["visible"], str(_ok_out)],
               [["tree", "--mode", "slim"], str(_ok_out)]):
      _args, _json_in = _cmd
      _proc = subprocess.run(
          [sys.executable, os.path.join(HERE, "main.py"), *_args,
           "--from-json", _json_in, "--out", _bad_out, "--no-color", "--quiet"],
          cwd=HERE, capture_output=True, timeout=30,
      )
      t.eq(_proc.returncode, 2, f"{_args[0]} 的 --out 写失败退出码为 2")
      t.ok(bool(_proc.stderr.strip()), f"{_args[0]} 的 --out 写失败在 stderr 给说明")
      t.ok(b"Traceback" not in _proc.stderr,
           f"{_args[0]} 的 --out 写失败无 traceback", repr(_proc.stderr))
  ```

  > `_is_device_target` 用 `getattr(..., 默认 lambda)` 读取：RED 阶段它还不存在，默认 lambda 让断言记失败而不是抛 AttributeError 中止整场（规则 5）。`json_io` / `io` / `contextlib` / `subprocess` / `sys` / `os` / `json` / `Path` / `TD` / `HERE` 均已在前文导入（`json_io` 见 `:2055`/`:2116`，`subprocess` 见第 12 段 `:2079-2083`）。`_ok_out` 的内容是合法 full JSON（含 `tree` 列表），所以三条 `--from-json` 命令能走到 `emit_json` 才失败——这正是我们要测的阶段。三条命令各自的既有失败退出码分别是 2（读文件错）；这里 `--from-json` 能读、`--out` 写不进，故归一到 2。

  **Step 2：** 跑自检。**期望退出码 1**，汇总块正常打印。失败项应为：原子性两条（当前 `os.replace` 从未被调用，写入会成功留下半成品文件 → `not _atomic_target.exists()` 失败；`_raised` 为 None → isinstance 失败）、`_is_device_target` 七条（函数不存在 → getattr 默认返回 False → 设备名断言全失败）、退出码三条 ×3 命令（当前是 traceback + 退出码 1）。字节数/LF 三条应已绿。**不得**改生产代码凑绿。

  **Step 3（GREEN）：**

  `tvuitree/interfaces/json_io.py` 全文改为（`load_full_json` 保持原样；`emit_json` 的 stderr 提示与 stdout 分支逐字保持）：

  ```python
  """Read and write the existing full-tree JSON format."""

  from __future__ import annotations

  import json
  import os
  import re
  import sys
  import tempfile
  from typing import Optional

  from .terminal import C, c

  # Windows 保留设备名：os.replace 打到这些名字上会失败或行为未定义，
  # 而 `--out NUL` 是本仓库既有的离线检查写法，必须继续可用。
  _WINDOWS_DEVICE_NAMES = {"nul", "con", "prn", "aux"}
  _WINDOWS_DEVICE_RE = re.compile(r"(com|lpt)[1-9]")

  def _is_device_target(out_path: str) -> bool:
      """目标是否是设备文件（NUL / CON / COM1 / os.devnull 等），这类目标只能直写。"""
      if out_path == os.devnull:
          return True
      stem = os.path.splitext(os.path.basename(out_path))[0].lower()
      return stem in _WINDOWS_DEVICE_NAMES or bool(_WINDOWS_DEVICE_RE.fullmatch(stem))


  def emit_json(obj: dict, out_path: Optional[str]) -> None:
      """写 JSON。文件目标走原子替换，失败时不留半成品也不残留临时文件。"""
      text = json.dumps(obj, ensure_ascii=False, indent=2)
      if not out_path:
          print(text)
          return
      payload = text + "\n"
      if _is_device_target(out_path):
          with open(out_path, "w", encoding="utf-8", newline="\n") as f:
              f.write(payload)
      else:
          # dirname 必须先 abspath：os.path.dirname("full.json") 是空串，
          # mkstemp(dir="") 的行为不可靠。
          directory = os.path.dirname(os.path.abspath(out_path))
          fd, temp_name = tempfile.mkstemp(prefix=".tvuitree-", suffix=".tmp", dir=directory)
          try:
              with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                  f.write(payload)
              os.replace(temp_name, out_path)
          except OSError:
              # 不清理就会在目标目录留下 .tmp：金样的「新文件」扫描会把它当成差异。
              try:
                  os.unlink(temp_name)
              except OSError:
                  pass
              raise
      byte_count = len(payload.encode("utf-8"))
      print(c(f"[out] 已写入 {out_path}（{byte_count} 字节）", C.GRY), file=sys.stderr)


  def emit_json_checked(obj: dict, out_path: Optional[str]) -> Optional[int]:
      """写 JSON；失败时打印中文说明并返回退出码 2，成功返回 None。

      退出码与文案属于 interfaces：AGENTS.md 规定文件错误用 2，且不得吐 traceback。
      """
      try:
          emit_json(obj, out_path)
      except OSError as error:
          print(c(f"写不了 {out_path}：{error}", C.RED), file=sys.stderr)
          return 2
      return None
  ```

  三个调用点改为先检查返回值再打印成功提示：

  `tvuitree/interfaces/observe.py`（`:11` 导入改为 `from .json_io import emit_json_checked, load_full_json`；`:40-42` 改为）：

  ```python
      failed = emit_json_checked(result, args.out)
      if failed is not None:
          return failed
      print(c("[observe] 已生成模型观察 JSON", C.GRY), file=sys.stderr)
      return 0
  ```

  `tvuitree/interfaces/tree.py`（`:15` 导入改为 `from .json_io import emit_json_checked, load_full_json`；`:118-120` 改为）：

  ```python
      failed = emit_json_checked(result, args.out)
      if failed is not None:
          return failed
      _summary(result, args.out)
      return 0
  ```

  `tvuitree/interfaces/visible.py`（`:11` 导入改为 `from .json_io import emit_json_checked, load_full_json`；`:38-41` 改为）：

  ```python
      failed = emit_json_checked(result, args.out)
      if failed is not None:
          return failed
      print(c(f"[visible] {len(result['page']['nodes'])} 个可见信息项", C.GRY),
            file=sys.stderr)
      return 0
  ```

  **不得**改 `shot.py`（它的文件错误已按 README:353 用退出码 1，是 shot 自己的约定）；**不得**改 `emit_json` 的 stderr 提示措辞或字节数算法；**不得**把 `emit_json` 搬出 `interfaces/json_io.py`（`selftest_tree.py:2116-2120` 断言它在那里）。

  **Acceptance criteria：**
  - `os.replace` 被注入失败时：`emit_json` 让 `OSError` 传播、目标文件不存在、目标目录无 `.tmp` 残留
  - 成功路径：文件内容为完整 JSON、以单个 LF 结尾、无 CRLF；stderr 提示的字节数等于文件实际字节数
  - `_is_device_target` 对 `os.devnull`、`NUL`、`CON`、`PRN`、`AUX`、`COM1`、`LPT1` 返回 True；对 `full.json` 与任意普通绝对路径返回 False
  - `observe`/`tree --mode slim`/`visible` 三条 `--from-json` 命令在 `--out` 不可写时：退出码 **2**、stderr 非空且含中文原因、stderr 不含 `Traceback`
  - `main.py observe --from-json _temp/e2e/full.json --out NUL` 退出码 0（设备名退回直写）
  - `selftest_tree.py:2056-2065` 与 `:2116-2120` 的既有断言继续通过
  - `json_io.py` 中不再存在对非设备目标的裸 `open(out_path, "w"` 直写

  **QA — happy path：**
  ```powershell
  $ev = '_temp/plan-evidence/code-review-remediation'
  New-Item -ItemType Directory -Force -Path $ev | Out-Null
  & $py main.py observe --from-json _temp/e2e/full.json --out NUL
  if ($LASTEXITCODE -ne 0) { throw 'NUL 直写失败' }
  & $py main.py tree --from-json _temp/e2e/full.json --mode slim --out "$ev/T3-slim.json"
  if ($LASTEXITCODE -ne 0) { throw 'slim 输出失败' }
  & $py -c "import json,os; p=r'$ev/T3-slim.json'; b=open(p,'rb').read(); print(len(b), b.endswith(b'\n'), b'\r\n' not in b); json.loads(b.decode('utf-8')); print('parse ok'); print('tmp litter:', [f for f in os.listdir(os.path.dirname(p)) if f.endswith('.tmp')])"
  ```
  期望：退出码全 0；LF 结尾、无 CRLF；可解析；`tmp litter: []`。证据写入 `$ev/T3-happy.txt`。

  **QA — failure path：**
  ```powershell
  $ev = '_temp/plan-evidence/code-review-remediation'
  New-Item -ItemType File -Force -Path "$ev/blocker.txt" | Out-Null
  & $py main.py observe --from-json _temp/e2e/full.json --out "$ev/blocker.txt/sub/out.json"
  "exit=$LASTEXITCODE"
  ```
  期望 `exit=2`、stderr 有中文原因、无 traceback。证据写入 `$ev/T3-fail.txt`。

  **Step 4：** 完整检查块 + 金样 check。**金样这里最关键**：`base/` 含 `observe.txt`/`slim.txt`/`visible.txt`/`keep_all.txt`/`keep_gone.txt`（都带 `[out] 已写入 ... 字节` 行）与全部 `.json`/`.png`。期望**零差异**——字节数算法与提示措辞未变，JSON 内容未变。若出现 `.tmp` 新文件差异，说明 Step 3 的 unlink 没生效，必须修而不是重建基线。

  **Step 5（提交）：**
  ```powershell
  git add tvuitree/interfaces/json_io.py tvuitree/interfaces/observe.py tvuitree/interfaces/tree.py tvuitree/interfaces/visible.py tests/selftest_tree.py
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
  git diff --cached --stat
  git diff --cached
  git commit -m "fix(interfaces): JSON 输出改为原子写并把写失败映射为退出码 2"
  ```

  Recommended task executor category: `unspecified-low` — 跨 4 个文件但每处改动都很小且已给出完整代码；设备名特判与临时文件清理是仅有的两个需要留神的点。

- [ ] 4. T4 `infrastructure/adb.py`：`props()` 校验行数、串位时抛 `AdbError`，并建立 ADB 假件

  **关闭：** GAP-1 / IS-1

  **References：**
  - `tvuitree/infrastructure/adb.py:138-144` —— `props()` 全文：8 个 key 用 `;` 拼一条 shell，`:143` 过滤空行，`:144` `dict(zip(keys, vals + [""] * len(keys)))`。
  - `tvuitree/infrastructure/adb.py:103-109` —— `shell()`（`:105` 会在 stderr 非空时把 stderr 追加到返回值，**污染行数**）与 `shell_raw()`（返回 `(rc, out, err)` 三元组，不追加）。**修复要用 `shell_raw` 只取 stdout。**
  - `tvuitree/infrastructure/adb.py:67-84` —— `_popen(args, timeout, binary, heal)`：命令拼为 `[self.adb] + (["-s", serial] if serial else []) + args`；超时抛 `AdbError`；`FileNotFoundError` 抛 `AdbError`；`heal` 为真且命中 `_OFFLINE_RE` 时自动重连并重试一次。**假件必须重写 `_popen`。**
  - `tvuitree/infrastructure/adb.py:30-31` —— `class AdbError(RuntimeError)`。
  - `tvuitree/infrastructure/snapshot.py:18-22` —— 唯一调用方：`dev = {}` 然后 `try: dev = adb.props() except AdbError: pass`。**只捕 `AdbError`**，故 `props()` 抛 `AdbError` 会干净降级为 `dev={}`（与设备不可达时同一形状），采集继续。
  - `tvuitree/domain/observation.py:203` —— `"device": full_json.get("device") or {}` 把 `dev` 拷进观察输出。故 `device` 从「静默错值」变成「诚实的 `{}`」，**schema 不变**。
  - `tvuitree/domain/tree/output.py:153` —— `"device": dev` 写进 full JSON。
  - `tvuitree/interfaces/mcp.py:286-290` —— `props()` 在 MCP `capture_tree` 计时阶段内执行，故**不得**改成 8 次独立 subprocess（会把 1 次派生变成 8 次，Windows 上每次几百毫秒）。
  - `tests/selftest_tree.py:1219-1231` —— 第 8 段的 `_fixture_snapshot` 整体替换 `snapshot.snapshot` 并硬编码 `"dev": {"model": "SELFTEST", ...}`（`:1224`），**从不经过 `Adb.props`**。故本任务与既有断言零交互，必须自建假件。
  - `tests/selftest_tree.py:1657-1683` —— `_BenchDevice` 假件范式（构造参数 `serial`/`outcomes`/`connected`/`state`/`connect_error`；实现 `connect`/`shell_raw`/`exec_out`）。**新假件参照此风格，但必须重写 `_popen` 且按命令名分派。**
  - `tests/selftest_tree.py:1207-1217, 1546-1557` —— 第 8 段的 save/restore 范式（`try` 前存原值、`finally` 全部还原）。**新段必须自带 save/restore，不得改第 8 段的全局。**
  - `README.md:72` —— 只提到 `device` 字段存在，**未**记录任何单个 prop 键名 → 本任务无需改 README。

  **Interfaces：**
  - Consumes: 无。
  - Produces:
    - `Adb.props() -> dict`：改用 `shell_raw` 只取 stdout；**不再过滤空行**；`rc != 0` 或行数与键数不符时抛 **`AdbError`**；成功时返回 8 个键的完整 dict（未设置的 prop 值为空串，位置正确）。
    - 新增测试假件 `_FakeAdbPopen` 与 `_fake_adb()`（第 16 段内定义，按命令名分派 `_popen`），供 T4 与 **T5** 共用。

  **Step 1（RED）：** 新增第 16 段，先建假件再写断言。假件重写 `_popen` 并**按命令名分派**（这是规则 3，GAP-3 的 GREEN 会在 `_reconnect` 内部新增 `devices` 调用，位置队列会失同步中止整场）。

  ```python
  # ================================================================== 16. ADB 属性与连接语义

  t.group("16. props() 拒绝串位的设备属性")

  class _FakeAdbPopen:
      """按命令名分派的 Adb 假件：重写 _popen，不用位置队列。

      为什么必须按命令名分派：_reconnect 的修复会在其内部新增一次 devices 调用，
      位置响应队列会因此失同步并抛 IndexError，让顺序自检整场中止。
      """

      def __init__(self, responses: dict, offline_once: bool = False) -> None:
          self._responses = dict(responses)
          self._offline_once = offline_once
          self.calls: list = []

      def _popen(self, args: list, timeout: float = 30.0, binary: bool = False,
                 heal: bool = True):
          name = args[0] if args else ""
          self.calls.append(list(args))
          if self._offline_once:
              self._offline_once = False
              return 1, b"", b"error: device offline\n"
          item = self._responses.get(name, (0, b"", b""))
          if isinstance(item, BaseException):
              raise item
          return item

  def _fake_adb(responses: dict, serial: str = "1.2.3.4:5555",
                offline_once: bool = False, auto_connect: bool = True) -> adb.Adb:
      device = adb.Adb("adb", serial, auto_connect=auto_connect)
      device._popen = _FakeAdbPopen(responses, offline_once)._popen
      return device

  _PROP_KEYS = ["ro.product.manufacturer", "ro.product.model", "ro.product.device",
                "ro.build.version.release", "ro.build.version.sdk",
                "ro.build.version.incremental", "ro.product.cpu.abilist",
                "ro.build.type"]

  # 正常：8 个键 8 行，逐一对应
  _good = "\n".join(["Google", "Chromecast", "glen", "14", "34", "ABC123",
                     "arm64-v8a", "user"]) + "\n"
  _dev_good = _fake_adb({"shell": (0, _good.encode("utf-8"), b"")}).props()
  t.eq(_dev_good.get("ro.product.manufacturer"), "Google", "manufacturer 对位正确")
  t.eq(_dev_good.get("ro.product.model"), "Chromecast", "model 对位正确")
  t.eq(_dev_good.get("ro.build.type"), "user", "最后一个键对位正确")
  t.eq(len(_dev_good), len(_PROP_KEYS), "返回全部 8 个键")

  # 部分 prop 未设置：getprop 仍各输出一行（空行），对位必须保持
  _with_blank = "\n".join(["Google", "", "glen", "14", "34", "", "arm64-v8a", "user"]) + "\n"
  _dev_blank = _fake_adb({"shell": (0, _with_blank.encode("utf-8"), b"")}).props()
  t.eq(_dev_blank.get("ro.product.model"), "", "未设置的 prop 得到空串，且不挤掉后面的值")
  t.eq(_dev_blank.get("ro.product.device"), "glen", "空值之后的键仍然对位")
  t.eq(_dev_blank.get("ro.build.version.incremental"), "", "第二个空值也对位")
  t.eq(_dev_blank.get("ro.product.cpu.abilist"), "arm64-v8a", "abilist 没被空值挤位")

  # 串位：行数与键数不符时必须抛 AdbError，绝不返回错位的值
  _short = "\n".join(["Google", "Chromecast", "glen", "14", "34", "arm64-v8a"]) + "\n"
  _raised_short = None
  try:
      _fake_adb({"shell": (0, _short.encode("utf-8"), b"")}).props()
  except Exception as error:            # 宽捕获后 isinstance：避免中止整场
      _raised_short = error
  t.ok(isinstance(_raised_short, adb.AdbError),
       "行数少于键数时抛 AdbError（不是静默串位）", f"实际 {type(_raised_short).__name__}")

  _long = "\n".join(["Google", "Chromecast", "glen", "14", "34", "ABC", "arm64", "user",
                     "EXTRA"]) + "\n"
  _raised_long = None
  try:
      _fake_adb({"shell": (0, _long.encode("utf-8"), b"")}).props()
  except Exception as error:
      _raised_long = error
  t.ok(isinstance(_raised_long, adb.AdbError),
       "行数多于键数时也抛 AdbError（多余行不得静默丢弃）",
       f"实际 {type(_raised_long).__name__}")

  # rc != 0 时抛 AdbError
  _raised_rc = None
  try:
      _fake_adb({"shell": (1, b"", b"error: device offline\n")}).props()
  except Exception as error:
      _raised_rc = error
  t.ok(isinstance(_raised_rc, adb.AdbError),
       "getprop 返回非 0 时抛 AdbError", f"实际 {type(_raised_rc).__name__}")

  # 降级契约：snapshot 只捕 AdbError，所以 props 抛 AdbError 时 device 变成诚实的 {}
  _snap_dev = {}
  try:
      _snap_dev = _fake_adb({"shell": (0, _short.encode("utf-8"), b"")}).props()
  except adb.AdbError:
      _snap_dev = {}
  t.eq(_snap_dev, {}, "串位时降级为空 dict（与设备不可达同一形状），不给出错值")
  ```

  > `adb` 模块已在 `:61` 导入（`from tvuitree.infrastructure import adb, image`）。`_FakeAdbPopen` / `_fake_adb` 定义在第 16 段，**T5 直接复用**，不要重复定义。

  **Step 2：** 跑自检。**期望退出码 1**，汇总块正常打印。失败项应为：两个空值对位断言（当前空行被 `:143` 过滤掉 → 后续值全部前移）、三个 `isinstance(..., adb.AdbError)` 断言（当前 `zip` + 补齐永不抛，返回串位 dict）。正常 8 行用例应已绿。**不得**改生产代码凑绿。

  **Step 3（GREEN）：** 替换 `adb.py:138-144`：

  ```python
      def props(self) -> dict:
          """读取设备属性；行数与键数不符时明确报错，绝不返回串位的值。

          `getprop <key>` 对未设置的键也输出恰好一行（空行），所以不能过滤空行：
          一过滤，后面的值就整体前移，model 会静默变成 device 的值 —— 而 device
          字段是模型和人工排查的共同证据，串位比缺失更伤信任。
          用 shell_raw 只取 stdout：shell() 会把非空 stderr 追加进来，污染行数。
          """
          keys = ["ro.product.manufacturer", "ro.product.model", "ro.product.device",
                  "ro.build.version.release", "ro.build.version.sdk",
                  "ro.build.version.incremental", "ro.product.cpu.abilist", "ro.build.type"]
          rc, out, err = self.shell_raw(";".join(f"getprop {k}" for k in keys), timeout=30)
          if rc != 0:
              raise AdbError(f"getprop 失败（exit={rc}）：{(err or out).strip()}")
          vals = [ln.strip() for ln in out.splitlines()]
          if len(vals) != len(keys):
              raise AdbError(
                  f"getprop 返回 {len(vals)} 行，与请求的 {len(keys)} 个键不符；"
                  "拒绝按行序配对，避免设备属性串位")
          return dict(zip(keys, vals))
  ```

  **保留单条 `;` 拼接命令**（1 次 subprocess），不得改成逐键查询（8 次派生，在 MCP `capture_tree` 计时阶段内会显著拖慢真机采集）。**必须抛 `AdbError`**，不得抛 `ValueError`/`RuntimeError`——`snapshot.py:21` 只捕 `AdbError`，换类型会让整轮采集失败（CLI rc 3 / MCP `error`），破坏既有降级设计。

  **Acceptance criteria：**
  - `props()` 使用 `shell_raw` 而非 `shell`
  - `props()` 中不再有空行过滤（无 `if ln.strip()` 条件）
  - 8 行正常输入 → 8 键全部对位
  - 含空行的 8 行输入 → 空值落在正确的键上，后续键不位移
  - 6 行输入 → 抛 `AdbError`；9 行输入 → 抛 `AdbError`；`rc != 0` → 抛 `AdbError`
  - `props()` 内 `shell_raw` 调用次数仍为 **1**（不得变成 8）
  - `snapshot.py` 的 `except AdbError: pass` 降级路径未被修改，且串位时 `device` 最终为 `{}`
  - full JSON 与观察输出的 `device` 字段**键集合与类型不变**（仍是 dict）

  **QA — happy path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.infrastructure import adb; d=adb.Adb('adb','1.2.3.4:5555'); d._popen=lambda args,timeout=30.0,binary=False,heal=True: (0, b'Google\nChromecast\nglen\n14\n34\nABC\narm64\nuser\n', b''); print(d.props())"
  ```
  期望打印 8 个键、`ro.product.model` 为 `Chromecast`、`ro.build.type` 为 `user`。证据写入 `_temp/plan-evidence/code-review-remediation/T4-happy.txt`。

  **QA — failure path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.infrastructure import adb; d=adb.Adb('adb','1.2.3.4:5555'); d._popen=lambda args,timeout=30.0,binary=False,heal=True: (0, b'Google\nChromecast\nglen\n14\n34\narm64\n', b'');
  try:
      print('BAD:', d.props())
  except adb.AdbError as e:
      print('OK AdbError:', e)"
  ```
  期望输出以 `OK AdbError:` 开头、**不**出现 `BAD:`（即绝不返回串位 dict）。再跑一次含空行的 8 行输入，期望 `ro.product.model` 为 `''` 且 `ro.product.device` 为 `glen`（证明空值不挤位）。证据写入 `_temp/plan-evidence/code-review-remediation/T4-fail.txt`。

  **Step 4：** 完整检查块 + 金样 check。金样的 `_rebuild_full` 复用**已保存**的 `meta["device"]`、从不重算 `props()`，故期望零差异。

  **Step 5（提交）：**
  ```powershell
  git add tvuitree/infrastructure/adb.py tests/selftest_tree.py
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
  git diff --cached --stat
  git diff --cached
  git commit -m "fix(adb): getprop 输出错位时明确报错，不再平移设备属性"
  ```

  Recommended task executor category: `unspecified-low` — 单文件小改，但需要正确构造按命令名分派的假件并遵守「必须抛 AdbError」这条不明显的约束。

- [ ] 5. T5 `infrastructure/adb.py`：`_reconnect` 改用 `adb devices` 状态判据，`connect()` 多设备时不猜

  **关闭：** GAP-3 / IS-3，GAP-8 / IS-8

  **依赖：T4**（复用第 16 段的 `_FakeAdbPopen` / `_fake_adb`；T4 必须先完成）

  **References：**
  - `tvuitree/infrastructure/adb.py:86-101` —— `_reconnect()` 全文：`:87` 守卫 `self._healing or not (serial and ":" in serial and auto_connect)`；`:92` `self._popen(["connect", self.serial], timeout=25, heal=False)`；**`:96` `ok = "connected" in msg.lower() and "cannot" not in msg.lower()`（要替换的措辞猜测）**；`:98` `logging.warning(...)`；`:100-101` `finally: self._healing = False`。
  - `tvuitree/infrastructure/adb.py:119-135` —— `connect()` 全文：`:120-127` 可选 `adb connect`；`:128` `self._popen(["devices"], timeout=20)`；`:129` `targets = [...]`；`:130` `self._connected = bool(self.serial) and self.serial in targets`；**`:131-134` 空 serial 时 `self._connected = bool(targets)` 且 `self.serial = targets[0]`（要改的静默抢占）**。
  - `tvuitree/infrastructure/adb.py:67-84` —— `_popen`：`:78` 命中 `_OFFLINE_RE` 且 `_reconnect()` 成功时重试原命令一次（`heal=False` 防递归）。
  - `tvuitree/infrastructure/adb.py:25-27` —— `_OFFLINE_RE` 匹配 `device offline` / `device not found` / `no devices/emulators` / `connection reset` / `closed by remote` / `adb: device`。
  - `tvuitree/interfaces/connection.py:28-42` —— `connect_for_cli`：`:34` `device = connect_device(options, quiet=args.quiet)` **无 try/except**，`:35-41` 在 `device is None` 时打印 4 条中文排查提示并返回 `None`（调用方转成退出码 2）。**这就是 `connect()` 不得抛异常的原因**：抛出会变成 traceback + 退出码 1，违反 AGENTS.md:17。
  - `tvuitree/application/connection.py:73-77` —— `connect_device` 返回 `device if device.connect(quiet=quiet) else None`，即 `connect()` 返回 False 会干净地变成 `None` → 退出码 2 + 友好提示。
  - `scripts/bench_screencap.py:170-175` —— `device_state()`：用 `shell_raw("echo ok")` 判断设备是否真的可用（`rc == 0 and out.strip() == "ok"`），是仓库里既有的「状态而非措辞」判据先例。
  - `tests/selftest_tree.py` 第 16 段（T4 新建）—— `_FakeAdbPopen` / `_fake_adb`，本任务直接复用，不要重复定义。
  - `README.md:120` —— `no_connect` 文档：「为 `true` 时不执行 `adb connect`，但仍会检查目标是否已经出现在 `adb devices` 中」→ 成员检查是既有文档行为，本任务不改 `connect()` 对**已指定 serial** 的判据。

  **Interfaces：**
  - Consumes: T4 的 `_FakeAdbPopen` / `_fake_adb`。
  - Produces:
    - `Adb._reconnect() -> bool`：不再解析 `adb connect` 的回显措辞；改为跑 `adb devices` 并要求本 serial 的**状态列为 `device`** 才返回 True。新增私有辅助 `_serial_is_device() -> bool`。
    - `Adb.connect() -> bool`：指定了 serial 时行为**完全不变**；未指定 serial 时——恰好一台设备则自动选中（保留便利），**多于一台则返回 False 且绝不改写 `self.serial`**，不抛异常，非 quiet 时 `logging.warning` 列出检测到的设备。

  **Step 1（RED）：** 在第 16 段之后新增第 17 段（**不要**往第 16 段里塞，保持每任务一段）。

  ```python
  # ================================================================== 17. 连接语义

  t.group("17. _reconnect 用 devices 状态判据、connect 不在多设备时猜")

  _SERIAL = "1.2.3.4:5555"
  _DEVICES_OK = ("List of devices attached\n"
                 f"{_SERIAL}\tdevice\n").encode("utf-8")
  _DEVICES_OFFLINE = ("List of devices attached\n"
                      f"{_SERIAL}\toffline\n").encode("utf-8")
  _DEVICES_EMPTY = b"List of devices attached\n"
  _DEVICES_TWO = ("List of devices attached\n"
                  "10.0.0.8:5555\tdevice\n"
                  "emulator-5554\tdevice\n").encode("utf-8")
  _DEVICES_ONE = ("List of devices attached\n"
                  "10.0.0.9:5555\tdevice\n").encode("utf-8")

  # --- GAP-3：_reconnect 不得再靠回显措辞判断 ---
  # 回显说 "connected" 但设备其实 offline → 必须判为未重连
  _lying = _fake_adb({"connect": (0, f"connected to {_SERIAL}\n".encode("utf-8"), b""),
                      "devices": (0, _DEVICES_OFFLINE, b"")}, serial=_SERIAL)
  t.eq(_lying._reconnect(), False,
       "adb connect 回显说 connected 但 devices 状态是 offline → 不算重连成功")

  # 回显措辞陌生但设备真的回到 device 状态 → 必须判为已重连
  _wording = _fake_adb({"connect": (0, b"some unfamiliar adb wording\n", b""),
                        "devices": (0, _DEVICES_OK, b"")}, serial=_SERIAL)
  t.eq(_wording._reconnect(), True,
       "回显措辞不认识但 devices 状态为 device → 算重连成功（判据是状态不是措辞）")

  # 回显说 cannot connect → 仍然 False
  _cannot = _fake_adb({"connect": (0, f"cannot connect to {_SERIAL}\n".encode("utf-8"), b""),
                       "devices": (0, _DEVICES_EMPTY, b"")}, serial=_SERIAL)
  t.eq(_cannot._reconnect(), False, "cannot connect 且不在 devices 里 → False")

  # devices 也掉线（抛 AdbError）时不得把异常漏出去
  _raise_dev = _fake_adb({"connect": (0, b"connected\n", b""),
                          "devices": adb.AdbError("adb 超时(20s)：devices")}, serial=_SERIAL)
  _raised_dev = None
  try:
      _result_dev = _raise_dev._reconnect()
  except Exception as error:
      _raised_dev, _result_dev = error, None
  t.ok(_raised_dev is None and _result_dev is False,
       "devices 查询失败时 _reconnect 返回 False，不漏异常",
       f"raised={type(_raised_dev).__name__} result={_result_dev}")

  # 守卫：未指定 serial 或 no_connect 时不尝试重连
  t.eq(_fake_adb({}, serial="usbserial")._reconnect(), False,
       "非 ip:port 的 serial 不触发自动重连")
  _no_auto = adb.Adb("adb", _SERIAL, auto_connect=False)
  _no_auto._popen = _FakeAdbPopen({"connect": (0, b"connected\n", b""),
                                   "devices": (0, _DEVICES_OK, b"")})._popen
  t.eq(_no_auto._reconnect(), False, "auto_connect=False 时不触发自动重连")

  # --- GAP-8：connect() 空 serial 时不得静默抢占某台设备 ---
  _multi = adb.Adb("adb", None, auto_connect=False)
  _multi._popen = _FakeAdbPopen({"devices": (0, _DEVICES_TWO, b"")})._popen
  t.eq(_multi.connect(quiet=True), False, "未指定 serial 且有多台设备 → connect 返回 False")
  t.eq(_multi.serial, None, "多设备时绝不改写 self.serial（不猜目标）")

  _single = adb.Adb("adb", None, auto_connect=False)
  _single._popen = _FakeAdbPopen({"devices": (0, _DEVICES_ONE, b"")})._popen
  t.eq(_single.connect(quiet=True), True, "未指定 serial 但只有一台设备 → 自动选中")
  t.eq(_single.serial, "10.0.0.9:5555", "单设备时 serial 被填成那台设备")

  _none_dev = adb.Adb("adb", None, auto_connect=False)
  _none_dev._popen = _FakeAdbPopen({"devices": (0, _DEVICES_EMPTY, b"")})._popen
  t.eq(_none_dev.connect(quiet=True), False, "没有任何设备 → False")
  t.eq(_none_dev.serial, None, "没有任何设备时 serial 保持 None")

  # 已指定 serial 的既有行为不得改变
  _named = adb.Adb("adb", _SERIAL, auto_connect=False)
  _named._popen = _FakeAdbPopen({"devices": (0, _DEVICES_OK, b"")})._popen
  t.eq(_named.connect(quiet=True), True, "指定 serial 且在 devices 里 → True（行为不变）")
  t.eq(_named.serial, _SERIAL, "指定 serial 时不改写 serial")
  _named_absent = adb.Adb("adb", _SERIAL, auto_connect=False)
  _named_absent._popen = _FakeAdbPopen({"devices": (0, _DEVICES_TWO, b"")})._popen
  t.eq(_named_absent.connect(quiet=True), False,
       "指定 serial 但不在 devices 里 → False（行为不变，不受多设备影响）")
  ```

  > `_FakeAdbPopen` 的 `responses` 里放 `BaseException` 实例时会就地抛出（见 T4 假件实现），用它模拟 `devices` 查询超时。所有断言都用返回值比较或宽捕获 + `isinstance`，不用 `t.eq(type(...))`（规则 1）。

  **Step 2：** 跑自检。**期望退出码 1**，汇总块正常打印。失败项应为：`_lying._reconnect()` 当前返回 `True`（措辞里有 "connected" 且无 "cannot"）、`_wording._reconnect()` 当前返回 `False`、`_multi.connect()` 当前返回 `True` 且 `_multi.serial` 被改写成 `10.0.0.8:5555`。指定 serial 的三条与单设备/无设备两条应已绿。

  **Step 3（GREEN）：**

  替换 `adb.py:86-101` 的 `_reconnect`，并新增 `_serial_is_device`：

  ```python
      def _reconnect(self) -> bool:
          """掉线后重连一次；判据是 `adb devices` 的状态列，不是 connect 的回显措辞。

          回显措辞随 adb 版本与 locale 变化：`already connected` / `connected to` /
          `cannot connect` / `failed to connect` 都出现过。靠子串猜会把「回显里有
          connected 但设备其实 offline」判成重连成功，让重试继续打向已死设备，
          把错误推迟成更难懂的下游异常。这里改用与措辞无关的事实：设备在
          `adb devices` 里且状态列是 device。
          """
          if self._healing or not (self.serial and ":" in self.serial and self.auto_connect):
              return False
          self._healing = True
          try:
              try:
                  self._popen(["connect", self.serial], timeout=25, heal=False)
                  return self._serial_is_device()
              except AdbError:
                  return False
          finally:
              self._healing = False

      def _serial_is_device(self) -> bool:
          """本 serial 是否出现在 `adb devices` 且状态列为 device。"""
          try:
              _rc, out, _err = self._popen(["devices"], timeout=20, heal=False)
          except AdbError:
              return False
          for line in out.splitlines()[1:]:
              if not line.strip() or "\t" not in line:
                  continue
              parts = line.split("\t")
              if parts[0].strip() == self.serial:
                  return parts[1].strip() == "device"
          return False
  ```

  替换 `adb.py:128-135`（`connect()` 的末尾）：

  ```python
          rc, out, _ = self._popen(["devices"], timeout=20)
          targets = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip() and "\t" in ln]
          if self.serial:
              # 已指定目标：成员判据不变（README 记录的 no_connect 行为依赖它）
              self._connected = self.serial in targets
              return self._connected
          if len(targets) == 1:
              # 只有一台设备时自动选中，保留给外部库使用者的便利
              self.serial = targets[0]
              self._connected = True
              return True
          if targets and not quiet:
              # 多台设备时绝不猜：静默选中一台会让所有读写打到调用方从未指定的设备
              logging.warning("[adb] 未指定 serial 且检测到多台设备，拒绝自动选择：%s",
                              ", ".join(targets))
          self._connected = False
          return False
  ```

  **关键约束：`connect()` 不得抛异常。** `interfaces/connection.py:34` 的调用处没有 try/except，抛出会变成 traceback + 退出码 1，违反 AGENTS.md:17 的「连接错误 → 2」；返回 False 才会经 `application/connection.py:77` 变成 `None`，进而由 `connect_for_cli` 打印 4 条中文排查提示并让调用方返回 2。

  **明确的非目标（防范围蔓延）：** 不改 `connect()` 对已指定 serial 的**成员**判据（`:130` 原语义保留），即不把它也升级成状态判据。只有 `_reconnect` 升级为状态判据——因为 IS-3 只约束重连路径，而改 `connect()` 会影响所有调用方的既有连接语义（含 `no_connect` 的文档行为）与 `scripts/bench_screencap.py:219` 的用法，属范围外。

  **Acceptance criteria：**
  - `adb.py` 中不再存在 `"connected" in msg.lower()` 或 `"cannot" not in msg.lower()` 这类回显措辞判定
  - 新增 `_serial_is_device()`，`_reconnect` 用它作判据
  - `connect` 回显 `connected to <serial>` 但 `devices` 状态为 `offline` → `_reconnect()` 返回 False
  - `connect` 回显陌生措辞但 `devices` 状态为 `device` → `_reconnect()` 返回 True
  - `devices` 查询抛 `AdbError` → `_reconnect()` 返回 False 且异常不外漏
  - 非 `ip:port` serial 或 `auto_connect=False` → `_reconnect()` 返回 False（守卫不变）
  - 空 serial + 2 台设备 → `connect()` 返回 False 且 `self.serial` 仍为 `None`
  - 空 serial + 1 台设备 → `connect()` 返回 True 且 `self.serial` 被填成该设备
  - 空 serial + 0 台设备 → `connect()` 返回 False 且 `self.serial` 仍为 `None`
  - 指定 serial 时 `connect()` 的成员判据行为与修改前完全一致
  - `connect()` 与 `_reconnect()` 在任何分支都**不抛异常**（`AdbError` 被内部消化为 False）
  - `_popen` 的 `heal=False` 递归防护未被破坏（`_reconnect` 内部的 `connect`/`devices` 调用都带 `heal=False`）

  **QA — happy path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.infrastructure import adb; d=adb.Adb('adb','1.2.3.4:5555',auto_connect=True); d._popen=lambda args,timeout=30.0,binary=False,heal=True: (0, (b'connected\n' if args[0]=='connect' else b'List of devices attached\n1.2.3.4:5555\tdevice\n'), b''); print('reconnect ->', d._reconnect())"
  ```
  期望 `reconnect -> True`。证据写入 `_temp/plan-evidence/code-review-remediation/T5-happy.txt`。

  **QA — failure path：** 同上但 `devices` 返回 `1.2.3.4:5555\toffline`，期望 `reconnect -> False`（回显仍说 connected，证明判据已从措辞切换到状态）。再跑空 serial + 两台设备，期望 `connect -> False` 且 `serial -> None`。证据写入 `_temp/plan-evidence/code-review-remediation/T5-fail.txt`。

  **Step 4：** 完整检查块 + 金样 check（金样不触网、不连设备，期望零差异）。

  **Step 5（提交）：**
  ```powershell
  git add tvuitree/infrastructure/adb.py tests/selftest_tree.py
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
  git diff --cached --stat
  git diff --cached
  git commit -m "fix(adb): 重连按设备状态判定且不在多设备时猜目标"
  ```

  Recommended task executor category: `deep-low` — 两个方法的状态机交互（`_healing` 递归防护、`heal=False` 重试路径、`connect_for_cli` 无 try/except 的退出码链）需要连贯推理，但所有判据已由证据定死，无需做取舍决策。

- [ ] 6. T6 依赖与探测路径卫生：删 `uiautodev`，删两个个人 adb 路径

  **关闭：** GAP-6 / IS-6，GAP-7 / IS-7

  **References：**
  - `requirements.txt:1-5` —— 全文 5 行：`uiautomator2`、`Pillow`、`pyflakes`、`uiautodev`、`mcp>=1.28,<2`。**只删第 4 行 `uiautodev`，不做版本固定、不拆 dev/prod。**
  - `tvuitree/infrastructure/adb.py:14-22` —— `ADB_CANDIDATES` 列表全文与其中文注释「Windows 上常见的 adb 位置（按顺序探测）」。
  - `tvuitree/infrastructure/adb.py:35-53` —— `resolve_adb`：显式指定 → `shutil.which("adb")` → `ADB_CANDIDATES` 逐个 `os.path.expandvars` + `os.path.isfile` → `ANDROID_HOME` / `ANDROID_SDK_ROOT` 下的 `platform-tools/adb(.exe)` → 兜底返回 `"adb"`。
  - `tests/selftest_tree.py:325` —— 既有断言 `t.eq(adb.resolve_adb("X:/adb.exe"), "X:/adb.exe", "显式指定的 adb 路径优先（不查文件系统）")`，**必须继续通过**。
  - `README.md` 快速开始段的 config 示例（含 `"adb": "D:\\platform-tools\\adb.exe"`）与 `config.json:4`（当前值 `D:\platform-tools\adb.exe`）——**本任务都不改**，那属 GAP-9 的范围（已推迟）。
  - 全库 grep 结论：`uiautodev` 仅出现在 `requirements.txt:4` 与 `docs/superpowers/plans/2026-10-02-comment-naming-structure.md:39`（旧计划把它列为 Out of scope「需用户另开任务」——**本任务就是那个另开的任务**）。所有 `.py` / `.ps1` 零引用。

  **Interfaces：**
  - Consumes: 无。
  - Produces: `requirements.txt` 减少一行；`ADB_CANDIDATES` 从 6 项减到 4 项（删 `D:\platform-tools\adb.exe` 与 `D:\SoftwareInstalled\...` 两条；**保留** `C:\platform-tools\adb.exe`——它是通用安装位置，不是个人机器痕迹）。`resolve_adb` 的函数体与签名不变。

  **Step 1（RED）：** 新增第 18 段。这是纯删除任务，断言用源文本/文件内容检查。

  ```python
  # ================================================================== 18. 依赖与探测路径卫生

  t.group("18. requirements 与 adb 探测列表不含个人痕迹")

  _req_path = os.path.join(HERE, "requirements.txt")
  _req_text = open(_req_path, "r", encoding="utf-8").read()
  t.ok("uiautodev" not in _req_text,
       "requirements.txt 不再引用零 import 的 uiautodev（死依赖）")
  for _needed in ("uiautomator2", "Pillow", "pyflakes", "mcp"):
      t.ok(_needed in _req_text, f"requirements.txt 保留实际使用的依赖 {_needed}")

  _adb_src = open(os.path.join(HERE, "tvuitree", "infrastructure", "adb.py"),
                  "r", encoding="utf-8").read()
  t.ok("D:\\platform-tools" not in _adb_src,
       "adb 探测列表不再含个人的 D:\\platform-tools 路径")
  t.ok("SoftwareInstalled" not in _adb_src,
       "adb 探测列表不再含个人的 SoftwareInstalled 安装路径")
  t.ok("C:\\platform-tools" in _adb_src,
       "保留通用的 C:\\platform-tools 探测（它不是个人机器痕迹）")
  t.ok("LOCALAPPDATA" in _adb_src and "ANDROID_HOME" in _adb_src,
       "保留环境变量与标准 SDK 探测")
  ```

  > `os` / `HERE` 已在前文定义。

  **Step 2：** 跑自检。**期望退出码 1**，失败项是 `uiautodev` 两条（`not in` 失败）与两条个人路径（`not in` 失败），汇总块正常打印。

  **Step 3（GREEN）：**

  `requirements.txt` 删除 `uiautodev` 行，保留其余 4 行及顺序：

  ```
  uiautomator2
  Pillow
  pyflakes
  mcp>=1.28,<2
  ```

  `tvuitree/infrastructure/adb.py:15-22` 的 `ADB_CANDIDATES` 改为：

  ```python
  # Windows 上常见的 adb 位置（按顺序探测）
  ADB_CANDIDATES = [
      r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe",
      r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe",
      r"C:\platform-tools\adb.exe",
      r"C:\Android\Sdk\platform-tools\adb.exe",
  ]
  ```

  **保留** `C:\platform-tools\adb.exe`（通用、无个人痕迹）；**只删** `D:\platform-tools\adb.exe` 与 `D:\SoftwareInstalled\Android\android_sdk\platform-tools\adb.exe`。`resolve_adb` 函数体不动。README 与 config.json 不动（GAP-9 范围）。

  **Acceptance criteria：**
  - `requirements.txt` 不含 `uiautodev`，仍含 `uiautomator2` / `Pillow` / `pyflakes` / `mcp`
  - `adb.py` 不含 `D:\platform-tools` 或 `SoftwareInstalled`
  - `adb.py` 仍含 `C:\platform-tools`、`LOCALAPPDATA`、`ANDROID_HOME`
  - `resolve_adb("X:/adb.exe")` 仍返回 `"X:/adb.exe"`（既有断言 `:325` 继续通过）
  - `README.md` 与 `config.json` 逐字节未变
  - 全量自检通过（断言数 > T5 结束时）

  **QA — happy path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.infrastructure import adb; print(adb.resolve_adb('X:/adb.exe')); print([c for c in adb.ADB_CANDIDATES])"
  ```
  期望第一行 `X:/adb.exe`，第二行是 4 项候选列表且不含 `D:` 开头项。证据写入 `_temp/plan-evidence/code-review-remediation/T6-happy.txt`。

  **QA — failure path：**
  ```powershell
  & $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.infrastructure import adb; bad=[c for c in adb.ADB_CANDIDATES if 'D:' in c or 'SoftwareInstalled' in c]; print('personal paths left:', bad)"
  ```
  期望 `personal paths left: []`。证据写入 `_temp/plan-evidence/code-review-remediation/T6-fail.txt`。

  **Step 4：** 完整检查块 + 金样 check（期望零差异；金样不读 requirements 或 adb 探测路径）。

  **Step 5（提交）：**
  ```powershell
  git add requirements.txt tvuitree/infrastructure/adb.py tests/selftest_tree.py
  git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'staged diff check failed' }
  git diff --cached --stat
  git diff --cached
  git commit -m "chore(repo): 移除未引用依赖与机器相关的 ADB 探测路径"
  ```
  提交信息里补一行说明探测行为变化：删掉两条 `D:` 候选后，依赖 `D:\platform-tools` 且 config 无 `adb` 键的新装机器会回退到 PATH 探测（可用 `--adb` 或 config 的 `adb` 显式指定）。

  Recommended task executor category: `quick` — 纯删除 + 源文本断言，零逻辑风险。

- [ ] 7. T7 文档核对：确认没有用户可见接口变化，必要时补一句 README

  **关闭：** IS-10（计划交付）；并履行 AGENTS.md:41「Update README for interface changes」

  **References：**
  - `AGENTS.md:41` —— 「Keep JSON fields, CLI exit behavior, diagnostics, MCP schemas, and screenshot coordinate semantics stable unless the change is intentional and documented. Update README for interface changes.」
  - `README.md:125` —— `set_default_device` 的原子写表述：「写入是原子的，失败时原文件保持不变」——T3 的 `emit_json` 原子写若要在 README 里说明，**只模仿这一句的措辞风格加一句**，且不得触发 `selftest_tree.py:1183-1195` 的 README 断言变化。
  - `README.md:353` —— shot 的文件错误退出码 1 约定，本计划不改。
  - `tests/selftest_tree.py:1183-1195` —— README 的机器检查断言全集（剪枝开关名、层目录名、画框约定短语）。**任何 README 编辑都必须让这些继续通过。**
  - 本计划 Scope 的「Must NOT have」清单与「Out of scope」清单——T7 只做核对，不得扩大范围。

  **Interfaces：**
  - Consumes: T1–T6 的实际 diff。
  - Produces: 一份核对结论（写进 `_temp/plan-evidence/code-review-remediation/T7-review.txt`）；README 至多一句增补（仅当 T3 的原子写被认定为「值得文档化的用户可见行为变化」时）。

  **Step 1（核对）：** 逐任务审读 T1–T6 的 staged diff，回答三个问题：
  1. 有没有 JSON 字段名/口径、CLI 退出码语义、MCP 工具名/入参 schema/返回键集合的变化？（预期：无。T3 的退出码变化是**修正违约**而非新语义，AGENTS.md:17 早已规定文件错误 → 2。）
  2. 有没有用户可见的新行为？（预期：T3 的「写失败不留半成品 + 退出码 2」是唯一值得一句话说明的。）
  3. 有没有 README 里已经描述过、但被本次改掉的行为？（预期：无。T5 不改 `connect()` 对已指定 serial 的判据，故 README:120 的 `no_connect` 描述仍准确。）

  **Step 2（按需补 README）：** 仅当第 1 步判定 T3 值得说明，在 README「JSON 输出提示」或相近小节加一句（模仿 `:125` 的措辞）：

  ```markdown
  `--out` 写入是原子的（先写临时文件再替换），失败时原文件保持不变且不留半成品。
  ```

  加完后跑 `selftest_tree.py` 确认 `:1183-1195` 的 README 断言全绿。**不得**为这句新建文本 grep 断言。

  **Step 3（核对 GAP-9 推迟记录）：** 在提交信息或 `_temp/plan-evidence/.../T7-review.txt` 里明确写一句：`config.json` 的 git 追踪策略（GAP-9/IS-9）已由用户决定推迟，理由是 `tests/selftest_tree.py:339-346` 依赖仓库真实 `config.json`，取消追踪需同步重写第 0 段，属不可逆的跨切面仓库策略变更。

  **Acceptance criteria：**
  - T7-review.txt 存在，逐条回答了上面三个问题，且结论与实际 diff 一致
  - 若加了 README 句子：`selftest_tree.py:1183-1195` 全绿；`git diff` 显示 README 只多了那一句
  - 若没加 README 句子：`git diff` 里 README 逐字节未变
  - GAP-9 的推迟理由已书面记录

  **QA — happy path：**
  ```powershell
  git diff --stat main~7..HEAD -- README.md config.json
  ```
  期望输出为空（README/config 未变）或仅 README 多一行（若加了原子写说明）。证据写入 `$ev/T7-happy.txt`。

  **QA — failure path：** 假设有人误把 `config.json` 改了：
  ```powershell
  git diff --stat HEAD -- config.json
  ```
  期望为空。若非空则**必须回滚** config.json 的改动（`git checkout -- config.json`）并重新提交。证据写入 `$ev/T7-fail.txt`。

  **Step 4：** 跑完整检查块 + 金样 check（最后一次全绿确认）。

  **Step 5（提交）：** 若有 README 改动则
  ```powershell
  git add README.md
  git diff --cached --check
  git diff --cached
  git commit -m "docs(readme): 补充 JSON 原子写说明"
  ```
  若无 README 改动则跳过提交（核对结论留在 `_temp/` 证据里）。

  Recommended task executor category: `writing` — 文档核对与可能的一句增补，无代码逻辑。

## Final verification wave

全部任务完成后**并行**派出下列终验任务；**每一个都必须 APPROVE** 才算交付。任何一个不 APPROVE，缺口转成新的 `- [ ] N.` 行补进 Todos，绝不降级成"备注"。终验结果与用户明确 OK 之前，不宣布完成。

- [ ] F1. 计划合规审计

  **审查对象：** 本计划文件 + T1–T7 的全部 staged diff 与提交。

  **审查内容：**
  - 每个任务的 `- [ ] N.` 行是否都在 `## Todos` 里、编号唯一、格式合规；F 行是否都在 `## Final verification wave` 里。
  - 每个任务是否都有 References / Acceptance criteria / happy+failure QA / Commit 行 / `Recommended task executor category:` 行。
  - 依赖矩阵（Execution strategy）与实际任务依赖是否一致：T4 的假件定义在第 16 段、T5 复用而不重复定义；T7 排在最后。
  - Must NOT have 清单逐条核对实际 diff：JSON 字段/退出码/MCP schema/generator/R0–R3/剪枝顺序/画框约定/domain 纯度/config.json/`.omo/`/`_temp/`/golden 基线——**一条违例即 FAIL**。
  - 每个任务的 staged diff 是否只含本任务文件（`tests/selftest_tree.py` 由各任务追加各自段，互不重叠）。
  - 命令与退出码逐条复核：完整检查块的每条命令 `$LASTEXITCODE` 检查是否都在。

  **证据：** `_temp/plan-evidence/code-review-remediation/F1-compliance.txt`。审查结论 `APPROVE` / `CHANGES REQUESTED` + 具体缺口。

- [ ] F2. 代码质量审查

  **审查对象：** T1–T6 修改的全部生产文件（`component.py`、`image.py`、`json_io.py`、`observe.py`、`tree.py`、`visible.py`、`adb.py`、`requirements.txt`）。

  **审查内容：**
  - 命名、类型注解、四空格、UTF-8；模块文档一行英文、函数/类文档与行内注释中文；库模块无 shebang/coding cookie。
  - 异常处理精确性：`props()` 只抛 `AdbError`；`connect()`/`_reconnect()` 不外漏异常；`emit_json` 的 `except OSError` 清理临时文件后 `raise`（保留原异常链，不吞）。
  - `emit_json` 的原子写模式与 `device_config.py:28-42` 是否同构（mkstemp → fdopen → replace → 失败 unlink）。
  - 无 AI 生成的代码气味：无空的 `except: pass` 遗留（T2 已把 `image.py:164-165` 的那个换成有内容的 note 追加）、无未使用的导入、无重复逻辑。
  - 依赖方向：domain 层不碰设备/文件/终端/MCP/Pillow/uiautomator2（重点查 `component.py` 仍是纯正则）。

  **证据：** `_temp/plan-evidence/code-review-remediation/F2-quality.txt`。

- [ ] F3. 真实环境 QA（离线必做 + 有设备才做）

  **离线必做（不需要 TV）：**
  1. 完整检查块全绿（逐条退出码）。
  2. `python tests/selftest_tree.py` 全绿，断言数 > 714（新增第 13–18 段的断言全部在内）。
  3. 三条 `--from-json` 离线运行全绿，其中 `observe --out NUL` 退出码 0（验证 T3 的设备名特判）。
  4. 金样 `golden.py check` 零差异（本地 `_temp/golden/` 存在时）。
  5. `python main.py --help` 与 `python main.py tree --prune-list` 输出正常。

  **有可用设备时才做（不阻塞离线验收，但有设备就必须做）：**
  6. `python main.py observe --out observe.json` 真机采集一次，确认 `device` 字段的 8 个键值对位正确（`ro.product.manufacturer` 是厂商、`ro.product.model` 是机型、`ro.build.type` 是构建类型——不是互相串位）。
  7. 若设备支持网络 ADB，触发一次掉线重连（`adb disconnect` 后立即 `observe`），确认 stderr 里的 `[adb] 连接中断，已自动重连` 之后采集继续成功（验证 T5 的状态判据）。
  8. `python main.py shot --json observe.json --out shot.png` 画一次框，确认框线落在读数上、notes 无异常。

  **证据：** `_temp/plan-evidence/code-review-remediation/F3-qa.txt`（离线部分）与 `F3-device.txt`（有设备时；无设备则写明"设备不可用，离线验收通过"）。

- [ ] F4. 理想状态保真度（IS 行逐条对照）

  **审查内容：** 把交付的实际行为与 Scope 里的 IS-1..IS-11 逐条对照，**一行一行**确认每条 IS 行都已被证明。任何一条未证明 → 转成新的 `- [ ] N.` 行。

  | IS | 证明方式 | 证据 |
  |---|---|---|
  | IS-1 | T4 断言：8 行/含空行/6 行/9 行/rc!=0 五种输入；串位抛 AdbError | F3-qa 第 6 条（有设备时）+ T4-fail.txt |
  | IS-2 | T3 断言：os.replace 失败 → 无半成品、无 .tmp 残留 | T3-fail.txt |
  | IS-3 | T5 断言：回显 connected 但 devices offline → False | T5-fail.txt |
  | IS-4 | T2 断言：text 抛异常 → notes 含说明且含 label | T2-fail.txt |
  | IS-5 | T1 断言：两种 uid/1000 形状 → None | T1-fail.txt |
  | IS-6 | T6 断言：requirements 无 uiautodev | T6-happy.txt |
  | IS-7 | T6 断言：adb.py 无个人路径 | T6-fail.txt |
  | IS-8 | T5 断言：多设备 → False 且不改写 serial | T5-fail.txt |
  | IS-10 | 本计划存在于 docs/，F1 审计通过 | F1-compliance.txt |
  | IS-11 | T3 断言：三条命令 --out 写失败 → 退出码 2、无 traceback | T3-fail.txt |

  **IS-9 明确不在本表**——它是用户决定推迟的，已在 Out of scope 记录，不算未关闭缺口。

  **证据：** `_temp/plan-evidence/code-review-remediation/F4-fidelity.txt`。

---

## Commit strategy

**分支与推送：** 在 `main` 原地执行，不开分支、不提 PR、不 push/merge（沿用上一份计划 `2026-10-02-comment-naming-structure.md:24` 与执行裁决第 1 条）。若改用 PR 流程，由执行者在 `/ulw-execute --make-pr` 下走，且 PR 描述需按 AGENTS.md「Contribution」段说明行为变更与验证结果，几何/渲染变化附前后 JSON 或截图。

**提交粒度：** 每个任务一个提交（共 7 个潜在提交，T7 可能没有提交）。提交顺序 = 任务执行顺序 T1→T2→T3→T4→T5→T6→T7。理由：每个提交都以「全量检查绿」收尾，粒度对应回归单元，出问题可精确 revert 单个任务而不拖累其他。

**提交信息约定（已按 Codex 重写后的现行规范修正）：**
- 采用 **Conventional Commits**：`类型(范围): 中文描述`。类型/范围为小写英文，中文描述为动词短语、单行、无句末句号、无正文。实测现行规范（`git log --format=full -4`）：`docs(plan)`、`chore(repo)`、`style(comments)`、`refactor(observation)`、`fix(interfaces)`、`feat(mcp)` 等。
- 各任务提交行已对齐：
  - T1 `fix(component): 拒绝窗口焦点解析中的非 component 子串`
  - T2 `fix(image): 截图标签绘制失败时写入 notes 而非静默吞掉`
  - T3 `fix(interfaces): JSON 输出改为原子写并把写失败映射为退出码 2`
  - T4 `fix(adb): getprop 输出错位时明确报错，不再平移设备属性`
  - T5 `fix(adb): 重连按设备状态判定且不在多设备时猜目标`
  - T6 `chore(repo): 移除未引用依赖与机器相关的 ADB 探测路径`
  - T7（若有 README 改动）`docs(readme): 补充 JSON 原子写说明`
  - 计划归档 `docs(plan): 添加代码评审整改计划`
- **尾注规则：** 代码类提交（fix/feat/refactor/style/chore 触及源码者）末尾附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`；`docs(plan)` 纯计划提交**不附**尾注（现行历史一致）。T6 触及 `requirements.txt` + `adb.py`，附尾注。
- T6 的提交正文可补一行探测行为变化说明（见 T6 Step 5）——正文仅此一处需要，其余保持单行。

**暂存纪律（每任务 Step 5）：**
1. `git add` 只列本任务文件（`tests/selftest_tree.py` 由该任务追加的段；跨任务文件按段归属）。
2. `git diff --cached --check`（whitespace 错误）→ 退出码 0。
3. `git diff --cached --stat` → 人工确认文件清单。
4. `git diff --cached` 全量审查 → 不得混入 `config.json`、`.omo/`、`_temp/`、其他任务改动、半成品。
5. 若暂存区已有其他内容，**先报告并保留，不清空**（AGENTS.md「Contribution」段）。

**绝不提交：**
- `config.json`（含本机地址 `192.168.1.147`）——每次提交前 `git diff --cached --name-only` 确认它不在列表里。
- `.omo/`（计划/草稿状态）——本计划文件本身提交到 `docs/` 是 T7 的职责（或由用户手动放置），`.omo/` 下的 draft 不提交。
- `_temp/` 下任何东西（QA 证据、金样、e2e 产物）——已 gitignore，作为本地验收证据。

**计划文件本身的归档：** 本计划当前写在 `.omo/plans/2026-10-02-code-review-remediation.md`（规划工具的落点）。你要的交付位置是 `docs/superpowers/plans/2026-10-02-code-review-remediation.md`。**把它放过去是执行阶段（或你手动）的一件事**：

```powershell
Copy-Item .omo\plans\2026-10-02-code-review-remediation.md docs\superpowers\plans\2026-10-02-code-review-remediation.md
git add docs/superpowers/plans/2026-10-02-code-review-remediation.md
 git commit -m "docs(plan): 添加代码评审整改计划"
```

（如果用 `/ulw-execute` 跑本计划，把这一步作为第一个任务之前的手动准备，或作为 T7 的一部分。）

---

## Success criteria

| IS 行 | 由哪个任务关闭 | 证明 QA | 证据路径 |
|---|---|---|---|
| IS-1 device 字段不串位 | T4 | 8 行对位 + 含空行对位 + 串位抛 AdbError + 降级 `{}` | `_temp/plan-evidence/code-review-remediation/T4-happy.txt`, `T4-fail.txt` |
| IS-2 --out 不留半成品 | T3 | os.replace 失败 → 目标不存在、无 .tmp | `T3-fail.txt` |
| IS-3 重连判定是状态非措辞 | T5 | connected 回显 + offline 状态 → False | `T5-fail.txt` |
| IS-4 标签失败可解释 | T2 | text 抛异常 → notes 含说明 + label | `T2-fail.txt` |
| IS-5 伪 component 被拒 | T1 | 两种 uid/1000 形状 → None | `T1-fail.txt` |
| IS-6 依赖干净 | T6 | requirements 无 uiautodev | `T6-happy.txt` |
| IS-7 探测路径无个人痕迹 | T6 | adb.py 无 D:/SoftwareInstalled | `T6-fail.txt` |
| IS-8 不猜目标设备 | T5 | 多设备 → False、serial 不变 | `T5-fail.txt` |
| IS-10 计划在 docs/ 且格式合规 | 交付动作 + F1 | F1 审计 APPROVE | `F1-compliance.txt` |
| IS-11 --out 写失败退出码 2 | T3 | 三条命令退出码 2、无 traceback | `T3-fail.txt` |
| IS-9（刻意推迟） | — | Out of scope 已书面记录 | T7-review.txt |

**总验收：** F1/F2/F3/F4 全部 APPROVE + 上表每行证据存在 + 完整检查块全绿 + 金样零差异（本地）+ `tests/selftest_tree.py` 断言数 > 714 且全绿。

---

## Plan self-review

1. **Spec coverage：** 8 项 GAP（1,2,3,4,5,6,7,8）+ 1 项新发现（11）各有至少一个任务关闭；IS-9 明确列为用户决定推迟，不算未关闭缺口。每个 GAP 行都在 Scope 表里有对应 IS 行与任务。
2. **Failure-phase safety：** 5 条 RED 规则封死顺序脚本中止风险；每个新异常断言用宽捕获 + `isinstance`；新属性用 `getattr(..., None)`；假件按命令名分派；新段互不重叠。T2 的 `notes==[]` 硬约束（`:1108-1111`）已写进 Step 3 与 Acceptance。
3. **Execution and types：** 依赖矩阵只有 T4→T5 一条硬链；每个任务的 Files / Interfaces / Consumes / Produces 明确；`Recommended task executor category` 全部给出且理由一行。
4. **Validation：** 每任务提交前跑完整检查块 + 金样；QA 覆盖 happy + failure 且有证据路径；离线可执行（不需要设备）。`--out NUL` 特判在 T3，是后续检查块的前提。
5. **Golden contract：** 只跑 `check` 不跑 `make`；期望零差异；临时文件清理防金样「新文件」失败。金样在 `_temp/`（gitignore），只读不提交。
6. **Scope：** 计划修订阶段只写 `.omo/plans/` 下这一个文件；不碰 `config.json`、不碰 `.omo/drafts/` 以外的文件。Gap-9 的推迟已有书面理由（`selftest_tree.py:339-346` 依赖真实 config）。
7. **Metis 反馈吸收：** Metis 的 10 项发现（G-A..G-O）全部折进任务细节（设备名特判、原子写 RED 机制、AdbError 类型、假件分派规则、正则双修、golden 检查、per-command 退出码、README 断言保护等）。Metis 的 G-H（只改回退正则）经实测**推翻**，改为双修 + `+` 量词，已在 TL;DR 与 Scope 记录。
8. **Task row grammar：** 所有 `- [ ] N.` 行编号连续（1–7）、格式合规；F 行为 `- [ ] F1.` .. `- [ ] F4.`；无 prose bullet 冒充任务。

<!-- CONT-6 -->
