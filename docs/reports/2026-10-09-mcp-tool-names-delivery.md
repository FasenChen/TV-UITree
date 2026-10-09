# MCP 工具命名交付与验证

日期：2026-10-09。

## 实施结果

- `observe_tv` → `get_screen_summary`。
- `get_visible` → `get_visible_controls`。
- 同步 MCP 计时名称、基准案例及测试、场景报告按名读取、当前 README、AGENTS 和基准指南。
- 其余四个工具、CLI `observe/visible`、应用层 API、参数默认值、返回字段和错误路径保持原契约。
- 不注册旧名别名；README 提示已有调用、提示词和自动化迁移，重启 MCP 服务并刷新客户端工具列表。
- 历史计划、验收文本及已有实测 HTML 保留当时名称。

## 检查与结果

| 检查 | 实际结果 |
|---|---|
| 更新测试后运行 `tests/selftest_tree.py` | RED：新入口尚不存在，退出码 1 |
| 实施后完整 `tests/selftest_tree.py` | 1256 条断言全部成立，退出码 0 |
| `tests/selftest_bench_mcp.py` | 日志、失败、样本统计自检通过，退出码 0 |
| main、tvuitree、tests、scripts 的 `py_compile`、`pyflakes` | 均退出码 0 |
| `main.py --help`、`main.py tree --prune-list`、`scripts/bench_mcp.py --help` | 均退出码 0 |
| 真实 stdio MCP `tools/list` | 六个预期工具，新名已注册，旧名不在集合中 |
| schema 与修改前基线对比 | 参数和输出 schema、描述相同；仅两处自动生成的输入 `title` 精确随函数名改名 |
| 场景报告脱敏样例 | 从新名 records 取出窗口、分辨率、节点计数及文字标签 |
| 真机 `get_screen_summary({})` | 协议及业务成功，`mode=observe`，唯一焦点，31 个摘要节点 |
| 真机 `get_visible_controls({})` | 协议及业务成功，`mode=visible`，唯一焦点，10 个摘要节点 |
| 真机 stderr 计时 | 两次调用各一个对应新名的 timing 块 |
| `config.json` 与基线字节比较 | 完全相同 |
| `git diff --check` | 退出码 0 |
| 独立 Ponytail 代码终审 | 通过；独立复跑两套自检及差异检查，AST 对比确认 MCP 仅改名称与计时 |

全部 Python 验证使用项目 `.venv`，实际 MCP 版本为 1.30.0。真实协议返回的 JSON 可以位于文本内容块；验收复用场景脚本已有解析逻辑，不要求客户端一定提供 `structuredContent`。

## 证据与边界

修改前文件副本、增量差异、自检日志、协议检查脚本和真机 JSON 位于忽略目录 `_temp/`，不随文档归档。报告不记录本机地址或序列号。

本轮真机验证覆盖两处新名称的当前场景读取，不代表全部场景或长时间性能验收。未运行完整真机基准，也未复测其他四个工具的真机行为。未暂存、提交、推送或发布；原有 USB ADB 工作区修改和设备设置保留。
