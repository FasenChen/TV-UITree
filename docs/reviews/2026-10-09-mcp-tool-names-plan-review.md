# MCP 工具命名 Ponytail 计划审核

日期：2026-10-09。审核对象：[实施计划](../superpowers/plans/2026-10-09-mcp-tool-names.md)。独立只读审核。

## 结论

通过，无阻塞问题，可以实施。改动仅将 `observe_tv` 改为 `get_screen_summary`、`get_visible` 改为 `get_visible_controls`，同步直接消费者，不增加兼容层。

## 核对范围

- MCP 入口、计时头、测试中的直接调用及工具 schema。
- 基准 CASES、仅 a11y 摘要案例和日志测试。
- `collect_tv_scene.py` 三处按名称读取结果。
- 当前说明文档与历史验收报告的范围区分。
- CLI、参数、默认值、业务返回与设备配置保持原契约。

## 验证补充

除输入 schema 外，实施验证同时比较 FastMCP 提供的 `outputSchema` 与基线。该项不是阻塞问题。

本阶段未运行测试或真机。直接移除旧名会使旧调用失效，README 必须提示迁移并刷新工具列表。
