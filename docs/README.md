# 项目文档索引

项目使用说明见 [根目录 README](../README.md)，编码与交付约定见 [AGENTS.md](../AGENTS.md)。长期维护的说明、计划、审查与交付报告统一存放在 `docs/`。

## 全项目复杂度审查

| 文档 | 用途及状态 |
|---|---|
| [Ponytail 全项目复杂度审查（2026-10-05）](reviews/2026-10-05-ponytail-audit.md) | 针对 a220fc2 的复杂度审查，列出 7 项删除或简化建议；1087 条基线自检通过；建议尚未实施 |
| [Ponytail 审查复核（2026-10-05）](reviews/2026-10-05-ponytail-audit-review.md) | 复核确认 7 项均有依据，修订截图替换方式，明确遍历顺序、测试迁移及接口边界；代码未修改 |
| [Ponytail 清理实施计划](superpowers/plans/2026-10-05-ponytail-cleanup.md) | 隔离 worktree 的 4 项实施已完成，1140 条自检通过；独立终审完成，代码已分阶段提交，用户已授权发布与合并 |
| [Ponytail 清理交付与验证](reports/2026-10-05-ponytail-cleanup-delivery.md) | 7 项建议的实施、分阶段验证和执行裁定；无生产代码终审问题，索引缺陷已修复 |
| [Ponytail 清理独立终审](reviews/2026-10-05-ponytail-cleanup-final-review.md) | 独立核对 5 类 Review Focus；唯一文档导航问题已修复，仓外调用、真机与性能测量边界保留 |

## 代码评审整改（2026-10-02 至 2026-10-03）

| 文档 | 用途及状态 |
|---|---|
| [OpenCode 原整改计划](superpowers/plans/2026-10-02-code-review-remediation.md) | Zcode 交付记录声明采用的执行依据，已归档；保留历史文本，不表示其所有步骤经过 Codex 认可 |
| [Codex 对原计划的评审](reviews/2026-10-02-code-review-remediation-review.md) | 实施前评审，列出 12 个问题及修正建议；不代表对整改后代码的评审 |
| [Codex 修订的 Zcode 交接计划](superpowers/plans/2026-10-03-code-review-remediation-zcode.md) | 后续修订方案；与原计划范围和步骤不同，不能把原计划的执行结果视为本计划全部完成 |
| [Zcode 整改交付记录](reports/2026-10-03-code-review-remediation-delivery.md) | Zcode 声明的提交 `6d174cd..45064d0`、验证和遗留事项；归档时未重新审核代码或复跑测试 |
| [Codex 整改代码复审](reviews/2026-10-03-zcode-remediation-code-review.md) | 后续独立复跑 790 条自检并检查边界，确认部分修复有效，仍发现 R1–R5；不能接受全部关闭的整体结论 |
| [Codex 复审补修计划](superpowers/plans/2026-10-03-remediation-follow-up.md) | 针对当前代码的 R1–R5 修复与永久回归计划，执行方式已选为 Codex 本会话顺序实施 |
| [Codex 复审补修交付报告](reports/2026-10-03-remediation-follow-up-delivery.md) | R1–R5 的本轮补修、864 条自检及 19 个金样精确对比；真实 MCP 错误路径通过，TV 不可达 |
| [Codex 补修独立终审](reviews/2026-10-03-remediation-follow-up-final-review.md) | 独立终审发现一项测试编码问题，已按 RED→GREEN 闭环；保留明确的未验证边界 |
| [当前代码质量与架构评审](reviews/2026-10-03-current-code-quality-and-architecture.md) | 针对 c5eb108 的整体只读审查；架构适合现有规模，列出观测语义和边界处理问题，尚未实施修复 |
| [观测质量补修计划（Codex 执行）](superpowers/plans/2026-10-03-code-quality-remediation-deepseek.md) | Q1–Q9 的三批、十任务执行依据；原 DeepSeek 交接版后改由 Codex 在隔离 worktree 实施，附执行记录 |
| [观测质量补修交付](reports/2026-10-03-code-quality-remediation-delivery.md) | Q1–Q9 与终审补修、1087 条自检、金样差异、MCP 协议与真机验证边界；已分批提交至隔离分支；尚未合并 |
| [观测质量补修独立终审](reviews/2026-10-04-code-quality-remediation-final-review.md) | 一次独立终审发现稀疏焦点坐标缺陷，已按 RED→GREEN 关闭；原结论及范围裁定保留 |

## 注释、命名与结构清理

| 文档 | 用途 |
|---|---|
| [清理计划及执行记录](superpowers/plans/2026-10-02-comment-naming-structure.md) | 前一轮清理的计划与记录 |
| [前一轮真机验证报告](reports/2026-10-02-comment-naming-structure-tv-validation.md) | 2026-10-02 的历史验证结果，与后续 Zcode 整改区间分开阅读 |

## 使用指南和其他计划

- [MCP Inspector 通用使用指南](MCP_Inspector_通用使用指南.md)
- [MCP 工具耗时计划](superpowers/plans/2026-09-29-mcp-tool-timing.md)
- [截图压测计划](superpowers/plans/2026-09-30-screencap-bench.md)
- [默认设备配置计划](superpowers/plans/2026-09-30-set-default-device.md)

## 存放约定

| 目录 | 内容 |
|---|---|
| `docs/` | 长期使用的指南及文档索引 |
| `docs/superpowers/plans/` | 带日期的实施计划，沿用项目既有位置 |
| `docs/reviews/` | 带日期和审查对象的评审报告 |
| `docs/reports/` | 带日期和验证范围的交付、验收报告 |
| `_temp/` | 原始设备捕获、JSON、PNG、执行日志、金样、临时验证脚本及本地证据；不提交 |
| `.omo/` | 工具恢复状态和内部草稿；正式计划以 docs 中的归档为入口 |

长期报告可以链接本地 `_temp` 证据，但必须说明这些文件不随仓库提供；报告的结论、范围和未完成事项应能独立阅读。不要把设备地址、截图、账号信息或敏感运行输出随文档归档。已经转移的报告在旧路径保留简短跳转说明，以兼容历史引用。

文档归档阶段只整理资料，APPROVE 等状态来自对应历史交付声明。后续独立代码复审发现的 R1–R5 已完成本轮补修，实际验证和限制以最新补修交付报告为准；当前 TV 不可达，尚未补做本轮真机 QA。
