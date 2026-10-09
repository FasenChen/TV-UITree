# MCP 工具命名实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `observe_tv` 改为 `get_screen_summary`，将 `get_visible` 改为 `get_visible_controls`，使名称明确表达读取对象。

**Architecture:** 直接重命名 MCP 入口函数及其计时名称，同步仓内消费者。继续复用现有应用层服务，不改变采集、筛选、返回结构或 CLI；不注册旧名别名。

**Tech Stack:** Python 3.10+、当前项目 `.venv`、FastMCP（实际安装 mcp 1.30.0）、现有脚本式自检。

**Spec:** 本会话已确认的两处最小命名建议，以及根目录 `AGENTS.md`。

## Global Constraints

- 仅修改两处 MCP 名称及直接消费者，不改其他四个 tool。
- `schema_version`、`mode=observe/visible`、参数、默认值、错误返回、stderr 计时阶段保持原契约。
- CLI `observe`、`visible` 和应用层 `collect_observation`、`collect_visible` 保持原名。
- 保留现有 USB ADB 工作区修改及 `config.json`；不暂存、提交、推送或发布。
- 仅当前使用说明更新名称；历史计划、审核、验收与包含实测数据的 HTML 报告保留当时名称。
- 不新增依赖、兼容别名、迁移选项或封装。

## Review Focus

- MCP `tools/list` 必须仅公开六个预期名称，旧名不再注册。
- 新名调用应保持输入 schema、默认值、业务结果及错误路径，计时头与调用名一致。
- 基准脚本的 case/tool 和日志测试必须一致，包括仅 a11y 的摘要案例。
- `collect_tv_scene.py` 按 tool 名读取的结果必须随之更新，不能生成空摘要。
- 旧调用方需迁移并刷新工具列表；文档必须明示改名与不保留别名。

## Task 1: 同步名称与消费者

**Files:**
- Modify: `tvuitree/interfaces/mcp.py`、`scripts/bench_mcp.py`、`scripts/collect_tv_scene.py`
- Test: `tests/selftest_tree.py`、`tests/selftest_bench_mcp.py`
- Modify: `README.md`、`AGENTS.md`、`docs/bench-mcp.md`、`docs/README.md`
- Create: `docs/reviews/2026-10-09-mcp-tool-names-plan-review.md`、`docs/reviews/2026-10-09-mcp-tool-names-code-review.md`、`docs/reports/2026-10-09-mcp-tool-names-delivery.md`

**Interfaces:**
- Consumes: 现有 MCP 入口与应用层观察服务，当前未提交的 USB ADB 参数契约。
- Produces: `get_screen_summary`、`get_visible_controls`，其余四个工具原名及全部业务字段不变。

- [x] Step 1: 保存受影响文件基线到忽略目录 `_temp/tool-rename-baseline/`，取得独立 Ponytail 计划审核；无阻塞问题继续执行。
- [x] Step 2: 更新现有测试调用与计时名称，在 `mcp_schemas` 构建后增加注册集合断言：

```python
t.eq(set(mcp_schemas), {
    "get_screen_summary", "get_full_tree", "get_visible_controls",
    "get_current_focus", "get_focus_screenshot", "set_default_device",
}, "MCP 仅注册六个现行工具名称，不保留旧名别名")
```

Run: `.\.venv\Scripts\python.exe tests/selftest_tree.py`
Expected: 因生产入口仍为旧名而失败；记录实际错误，不将其作为产品缺陷。

- [x] Step 3: 在明确列出的当前文件中将 `observe_tv` 替换为 `get_screen_summary`，将 `get_visible` 替换为 `get_visible_controls`；包括 `observe_tv_a11y` 案例名。保留返回 `mode`、schema 和 CLI。README 添加迁移提示；不修改历史报告。
- [x] Step 4: 运行完整 `selftest_tree.py`、`selftest_bench_mcp.py`，以及 main/tvuitree/tests/scripts 的 `py_compile`、`pyflakes`、CLI 帮助、裁剪列表、基准脚本帮助和 `git diff --check`。
Expected: 所有命令退出码 0。完整树自检中的替身覆盖 CLI/MCP 结果一致、输入参数、错误、计时和 USB 参数传播。
- [x] Step 5: 使用真实 stdio MCP 会话执行 `tools/list`（不访问 TV）；核对六个名称及两处参数 schema 与基线一致。用最小脱敏 records 检查场景报告摘要提取；核对 `config.json` 字节不变。可用设备存在时执行两处只读采集；不可用则记录原因，不阻塞离线验证。
Expected: 工具集合正确、schema 不变、场景摘要包含样例标签、配置未改变。
- [x] Step 6: 取得独立 Ponytail 代码终审，核对本轮相对基线的增量，归档检查结果并更新 `docs/README.md`。
Expected: 无阻塞问题；明确旧调用方需迁移及真机验证边界。

## 执行记录

- 已保存修改前基线；原有 USB ADB 工作区内容保留。
- 执行裁定：本轮为低影响入口重命名，直接在当前工作区实施并按基线审核；不创建隔离分支或把用户未提交修改纳入提交。风险为旧名调用失效，已在迁移提示及注册检查中明确。
- 独立计划审核通过；补充比较 MCP 输出 schema。
- RED：更新测试后，完整自检在新名 `get_screen_summary` 不存在时以退出码 1 失败。
- GREEN：同步生产入口后，完整自检 1256 条断言全部成立。
- 验证裁定：FastMCP 自动生成的输入 schema `title` 从旧函数名加 `Arguments` 改为新函数名加 `Arguments`；这是工具改名的预期元数据变化。验证要求这两处标题精确改名，其余输入字段、输出 schema 和描述仍与基线逐项相等。不为保留旧标题引入自定义框架逻辑。
- 所有离线、静态、CLI、stdio 注册与消费者检查通过；两处新工具真机调用成功且各一个新名计时块。配置字节未变，具体证据见交付报告。
- 独立代码终审通过；独立复跑 1256 条树自检、基准自检、差异检查，并以 AST 确认 MCP 仅改两处函数名与计时名称。
