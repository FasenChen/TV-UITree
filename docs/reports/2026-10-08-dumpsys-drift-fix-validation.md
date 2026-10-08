# dumpsys 漂移误报修复与验收（2026-10-08）

消息队列等非 View 日志变化导致的漂移误报已修复。离线自检 1155 条、9 份历史真机输入回放、新真机数据与截图 20 项检查、真实 MCP 36 项检查全部通过。未提交或推送。

## 根因与变更

此前 `_hierarchy_lines` 以同时包含左右花括号作为 View 行条件，误收 MessageQueue 日志，也漏掉无花括号的旧格式 DecorView 根行。历史 9 份采集中，4 份真实 View 行未变化却返回 `drift=true`。

本次复用 `parse_dumpsys_top` 与节点的 `lineno`，取回现有解析器实际消费的 View 原文；仍比较原始顺序、缩进、flags、实例标识及坐标。继续比较所有已解析 Activity 段。修复位于唯一共享调用方 `snapshot.py` 所用的 domain 函数，CLI 与 MCP 不需要各自补丁。

生产变更仅涉及 `tvuitree/domain/tree/capture.py`；永久回归写入既有 `tests/selftest_tree.py`。没有新增依赖、模块、开关或归一化规则。接口字段、R0–R3、匹配、可见筛选、焦点与截图坐标契约均未改动。

## 离线验证

| 检查 | 实际结果 |
|---|---|
| 修改前基线 | 1140 条自检通过 |
| 先加入回归，生产代码保持旧实现 | 1155 条中 7 条按预期失败，退出码 1 |
| 应用最小修复后完整自检 | 1155 条全部通过，退出码 0 |
| `py_compile`、`pyflakes`、`git diff --check` | 均通过 |
| `main.py --help`、`main.py tree --prune-list` | 均通过 |
| 9 份历史原始 dumpsys 前后输入回放 | 9/9 通过，原 4 个误报消失 |

新增回归覆盖非 View 日志增删与变化、层次外形似 View 的日志、真实节点增删、焦点 flags、旧格式根行、Android 16 后置根名称、顺序、缩进层级、多 Activity 与层次消失。既有坐标变化、相同输入、单调时钟、空输入和差异说明测试保留。

旧 full JSON、原始捕获和旧 `drift_findings.json` 保持历史内容；修复后回放结果另存，不改写旧警告。

## 新真机验证

本轮开始时电视位于 launcher 的 Watchlist 焦点。为取得跨调用可比的稳定画面，经已观察到的 Open Settings 入口进入设置，仅移动焦点，没有修改设置项。

| 场景 | 焦点与坐标 | a11y / View / 配对 | 检查 |
|---|---|---|---|
| 稳定设置页 | GENERAL SETTINGS；`[105,276,427,334]` | 46 / 70 / 46 | 10/10 通过 |
| 单次 DOWN 后 | Channels & Inputs；`[90,327,822,465]` | 58 / 96 / 58 | 10/10 通过 |

两场景分别核对原始 XML 字段、顺序与父子关系、每个 View 的覆盖和 flags/局部坐标、XML 与 View 的唯一焦点、visible 的文案/状态/动作/矩形、PNG 逻辑尺寸和独立绘制的逐像素边框。两次抓取中的真实 View 行均一致，修复返回 `drift=false`、`detail=null`，无漂移警告。

新稳定页原始输入也复现了根因：旧花括号筛选返回漂移，独立 View 行核对与修复实现均判断不漂移。真实 View 变化的确定性检测由永久离线回归验证，不要求电视恰好在两次采集之间改变布局。

测试结束经返回键和方向键恢复 launcher 的原 Watchlist 焦点；类别、文案、`[124,352,572,449]` 坐标与 `selected=true` 一致。页面时钟及动态内容不要求与测试前像素完全相同。

## 真实 MCP 与 CLI 验证

启动实际 stdio MCP，五个读取工具共调用 9 次：`get_full_tree`、`observe_tv`、`get_visible`、`get_current_focus`、`get_focus_screenshot`。另检查非法布尔端口在写配置前拒绝。36 项检查全部通过，包括：

- 双源与 a11y 模式的原始读数、观察/可见投影、唯一焦点，以及 `max_nodes` 截断。
- 两次截图分别生成新路径，PNG 文件、Base64 和 MCP 原生 Image 字节一致，标注像素与当次稳定画面一致。
- 每个执行的工具只向 stderr 写一个计时块；stdio 协议成功。
- 跨调用原始字段及原始截图像素保持稳定；配置字节不变。
- CLI 的 observe/visible 离线结果与完整 JSON 的纯投影一致，slim 回放成功。

首次在动态 launcher 上执行同一组检查时，30 项通过、6 项跨帧比较失败；捕获显示临时快捷控件、时钟和画面在不同调用间变化。该次结果完整保留，随后在稳定设置页重验通过。没有通过修改生产逻辑掩盖跨帧变化。

临时验收脚本按真实契约修正两项假设：规范化 Activity 的短类名以核对原始 View，焦点容器无直接文案时允许 `labels` 缺省并继续与当次 baseline 比较。这些改动只在忽略目录，不影响正式工具。

## 执行与交付

复用原项目虚拟环境，在原 main 基线的受管隔离 worktree 实施；计划要求的 Bash 记账方式改用 PowerShell/Python，账本与原始证据放在项目约定的 `_temp/`。通过检查后交付相关文件到原工作区，保留原 `config.json` 的已有修改和历史验收报告。不执行 Git 合并、提交或推送。

独立终审已完成：Critical / Important / Minor 均无发现；五类 Review Focus 逐项核对通过。审查者独立复跑 1155 条自检、pyflakes、38 文件内存语法编译、9 份历史和 2 份新原始输入回放，复核 MCP 计时块、截图字节与跨帧像素证据。回写原工作区后再次执行 py_compile、pyflakes、完整自检（1155 条）、CLI help/prune-list 及 git diff --check，全部退出码为 0。五个任务文件已交付，配置、历史报告及旧原始结果哈希/字节不变；隔离 worktree 的临时日志和截图已逐文件核对并保存，可通过受管归档恢复工作区快照。本报告的验证范围是本次缺陷及实际测试场景，不代表所有应用、所有 Android 版本均已验收。解析器未消费的未知 View 格式不在本次新增识别范围内；既有解析器是漂移检测与树构建共同使用的事实来源。

## 本地证据

原始证据位于忽略目录，不随仓库提交。即使这些本地文件缺失，以上结果、范围和执行方式仍可独立阅读。

- [RED 日志](../../_temp/tv_validation_20261008_drift_fix/red.log)、[GREEN 日志](../../_temp/tv_validation_20261008_drift_fix/green.log)
- [历史回放修复前](../../_temp/tv_validation_20261008_drift_fix/drift_findings_before.json)、[修复后](../../_temp/tv_validation_20261008_drift_fix/drift_findings_after.json)
- [20 项真机汇总](../../_temp/tv_validation_20261008_drift_fix/live_fix_summary.json)、[36 项 MCP 汇总](../../_temp/tv_validation_20261008_drift_fix/mcp/summary.json)
- [首次动态页面 MCP 结果](../../_temp/tv_validation_20261008_drift_fix/mcp_desktop_attempt/summary.json)
- [交付后检查](../../_temp/tv_validation_20261008_drift_fix/delivery_checks.json)、[交付自检日志](../../_temp/tv_validation_20261008_drift_fix/delivery_selftest.log)
- [焦点恢复核对](../../_temp/tv_validation_20261008_drift_fix/restoration_summary.json)、[执行账本](../../_temp/tv_validation_20261008_drift_fix/progress.md)

实施依据见[修复计划](../superpowers/plans/2026-10-08-dumpsys-drift-false-positive.md)。[原真机报告](2026-10-08-real-tv-data-validation.md)保留修复前发现及结论。
