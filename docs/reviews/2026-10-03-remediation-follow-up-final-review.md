# 复审补修独立终审及问题闭环

日期：2026-10-03。审查对象：HEAD `45064d04053990c67c87a90104b6a4f660b5d66a` 到本轮未提交工作树的差异。依据：[补修计划](../superpowers/plans/2026-10-03-remediation-follow-up.md)、[R1–R5 代码复审](2026-10-03-zcode-remediation-code-review.md)。

由独立新上下文审查者只读检查全部生产补修、回归测试、交付报告及执行裁定。终审发现 Critical 0 项、Important 1 项、Minor 0 项，原始结论为 **With fixes**。唯一重要问题随后由主实施者按 RED→GREEN 修复并完成全套检查；未安排重复终审，不将主实施者验证表述为审查者再次 APPROVE。

## 已核实的改动

- R1–R5 的生产差异与计划一致，边界限定在窗口组件解析、ADB 查询失败与设备名平台分类。
- 恢复测试保留真实 `_popen`；原子性测试注入部分写入和替换失败；visible 的有效 fixture 与 spy 消除原有测试假阳性。
- 审查者独立比较 19 个金样文件的集合和原始字节，完全相同；读取最终 864 条日志及检查结果，重新运行 diff-check 通过。
- 报告明确 MCP 仅验证真实协议与错误路径；真机及实际 POSIX 文件系统验证未完成。

## Important：测试子进程编码依赖（已修复）

位置：`tests/selftest_tree.py` 第 15 段输出成功/失败对照循环，最终调用位于约 2284 行。

父进程设置 `encoding="utf-8"` 仅决定管道解码，不能改变子进程实际输出编码。生产 `terminal.setup_console` 保留可显示中文的 GBK。关闭 `PYTHONUTF8`、移除 `PYTHONIOENCODING` 时，三个 CLI 正确返回 2，但新增“写不了”断言因错误解码全部失败；标准自检因此依赖外部环境。

主实施者在完整自检中复现 RED：3 个失败 / 864 条。最小修复仅给这组测试的子进程传入 `env=dict(os.environ, PYTHONIOENCODING="utf-8")`，匹配既有解码设置；不改全局环境或生产终端。

修复后实际验证：

| 环境/检查 | 结果 |
|---|---|
| UTF-8 父进程，全套 compile/pyflakes/selftest/diff-check | 全部退出码 0，864 条通过 |
| `PYTHONUTF8=0`，未设置 PYTHONIOENCODING | 完整自检退出码 0，864 条通过 |
| `PYTHONUTF8=0`，父进程 PYTHONIOENCODING=gbk | 完整自检退出码 0，864 条通过 |

## 审查者未重新判定的行为及实施裁定

| 行为 | 裁定及实际限制 |
|---|---|
| 初始 connect 对指定 serial 仅检查成员资格 | 按明确计划保留既有判据；offline/unauthorized 成员可能仍返回 True，之后由具体命令报告失败。本轮恢复路径的 device 状态检查不等于初始连接语义已更改 |
| activity record 组件解析、normalize_component 的宽松规则 | 不扩展仅窗口路径的修复；这些函数原有宽松输入仍可能被接受，未证明整个组件模块已经严格校验 |
| props、绘图、ADB 搜索路径、config 追踪 | 不扩展本轮复审为新一轮全仓审计；它们本轮无生产差异，其他既有风险未全部重新判定 |
| 真机成功采集/截图/真实恢复与实际 POSIX 文件系统 | 维持未验证记录；设备不可达，本机 Windows。离线替身和分类模拟不能证明现场行为及真实 POSIX 文件系统兼容性 |

没有待处理的 Minor。当前接受本轮补修的依据是独立终审加唯一问题的确定性修复验证；真机和实际 POSIX 验证限制仍存在。完整交付见 [本轮交付报告](../reports/2026-10-03-remediation-follow-up-delivery.md)。
