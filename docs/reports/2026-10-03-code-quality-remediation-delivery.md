# 观测质量与边界补修交付（2026-10-04 终验）

Q1–Q9 已修复，并关闭独立终审发现的稀疏焦点坐标边界；最终 1087 条离线断言通过。集中终审为 With fixes，1 项 Important 已用 RED→GREEN 闭环，无待处理 Critical/Important/Minor。实现保留原四层架构和 full JSON 投影流程，不新增依赖、工具或 schema 版本。

依据：[当前 Q1–Q9 评审](../reviews/2026-10-03-current-code-quality-and-architecture.md)、[实施计划与执行记录](../superpowers/plans/2026-10-03-code-quality-remediation-deepseek.md)、[AGENTS.md](../../AGENTS.md)。

## 范围与工作区

- 用户将执行者从 DeepSeek 改为 Codex，并选择隔离的托管 worktree。
- 分支：`codex/code-quality-remediation`；实现验收时基线与 HEAD 均为 `c5eb108494b8a221eba0cf5074bd162c6676cf28`。当时实现为本分支未提交差异，独立审查绑定该 diff。用户随后授权推送，当前提交清单见下方。
- 原仓库 main 的生产代码和配置保持原状态；原有 docs 索引、计划、评审和本地工具状态保留。
- 实现验收阶段未提交或推送；2026-10-04 用户授权提交并推送本隔离分支。没有合并或历史改写，个人设备配置不进入本次差异。最终配置哈希复核见验收记录。

## 缺陷、修复与验证

每项先写行为回归并观察完整自检正常汇总的失败，再实现并运行 compile/pyflakes/完整自检/diff check。未删除原有效断言，原 EXP 常量没有为了取绿而调整。

| 问题 | 实际行为变化 | tests/selftest_tree.py 分组 | GREEN 总断言数 |
|---|---|---|---|
| Q1 | R1 先建静态候选图，再仅绑定双方候选均唯一的边；歧义不随遍历被抢占 | 24 / T1 | 869 |
| Q2 | 明确 enabled=False 保留；缺失/None 不转为 False；CLI/MCP 共享结果 | 25 / T2 | 890 |
| Q3 | 子矩形与父容器的 0,0,width,height 局部范围比较；只改告警，不改绘图 | 26 / T3 | 898 |
| Q4 | 损坏主源 XML 抛 ValueError，CLI 返回 3、MCP 返回 error；合法空 hierarchy 仍合法 | 27 / T4 | 907 |
| Q6 | 文件入口复用 domain 的纯结构校验，非法嵌套结构受控拒绝；保留稀疏字段和未知字段 | 28 / T5 | 993 |
| Q7 | 初始连接与恢复共用 device 状态判据；不可用状态拒绝、多设备不猜、失败不抢 serial | 29 / T6 | 1024 |
| Q5 | input/shot 实际外部失败返回 1；连接失败仍为 2；合法带时区时间正常处理 | 30 / T7 | 1035 |
| Q8 | CLI 在连接前、API 在第一条发送前验证完整序列；非法语法无部分按键副作用 | 31 / T8 | 1052 |
| Q9 | 无标签但明确可操作/可勾选的可见控件保留；checked=False 与禁用读数保留 | 32 / T9 | 1079 |

T2/T9 的离线接口测试替换共享 full JSON 采集入口及其 MCP 导入引用，真实 CLI/MCP 投影和 timing 运行。T4 则替换基础 snapshot 边界，证明解析失败传播到实际接口。这些替身不代表真实设备验证。

## 金样差异

动代码前，从既有离线素材在本轮独立目录生成 baseline；最终生成 final。没有覆盖旧 base/now，没有运行旧 make。现有生成器仅归一输出目录及截图年龄，此次没有新增归一规则。

19 个生成文件中 16 个逐字节相同，3 个差异均逐项核对：

1. `rebuilt_full.json`：唯一 JSON 路径差异是 `align_rules.R1` 从“候选唯一”改成“双向候选唯一”；其余重建内容相同。
2. `shot_all.txt`：祖先链告警由 77 降为 72，并使用统一父局部范围说明。正常图形、绘制数量和裁剪提示不变。
3. `shot_actionable.txt`：告警总数仍为 9，错误地标为溢出的非原点父子关系改为继续检查真正溢出的祖先，并同步说明文字。

三张 PNG 逐字节一致；observe/visible/slim JSON 等其他结果一致。此素材没有覆盖每一种新行为，歧义、disabled、无标签 Switch 等由新增回归独立验证，不能把金样等效当成所有新功能覆盖。

## 验收和限制

- 项目现有 `.venv`，未升级或重建；每个任务 GREEN 均通过 py_compile、pyflakes、完整自检和 git diff --check。
- 全量自检从 864 增至 1087 条（九项任务为 1079，独立终审补修增加 8 条）。额外在 PYTHONUTF8=0 的默认父进程、显式 GBK 父进程分别通过完整自检。
- 真实 `main.py mcp` stdio 服务经现有 MCP SDK 客户端完成 initialize、六工具 tools/list、get_visible 连接错误结果，以及 stderr 恰好一个 timing 块检查。使用明确不存在的 adb 路径，不访问 TV。
- MCP 成功采集投影由离线接口夹具验证；本轮没有声称真实 stdio 设备采集成功、长期压力或 Inspector UI 通过。
- 短时 adb devices 查询未发现配置目标处于 device 状态，未执行实时采集、真实按键或掉线实验；真机成功路径待设备可达。
- 最终 help/prune-list、文档相对链接、配置 SHA256 复核全部通过；两份配置和动手前哈希一致。
- [独立终审记录及发现闭环](../reviews/2026-10-04-code-quality-remediation-final-review.md)：第 33 组实际 JSON+PNG CLI 回归先正常失败 6 项，再全部通过；缺失焦点坐标明确报告未知。
- 终审补修后另建 post-review 输出，19 文件与补修前 final 全部精确相同；本轮 baseline 的三项有意差异仍是上节列出的范围。

## 执行裁定

1. 复用原项目虚拟环境，并仅复制本地离线素材和配置进入 worktree；不按通用初始化建议重新安装。误判风险是 Python 子进程根路径不同；已用隔离工作区完整自检及实际 stdio 启动验证。
2. Windows 使用本计划专属 ignored `_temp` 证据目录和 Python/PowerShell task runner，替代 Bash SDD 辅助脚本；保留逐项 RED/GREEN 和账本。误判风险是遗漏步骤；通过任务映射与集中终审核对。
3. 实现验收时授权不包含提交/推送/合并，因此保留证据和 worktree；后续用户已授权提交与推送，仍不自动合并。误判风险是只读 HEAD 比较看不到实现；审查使用未提交 diff 及文件哈希绑定。

## 终审及裁定补充

独立审查绑定补修前未提交差异，确认 Q1–Q9 主案例和五项 Review Focus；执行者按实际影响将稀疏焦点截图问题判为 Important，并完成唯一一次修复 pass，没有请求复审或伪造补修后的代理 APPROVE。闭环后最终结果为 1087 条，原报告中的各任务 GREEN 数仍保留历史值。

审查者未判定的真机、多窗口、长期并发/Inspector/新依赖、完整 metadata 重构及 XML 属性缺失策略，均有范围理由与风险，逐项见独立终审报告；不把未验证行为当作通过。无审查待办 Minor。

## 用户授权后的提交交付（2026-10-04）

本轮按三批修复、独立终审补修、文档归档分别提交，均使用 `类型(模块): 说明`。共享 selftest、output 和 screenshot 的差异块精确暂存，没有把后续变化混入早期提交。每个代码提交均在独立暂存快照运行 compile、pyflakes 和完整 selftest：

| 提交 | 内容 | 快照断言数 |
|---|---|---|
| `21bbf69` | fix(observation): 修复匹配歧义、禁用读数与采集诊断 | 907 |
| `9cec5c7` | fix(boundaries): 校验设备与输入并统一运行错误出口 | 1052 |
| `38a09d8` | fix(visible): 保留无标签控件及明确开关状态 | 1079 |
| `5165e38` | fix(screenshot): 明确报告焦点坐标缺失 | 1087 |

代码终值提交为 `5165e38b6ecec6f7e19a4fcaa199dd1197df59f7`；README 与正式计划/评审/交付报告另作 `docs(quality)` 提交。远程目标为 FasenChen/TV-UITree 的 `codex/code-quality-remediation`，PR 目标为 `main`，本轮不自动合并。远程推送及 PR 结果以实际分支/PR 状态为准。

## 本地证据索引

执行账本、每任务完整 RED/GREEN 日志、新金样和差异、设备探测、协议与编码日志位于本 worktree 的 ignored `_temp/plan-evidence/code-quality-remediation-20261003/`。它们不随仓库提供；以上结论、触发条件和限制不依赖这些文件才能理解。正式报告不归档设备地址、原始截图或敏感运行输出。
