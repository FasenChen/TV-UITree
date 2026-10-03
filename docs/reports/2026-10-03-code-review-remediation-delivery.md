# 交付文档：code-review-remediation 整改交付（供 Codex 审核）

> 归档说明（2026-10-03）：本文是 Zcode 的交付记录，原位于 `_temp/plan-evidence/code-review-remediation/DELIVERY.md`。以下修复、790 条断言及 APPROVE 为 Zcode 声明，本次文档整理没有重新审核代码或复跑测试。执行依据为 [2026-10-02 原计划](../superpowers/plans/2026-10-02-code-review-remediation.md)，并非 [Codex 的 2026-10-03 修订计划](../superpowers/plans/2026-10-03-code-review-remediation-zcode.md)；整改后代码仍需结合 [实施前评审](../reviews/2026-10-02-code-review-remediation-review.md) 单独核对。归档时脱敏了本地设备地址，并修正了第 6 节待补 QA 的错误输入与恢复验证方式。原始执行证据仍在 `_temp`，不随仓库提供。

文档入口：[项目文档索引](../README.md)。

后续状态：[Codex 独立代码复审](../reviews/2026-10-03-zcode-remediation-code-review.md) 已确认现有 790 条自检通过，同时发现 R1–R5；本文原交付声明中的“全部关闭”不能作为当前验收结论。

- 交付日期：2026-10-03
- 执行依据：`docs/superpowers/plans/2026-10-02-code-review-remediation.md`（与 `.omo/plans/2026-10-02-code-review-remediation.md` 逐字节一致，已随 `45064d0` 入库）
- 交付区间：`6d174cd..45064d0`，共 8 个提交，在 `main` 原地执行，未推送远程
- 环境：Windows 10.0.26200 / Git Bash / 项目 venv `.venv\Scripts\python.exe`（Python 3.14.3，`PYTHONUTF8=1`）
- 总结论：**9 项缺陷（GAP-1..8、GAP-11）全部关闭，终验 F1/F2/F4 均 APPROVE，F3 离线部分全绿、真机部分待设备可用补做**

---

## 1. 提交清单与文件边界

| 提交 | 任务 | 文件 |
|---|---|---|
| `93ffa9b` | T1 fix(component): 拒绝窗口焦点解析中的非 component 子串 | `tvuitree/domain/component.py`、`tests/selftest_tree.py`（第 13 段） |
| `67e9f3a` | T2 fix(image): 截图标签绘制失败时写入 notes 而非静默吞掉 | `tvuitree/infrastructure/image.py`、`tests/selftest_tree.py`（第 14 段） |
| `eb00cb2` | T3 fix(interfaces): JSON 输出改为原子写并把写失败映射为退出码 2 | `tvuitree/interfaces/{json_io,observe,tree,visible}.py`、`tests/selftest_tree.py`（第 15 段） |
| `6fe42ff` | T4 fix(adb): getprop 输出错位时明确报错，不再平移设备属性 | `tvuitree/infrastructure/adb.py`、`tests/selftest_tree.py`（第 16 段，定义 ADB 假件） |
| `a1e7e28` | T5 fix(adb): 重连按设备状态判定且不在多设备时猜目标 | `tvuitree/infrastructure/adb.py`、`tests/selftest_tree.py`（第 17 段，复用假件） |
| `a77a6a4` | T6 chore(repo): 移除未引用依赖与机器相关的 ADB 探测路径 | `requirements.txt`、`tvuitree/infrastructure/adb.py`、`tests/selftest_tree.py`（第 18 段） |
| `4f62bfd` | T7 docs(readme): 补充 JSON 原子写说明 | `README.md`（仅 1 行） |
| `45064d0` | docs(plan): 添加代码评审整改计划 | `docs/superpowers/plans/2026-10-02-code-review-remediation.md` |

范围合计 11 个文件，+471/−31（`git diff 6d174cd..45064d0 --stat`）。`config.json`、`.omo/`、`_temp/` 未入库；`tvuitree/interfaces/mcp.py` 零改动；full JSON `generator` 仍为 `tv_tree.py`。

## 2. 缺陷 → 修复 → 验证对照

| GAP | 缺陷（修复前） | 修复 | 离线验证 |
|---|---|---|---|
| GAP-5 | `component_from_window` 把 `uid/1000` 当成前台 component，下游 `pick_block` 可能回退到另一页面的树 | 两条正则的包名组改为 `[A-Za-z][\w]*(?:\.[\w]+)+`（严格与回退各一处，点号组为 `+` 不是 `*`） | 第 13 段：3 种 `uid/1000` 形状 → `None`；真机格式 4 例保持原返回 |
| GAP-4 | `dr.text` 失败被 `except: pass` 静默吞掉，截图缺标签无从解释 | `except` 分支追加中文 note（含 label 与异常类型）；正常路径零追加（`notes==[]` 断言保持） | 第 14 段（Pillow 已装，实际执行）：monkeypatch `ImageDraw.text` 抛 OSError → notes 含「框标签绘制失败…TextView#title」，框照画、几何逐像素不变 |
| GAP-2 | `emit_json` 裸 `open` 直写，中断会留下截断半成品 | mkstemp → fdopen → `os.replace` 原子替换；失败 unlink 临时文件后 `raise`；Windows 保留设备名（NUL/CON/COM1…）与 `os.devnull` 退回直写（`--out NUL` 既有用法兼容） | 第 15 段 (a)：注入 `os.replace` 失败 → OSError 传播、目标不存在、无 `.tmp` 残留；成功路径字节数按 UTF-8（含末尾 LF）、无 CRLF |
| GAP-11 | `observe/tree/visible` 的 `emit_json` 在 try/except 之外，写失败 → traceback + 退出码 1，违反 AGENTS.md「文件错误 → 2」 | 新增 `emit_json_checked`（OSError → 中文 stderr + 返回 2），三个调用点接入且写失败不打印成功提示 | 第 15 段 (b)：三条真实子进程 `--out` 指向不可写路径 → 退出码 2、stderr 有中文说明、无 `Traceback` |
| GAP-1 | `props()` 用 `shell` 拼接 getprop 并过滤空行，空值使后续属性整体前移（model 静默变成 device 的值）；行数不符时 zip 静默补齐/丢弃 | 改用 `shell_raw`（只取 stdout）、不过滤空行；`rc != 0` 或行数 ≠ 8 抛 `AdbError`（唯一调用方 `snapshot.py` 只捕 `AdbError`，干净降级为 `dev={}`） | 第 16 段：8 行对位、含空行对位（空值不挤位）、6/9 行与 rc≠0 抛 `AdbError`、降级 `{}` |
| GAP-3 | `_reconnect` 靠 connect 回显措辞（`"connected" in msg`）猜结果，回显说 connected 但设备 offline 时误报已重连 | 新增 `_serial_is_device()`：跑 `adb devices` 并要求本 serial 状态列为 `device`；`_reconnect` 用它作判据，`heal=False` 递归防护不变，成功时保留既有 `[adb] 连接中断，已自动重连` 日志 | 第 17 段：回显 connected + offline → False；陌生措辞 + device → True；devices 查询抛 AdbError → False 不外漏 |
| GAP-8 | `connect()` 空 serial 时静默选中 `targets[0]` 并改写 `self.serial`，可能操作调用方从未指定的设备 | 空 serial：恰好一台 → 自动选中（便利保留）；多台 → 返回 False + warning 列出设备，serial 不改写；零台 → False。已指定 serial 的成员判据逐字未动（README `no_connect` 行为依赖它）；全程不抛异常（`connect_for_cli` 调用处无 try/except） | 第 17 段：多设备 → False 且 serial 保持 None；单台 → True 并填 serial；指定 serial 行为不变 |
| GAP-6 | `requirements.txt` 含零 import 的 `uiautodev`（死重量 + 供应链面） | 仅删该行，其余 4 行与顺序不动 | 第 18 段源文本断言 |
| GAP-7 | `ADB_CANDIDATES` 含两个个人机器路径（`D:\platform-tools`、`D:\SoftwareInstalled\...`） | 删两条 `D:` 候选，保留 `C:\platform-tools` 与环境变量/标准 SDK 探测；`resolve_adb` 函数体不动 | 第 18 段源文本断言；`resolve_adb("X:/adb.exe")` 既有断言继续通过 |

## 3. 执行偏差声明（与计划文本的差异，均已记录并经 F1 审计确认）

1. **金样基线在动工前已过期（与本次改动无关）**：base 生成于 2026-09-30 17:14，早于 `89c3307`（2026-10-02，把 `[out]` 字节数从 locale/GBK 计数修复为显式 UTF-8）；且捕获环境此后迁到 UTF-8（`PYTHONUTF8=1`）。原始 `golden.py check` 有 10 个 `.txt` DIFF（恰为全部 .txt），经 GBK→UTF-8 转码归一后收敛为且仅为：字节数数字（5 例）、GBK 编不出的 `⊆`/`−`（2 例）、转码后完全一致（3 例）；全部 7 个 `.json`、3 个 `.png`、`rebuilt_full.json` 逐字节相同。遵守计划禁令未跑 `make`，改用 `_temp/plan-evidence/code-review-remediation/golden_equiv.py` 作每任务金样判据（非 .txt 必须逐字节相同；.txt 仅允许上述三类差异；出现 NEW/MISSING/其他差异即失败），T1–T6 每个任务后均通过。
2. **T3 RED 片段两处修正**（否则顺序自检中止，违反计划规则 5 的精神）：当前 `json_io` 尚未 `import os`，先 `json_io.os = os` 兜底再打补丁；`t.eq` 无第 4 参数签名，`_litter` 先算后断言。
3. **T4/T5 测试假件解码契约**：`_FakeAdbPopen._popen` 在 `binary=False` 时把 out/err 解码为 str（计划片段原样返回 bytes，违背真实 `_popen` 契约，会让 RED 阶段「正常 8 行」等用例也变红）。
4. **T5 保留重连成功日志**：计划 GREEN 片段漏掉 `logging.warning("[adb] 连接中断，已自动重连 %s")`，但计划 F3 真机 QA 第 7 条明确依赖该 stderr 消息，故恢复；属既有行为保留，非新增。
5. **`--out` 写失败退出码从 1/traceback 变为 2**：这是计划 T3 的明文产出（GAP-11），修复的是对 AGENTS.md:17「文件错误 → 2」的既有违约，不是新语义（F1 审计已按此定性）。

## 4. Codex 可复跑的验证清单

在仓库根目录、使用项目 venv（PowerShell 版；`$py = '.\.venv\Scripts\python.exe'`）：

```powershell
# 1) 编译与静态检查（预期均退出码 0、零输出）
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
& $py -m py_compile $pythonFiles
& $py -m pyflakes $pythonFiles

# 2) 离线回归（预期：790 条断言全部成立，退出码 0）
& $py tests/selftest_tree.py

# 3) CLI 冒烟（预期退出码 0）
& $py main.py --help
& $py main.py tree --prune-list

# 4) 离线 --from-json 三条（预期退出码 0；--out NUL 验证设备名直写特判）
& $py main.py observe --from-json _temp/e2e/full.json --out NUL
& $py main.py visible --from-json _temp/e2e/full.json --out NUL
& $py main.py tree --from-json _temp/e2e/full.json --mode slim --out NUL

# 5) 金样等效判据（预期末行「通过」，退出码 0；先跑一次 golden.py check 以生成 now/）
& $py _temp/golden/golden.py check
& $py _temp/plan-evidence/code-review-remediation/golden_equiv.py
#    说明：golden.py check 原始退出码为 1（基线过期，10 个既有 .txt 差异），
#    归一判据见 BASELINE-golden.txt 与 golden_equiv.py 头注释。

# 6) 抽查核心行为
& $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.domain import component as c; print(c.component_from_window('Window{abc u0 uid/1000}'))"
#    预期输出 None
& $py -c "import sys; sys.path.insert(0,'.'); from tvuitree.infrastructure import adb; bad=[c for c in adb.ADB_CANDIDATES if 'D:' in c or 'SoftwareInstalled' in c]; print('personal paths left:', bad)"
#    预期输出 personal paths left: []
```

关键护栏断言位置（复审时重点看 `tests/selftest_tree.py`）：第 0 段读真实 `config.json`（未动）；`:1108-1111` 画框正常路径 `notes==[]`；`:1159-1195` 源文本与 README 机器检查；`:2056-2065` emit_json 字节数/LF；`:2116-2120` json_io 公开函数；新增第 13–18 段（`git diff 6d174cd..45064d0 -- tests/selftest_tree.py` 为单 hunk 纯追加 +337/−0，第 0–12 段零删改）。

## 5. 终验结论与证据索引

| 终验 | 结论 | 证据（`_temp/plan-evidence/code-review-remediation/`） |
|---|---|---|
| F1 计划合规审计 | **APPROVE**（Must-NOT-have 16 项逐条通过；文件边界 8/8；依赖矩阵合规；偏差 1–5 全部核实） | `F1-compliance.txt` |
| F2 代码质量审查 | **APPROVE**（风格/注解/异常精确性/原子写同构/AI 气味清零/依赖方向干净；2 条备查观察项均属既有行为，不构成缺口） | `F2-quality.txt` |
| F3 真实环境 QA | 离线部分**全绿**（检查块逐条退出码 + 790 断言 + 金样等效通过）；真机部分待补 | `F3-qa.txt`、`F3-device.txt` |
| F4 理想状态保真 | **APPROVE**（IS-1..IS-11 逐条已证明；IS-1/IS-3 附真机复核备注） | `F4-fidelity.txt` |



本地证据链接（仅当前工作区可用）：[F1 合规审计](../../_temp/plan-evidence/code-review-remediation/F1-compliance.txt)、[F2 质量审查](../../_temp/plan-evidence/code-review-remediation/F2-quality.txt)、[F3 离线 QA](../../_temp/plan-evidence/code-review-remediation/F3-qa.txt)、[F3 设备记录](../../_temp/plan-evidence/code-review-remediation/F3-device.txt)、[F4 保真核对](../../_temp/plan-evidence/code-review-remediation/F4-fidelity.txt)、[金样等效脚本](../../_temp/plan-evidence/code-review-remediation/golden_equiv.py)。这些原始日志保留在 `_temp`，不与长期报告一起归档。

每任务 QA 证据：`BASELINE-golden.txt`、`golden_equiv.py`、`T1..T6` 的 `*-happy.txt` / `*-fail.txt`、`T3-slim.json`、`T7-review.txt`。

## 6. 遗留事项

1. **真机 QA 待补**：Zcode 执行时记录 TV 不可达（设备列表为空、连接超时），不代表归档时的在线状态。设备可用后，采集 full JSON 核对设备属性，并使用 `shot --json full.json --out shot.png` 验证画框；observe 摘要没有 tree，不能作为 shot 输入。初始连接不能证明采集中自动恢复，恢复路径应采用保留真实 `_popen` 的离线故障模拟验证；不得把全局 `adb disconnect` 当作常规检查。真机测试是否影响最终验收由实际验证范围决定，本次归档不作“不阻塞”的新结论。
2. **GAP-9 / IS-9（config.json 的 git 追踪策略）按用户决定推迟**：`tests/selftest_tree.py` 第 0 段依赖仓库真实 `config.json`，取消追踪需同步重写第 0 段、README 快速开始、`device_config` 报错文案与 `set_default_device` 语义，属不可逆跨切面变更，需另开任务（书面记录见 `T7-review.txt`）。
3. **金样基线重建（建议，需用户决策）**：当前 base 与环境/`89c3307` 存在既有漂移，靠 `golden_equiv.py` 归一判据弥补。可在任一后续时点由用户显式批准 `golden.py make` 重建基线，使 `golden.py check` 恢复严格零差异。
4. **工作区未跟踪项（按 AGENTS.md 保留，未入库）**：`.omo/`、`.zcodeignore`、`docs/superpowers/plans/2026-10-03-code-review-remediation-zcode.md`（同一整改的 Zcode 交接版计划，与本计划不同源）。

## 7. 审查注意

- 本交付在 `main` 原地执行、未推送；如需 PR/推送流程请另行授权目标与范围。
- `props()` 串位时抛的是 `AdbError` 而非 ValueError：`snapshot.py:21` 只捕 `AdbError` 并降级 `dev={}`，换异常类型会破坏既有降级设计（CLI rc 3 / MCP `error`）。
- `connect()` 多设备时必须返回 False 而非抛异常：`interfaces/connection.py` 调用处无 try/except，抛出会变成 traceback + 退出码 1。
- `--out NUL` 是本仓库既有离线检查写法：`_is_device_target` 的设备名特判是为保住它，不是多余分支。
- 画框约定（框 = 读数、逐像素对齐、不加偏移、不补偿）未动；`image.py` 的改动仅在异常分支追加 note。
