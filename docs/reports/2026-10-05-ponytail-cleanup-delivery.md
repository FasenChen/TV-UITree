# Ponytail 清理交付与验证

日期：2026-10-05。基线：`a220fc2d8a2636669333e344d146fb33d25ce1a0`。依据：[审查复核](../reviews/2026-10-05-ponytail-audit-review.md)和[实施计划](../superpowers/plans/2026-10-05-ponytail-cleanup.md)。

## 交付状态

4 项实施任务已完成，7 条原审查建议全部落地。代码与测试在 Codex 管理的隔离 worktree 完成实施，隔离执行阶段未改动原 `D:\Code\tv-uitree` 的生产代码。用户随后授权提交、推送并合并到 main；4 个代码阶段已分别提交到 `codex/ponytail-cleanup`，提交记录见后文。依赖和配置未修改。

工作位置：`C:\Users\FashionChen\.codex\worktrees\ponytail-cleanup\tv-uitree`。

独立终审已完成：未发现生产代码问题；唯一文档索引缺陷已修复。详细结果见[独立终审报告](../reviews/2026-10-05-ponytail-cleanup-final-review.md)。

## 修改结果

| 原建议 | 实施结果与保留边界 |
|---|---|
| 1 | 删除 A11Y_ATTRS、Node.label、U2Node.bounds_str、domain.screenshot.walk。保留实际使用的 Node.bounds_str、short_cls 和 JsonNode.label |
| 2 | align 的几何统计调用 geom_of，删除 pred_noscreen 和第二套条件。R1 的 pred、R0–R3 和插入规则保持原样 |
| 3 | 删除 node_summary 的 include_children 选项和页面 included_paths 集合。保留孩子数量、焦点上下文、各树位置、顺序、上限、回退及截断 |
| 4 | 删除 image.load_tree 和 import json。第 7 组成功读取与 6 类非法输入迁移到 json_io.load_full_json，提前导入实际入口；校验和 CLI 退出行为保持原样 |
| 5 | u2_all 返回 list(iter_nodes(roots))；iter_nodes 类型接受 Node/U2Node；裁剪主体直接使用 clip_to_chain。保留多根逆序、孩子原序 |
| 6 | draw_boxes_png 使用 BytesIO，两个公开入口共用私有 _draw_boxes。文件入口继续按扩展名保存，字节入口显式 PNG；缺 Pillow 返回原图及原提示。绘图主体及 MCP 最终落盘/计时逻辑不改 |
| 7 | 删除 build_unified.view_roots、parse_node_line.indent、tree._summary.out_path，并更新全部仓内调用和旧签名断言。parse_dumpsys_top 缩进与告警、build_full_json 的既有签名保留 |

生产代码净减少 59 行（38 行新增、97 行删除），测试净增加 115 行；仅陈述实际差异，不作为验收指标，也不宣称性能提升。

## 实际验证

所有命令在隔离 worktree 根目录执行，使用原项目的 `D:\Code\tv-uitree\.venv\Scripts\python.exe`，无需安装或重建环境。

| 阶段 | 完整 selftest 结果 | 其他验证 |
|---|---|---|
| 原目录准备基线 | 1087 条全部通过，退出 0 | help、tree --prune-list、git diff --check 退出 0 |
| 隔离目录基线 | 1087 条全部通过，退出 0 | 确认原 HEAD 和隔离状态 |
| 任务 1：先补保护断言，再清理 | 前后均 1100 条通过，退出 0 | py_compile、pyflakes、git diff --check 退出 0 |
| 任务 2：先补几何/遍历断言，再重构 | 前后均 1128 条通过，退出 0 | py_compile、pyflakes、git diff --check 退出 0 |
| 任务 3：迁移加载测试，再删除旧入口 | 前后均 1128 条通过，退出 0 | py_compile、pyflakes、git diff --check 退出 0 |
| 任务 4 RED | 1139 条中只有“字节画框不需要创建临时目录”失败，退出 1 | 失败原因为注入的临时目录创建错误，格式与回退断言均通过 |
| 任务 4 GREEN | **1140 条全部通过，退出 0** | py_compile、pyflakes、git diff --check 退出 0 |
| 最终 CLI 检查 | help、tree --prune-list 均退出 0 | 未重复无变更的整套自检 |

新增 53 条行为断言，覆盖重复树位置/上限/焦点上下文、几何四档/多根顺序、PNG 字节与像素、JPEG 格式、缺 Pillow、非法 PNG 和移除临时目录。旧 EXP_* 未修改，旧错误输入断言未删。完整自检中的 MCP 图像、文件保存与 timing stages 测试通过。

本次未进行真实 TV/ADB 集成验证。结果证明离线契约和替身集成通过，不代表真机画面已验证；没有向设备发送输入。

原始日志、逐任务差异快照和进度 ledger 留在该计划的 ignored 技能工作目录，不随报告提交。交付结论无需读取这些临时文件即可理解。

## 独立终审与文档验证

独立审查者核对全部 5 类 Review Focus 和当前差异，未发现生产逻辑或测试契约问题。发现索引将计划与交付记录拼成一行，导致交付报告链接不可见；已拆成独立行，临时文档校验由失败转为通过，全部本轮文档的路径、链接、空白和表格入口检查通过。没有延后 Minor 项。仅文档修复，无需重跑应用测试。

## 执行裁定与限制

1. 任务 1–3 按已审阅计划采用先通过的行为保护断言；纯删除和等价重构没有制造人为 RED。任务 4 的新 I/O 要求完整执行 RED→GREEN。代价是前者的有效性依赖现有真实契约覆盖和独立终审。
2. 实施及终审阶段尚未授权提交，使用逐任务差异快照记录检查点并保留未提交差异。用户随后授权推送并合并到 main，按快照重建四个经过验证的阶段提交；记录保留这一先审查、后提交的过程。
3. 标准 review-package 脚本要求非空已提交范围，而本轮 HEAD 未变；终审改用对基线的完整工作区差异及当前文件，明确包含全部代码/测试和未跟踪文档，避免零范围漏审。代价是评审人同时核对实际工作区与差异包。

4. 文档索引问题原审查等级为 Minor；实施者按交付导航不可见的实际影响纳入必要修复，完成一次文档校验失败到通过，不改代码或新增持久测试。代价是修复结论由实施者检查，独立审查意见的原始分级仍保留。

仓外直接导入已删除内部符号的调用未检查；不新增推测性旧签名兼容层。公开包入口、CLI/MCP JSON 和截图两个公开签名保持不变。

## 推送与 main 整合交接

用户于 2026-10-05 明确授权推送并合并到 main。目标为 `FasenChen/TV-UITree` 的 `main`，来源分支为 `codex/ponytail-cleanup`；首次发布前核对远端 main 与基线 a220fc2 一致，不执行强制推送。

| 阶段 | 提交 |
|---|---|
| 摘要及闲置代码清理 | d0801db，refactor(summary): 删除闲置属性与摘要选项 |
| 几何与遍历统一 | bce9f05，refactor(tree): 统一几何分级与节点遍历 |
| 删除重复加载器 | 1799615，refactor(image): 移除重复 JSON 加载入口 |
| 内存 PNG 渲染 | 04e1e2c，refactor(image): 使用内存缓冲渲染 PNG |

文档另行归档提交，纳入同一 PR。发布前完整自检 1140 条通过，py_compile、pyflakes、help、tree --prune-list 和 git diff --check 均退出 0。远端是否已合并以及合并 SHA 以 GitHub PR 和 origin/main 的实际记录为准，不将发布授权当作合并结果。
