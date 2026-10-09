# MCP 工具命名 Ponytail 代码终审

日期：2026-10-09。审核范围：[实施计划](../superpowers/plans/2026-10-09-mcp-tool-names.md)及本轮相对 `_temp/tool-rename-baseline/` 的增量，排除原有 USB ADB 修改。独立只读审核。

## 结论

通过，无阻塞或应修复问题。两处工具名称、计时、基准案例、场景消费者、测试及当前文档同步完整，未增加兼容层。

## 独立证据

- 复跑 `tests/selftest_tree.py`：1256 条断言全部通过。
- 复跑 `tests/selftest_bench_mcp.py`：通过。
- `git diff --check`：通过。
- 用 Python AST 对比修改前基线与现行 MCP 文件：仅将两处函数名和计时字符串规范化后，全文件相等；业务实现、参数和返回未改变。
- 脱敏 records 调用场景报告消费者：新名可提取标签、组件和屏幕信息。
- 基准默认与仅 a11y 案例一致；当前代码和说明中的旧名只保留于 README 迁移提示。

## 边界

独立审核未执行真机与 stdio schema 检查，这两项由主执行者完成，见[交付报告](../reports/2026-10-09-mcp-tool-names-delivery.md)。FastMCP 自动生成的输入 schema 标题随函数名变化是预期元数据变化。

旧名已移除，调用方需迁移并刷新工具列表；README 已明确提示。性能和并发行为沿用原实现，本轮没有新增相关逻辑。
