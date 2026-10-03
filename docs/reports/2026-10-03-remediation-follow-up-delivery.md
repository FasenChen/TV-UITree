# 整改复审补修交付与验证报告

日期：2026-10-03。实施依据：[补修计划](../superpowers/plans/2026-10-03-remediation-follow-up.md)；问题来源：[Zcode 整改代码复审 R1–R5](../reviews/2026-10-03-zcode-remediation-code-review.md)。

本轮已完成 R1–R5 的最小补修和回归补强。最终离线自检 864 条断言全部成立；19 个金样产物与本轮执行前基线逐字节一致。当前配置的 TV 不可达，未完成真机采集与画框验证。[独立终审](../reviews/2026-10-03-remediation-follow-up-final-review.md)发现一处新增测试的编码依赖，已按 RED→GREEN 修复；没有未处理的重要或轻微问题。

## 实施范围

**后续 Git 交付：** 用户随后明确授权提交并推送至 `origin/main`。补修代码已提交为 `8ca3846`（`fix(remediation): 修复组件解析与连接查询并补齐输出回归`）；文档归档独立使用 `docs(remediation)` 提交。本报告下文的 HEAD、未提交状态及相关裁定是执行终验时的历史快照，不能视为后续授权后的当前 Git 状态。文档提交可通过本文件的 Git 历史定位；推送结果以远程分支核对记录为准。

执行前、执行后的 HEAD 均为 `45064d04053990c67c87a90104b6a4f660b5d66a`；本轮代码保留为未暂存的工作树差异，没有提交、推送、合并或历史改写。此前文档归档改动及 `.omo/`、`.zcodeignore` 保留。

| 文件 | 本轮改动 |
|---|---|
| `tvuitree/domain/component.py` | 仅窗口组件解析，允许合法系统包并拒绝数字类名；activity record 解析及归一函数未改 |
| `tvuitree/infrastructure/adb.py` | connect 清除陈旧连接状态，处理设备查询异常与非零退出码；恢复查询检查退出码 |
| `tvuitree/interfaces/json_io.py` | Windows 保留设备名仅在 Windows 特判；实际 os.devnull 仍直接输出 |
| `tests/selftest_tree.py` | 第 15 段使用有效输入验证输出；第 19–23 段覆盖补修及真实执行边界 |
| `README.md` | 明确连接/采集错误退出码及普通文件原子替换的范围，保留此前索引链接 |
| `docs/README.md`、本报告、补修计划 | 本轮执行记录与文档索引 |

`config.json` 的 SHA256 与执行前一致，配置内容未记录到报告。props、截图绘制、依赖、ADB 搜索路径、generator、剪枝规则、MCP schema 和 timing 生产实现未改。

## 问题与证据

| 问题 | 修复后的行为 | 永久回归及 RED→GREEN |
|---|---|---|
| R1：强制包名带点号拒绝系统包 | `android/com.android.internal.app.ResolverActivity` 在严格与回退路径均可识别；UID/数字类名拒绝 | 第 19 段，RED 3 个失败，GREEN 800 条通过 |
| R2：设备查询异常外漏 | devices 超时、adb 不存在、查询非零退出码返回 False；清除陈旧状态，CLI 进入退出码 2 通道 | 第 20 段，替身位于 subprocess.run，保留实际 _popen；RED 7 个失败，GREEN 811 条通过 |
| R5：失败查询的部分 stdout 被误判为恢复 | 查询 rc 非零不能证明恢复，也不打印恢复成功日志；原命令最多重试一次 | 第 21 段，RED 2 个失败，GREEN 832 条通过；真实 _popen 恢复/仍掉线/重试又掉线三条序列 |
| R3：POSIX 普通文件绕过原子替换 | Windows 保留名仅在 nt 平台识别；os.devnull 保持直写 | 第 22 段，RED 4 个失败，GREEN 841 条通过；Windows/POSIX 纯分类分支模拟 |
| R4：visible 写失败用例实际提前输入失败 | 独立 fixture 含有效 screen，spy 证明到达输出边界；三命令均有成功/失败对照 | 第 15 段，RED 1 个输出调用计数失败，GREEN 864 条通过 |
| 已有文件的失败原子性覆盖缺口 | 部分写入和替换失败均保留旧文件完整字节并清理临时文件 | 第 23 段，已有实现保证直接加入有效回归，未伪造 RED、未改原子写实现 |

## 最终验证

所有离线检查使用项目 `.venv`、`PYTHONUTF8=1`，从仓库根目录运行。

| 检查 | 实际结果 |
|---|---|
| `python -m py_compile`：main.py、tvuitree/tests 所有 Python 文件 | 退出码 0 |
| 同范围 `python -m pyflakes` | 退出码 0 |
| `python tests/selftest_tree.py` | 退出码 0，864 条断言通过；基线为 790 条 |
| `git diff --check` | 退出码 0 |
| `python main.py --help` | 退出码 0 |
| `python main.py tree --prune-list` | 退出码 0 |
| 金样本轮 baseline/final | 文件集合相同，19/19 文件原始字节一致；每条生成命令记录 rc=0 |
| config 哈希及 HEAD | 均未变化 |
| Windows 编码兼容回归 | 关闭 UTF-8 模式、未设 PYTHONIOENCODING，以及显式 GBK 父进程，两次完整自检均退出码 0、864 条通过 |
| 实际 MCP stdio | SDK 启动真实服务器，initialize 与 list_tools 通过，发现 6 个工具；get_visible(no_connect=True) 返回既有中文连接错误，恰好一个 stderr timing 块，无 traceback |
| 真机 | 当前目标未在 devices 中出现，connect 5 秒探测超时；未采集 full JSON、截图或验证真机恢复 |

真实 MCP 检查仅证明协议及本次不可达设备的错误路径。成功采集路径、截图和真实掉线恢复未在本轮真机验证；原有第 8 段接口/timing 回归及第 21 段恢复链替身属于离线验证。

## 金样基线说明

旧 `_temp/golden/base` 在本轮动手前已有 10 个文本文件差异。本轮逐项核对同名输出：JSON/PNG 原始字节相同；文本差异限定为 GBK/UTF-8 编码、五处既有 stdout 字节计数及两个 GBK 不可编码字符。计数归一仅应用于指定输出诊断行，没有全局忽略数字差异；其余 stdout/stderr 内容必须相同。

据此，在改生产代码前生成独立当前 baseline，结束后生成 final，再严格比较每个文件原始字节。未覆盖旧 base/now，未运行 make，未以旧工具宽松归一作为本轮通过依据。

## 执行决策与限制

1. 在获批计划指定的当前目录顺序实施，保留原有未提交文档；代价是同一工作树存在归档与补修差异，以状态快照和文件边界区分。
2. 使用计划指定的 ignored `_temp/plan-evidence` 留存 ledger 和日志，未引入技能包装目录/提交区间脚本；代价是进度手工核对，各任务均有 RED/GREEN 证据。
3. 金样使用新 baseline/final 目录，保留旧产物；代价是增加本地证据文件。
4. unittest.mock.patch 在 T2 首次使用时导入，而非 T0；提前导入导致 pyflakes 未使用错误，调整后检查全绿，行为无代价。
5. 依照计划不自动提交，保留实施证据；技能的“提交后删除工作目录”条件未成立，证据不删除。后续提交需按文件/差异块区分此前归档变更。

独立终审的四项未判定行为已逐项裁定：初始连接成员判据、其他组件解析函数保持既有语义；不扩展审查至本轮未改生产模块的全部风险；真机与实际 POSIX 保持未验证状态。具体行为及代价见终审记录，未以计划排除为由声称这些边界已安全或通过。

终审唯一 Important 是新测试按 UTF-8 解码却未控制子进程编码。在 GBK 环境完整自检先出现 3 个失败，随后仅为这一组测试子进程指定 PYTHONIOENCODING=utf-8；生产 console 不变。最终全套检查与两种 GBK 父进程检查均通过。审查者原结论 With fixes，后续闭环由主实施者验证，没有虚构第二次 APPROVE。

Windows/POSIX 设备分类分支已模拟验证；本机是 Windows，真正 POSIX 文件系统上的 NUL/CON.json 原子写用例未运行，不能称作 Linux 实机测试。指定 serial 的初始 connect 成员判据沿用既有语义，未扩展成状态列检查，计划明确将该行为变更排除在本轮之外。config 追踪策略也不在本轮范围内。

## 本地证据

日志、JSON、金样和临时脚本集中在 [_temp 执行证据](../../_temp/plan-evidence/remediation-follow-up-20261003/)，不随仓库交付。主要文件为 `progress.md`、各任务 RED/GREEN 日志、`final-fixed-results.json`、`final-boundaries.json`、`final-encoding-red.log`、`final-encoding-green.json`、`legacy-audit.json`、`device-probe.json`、`mcp-protocol.json` 及 `baseline/`、`final/`。本报告包含结论和限制，无需本地证据也可独立阅读。
