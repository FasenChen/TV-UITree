# 独立截图压测脚本精简

## 结果

删除 `scripts/bench_screencap.py`，统一保留 `scripts/bench_mcp.py` 作为 MCP 与直接截图耗时压测入口。原有网络/USB 参数、八个待测项、计时范围、预热与失败统计、报告格式和输出位置保持一致。

`bench_mcp.py` 原先从旧脚本导入 positive_int 和 summarize，后者依赖 percentile。本次将这三个函数原样移入现有脚本，继续使用正整数校验、最近秩分位数和空样本返回 None；新增的 math/Optional 导入均来自 Python 标准库，没有新增模块或依赖。

使用方式保持为：

```powershell
.\.venv\Scripts\python.exe scripts/bench_mcp.py --count 10 --warmup 1
.\.venv\Scripts\python.exe scripts/bench_mcp.py --serial USB_SERIAL --count 2 --warmup 1
```

直接截图仍包含连接检查，并单列 screenshot 阶段用于查看不含连接的截图耗时。旧脚本的多台网络设备连续截图入口、命令和报告生成逻辑随文件删除，不增加兼容入口。

## 测试与文档整理

- 主回归中旧截图脚本专属的 Section 10、设备替身、动态导入及 importlib.util 随被删除入口移除；其余编号保持原样。
- 正整数、最近秩、单样本、乱序样本和空样本的 9 条回归转入 `tests/selftest_bench_mcp.py`，继续覆盖迁移的函数。
- 保留 MCP 压测的日志归属、失败阶段、预热/失败排除、同轮比较、业务错误、报告生成，以及主回归中的 USB/网络压测参数传递检查。
- README 移除旧脚本命令、运行说明和目录条目，改用现有 MCP 压测命令；压测指南同步说明统一入口。
- 文档索引将原截图压测计划标为历史记录；原计划、历史报告和忽略目录中的已有测量数据保持原样。

## 实际验证

| 检查 | 结果 |
|---|---|
| 迁移前 RED | 压测自检改从 bench_mcp 导入 percentile 后失败，确认目标模块尚未具备完整的独立统计实现 |
| 压测离线自检 GREEN | 参数校验、最近秩统计及既有 MCP 压测回归全部通过 |
| 完整项目自检 | 1203 条断言全部通过；此前 1273 条中 70 条属于旧 Section 10，其中 9 条迁入独立压测自检，其余旧入口专属断言随入口移除 |
| 前后 AST 对比 | 原 bench_mcp 的 8 个函数和 CASES 列表完全一致；迁入的 3 个函数与旧实现完全一致 |
| 样本统计前后比较 | 空样本、单样本、乱序样本、负值及四元素样本汇总与旧函数一致 |
| py_compile / pyflakes | main.py、tvuitree、tests 及 bench_mcp.py 通过 |
| bench_mcp.py --help | 退出 0，脚本可独立启动 |
| 活跃引用检查 | scripts、tests、README 和当前压测指南均不再引用已删除脚本 |
| git diff --check | 通过 |
| 本机配置 | SHA-256 与本次精简前一致，保留已有用户修改 |

首次编译检查与自检并行时，Windows 的同名 pycache 写入发生访问拒绝；自检完成后顺序执行编译、静态检查与压测自检，均通过。未为此修改应用逻辑。

本地证据在忽略的 `_temp/remove_screencap_bench/`：迁移前源码、red.log、full-suite.log、帮助输出和配置摘要。报告不归档本机设备地址或序列号。

## 自审与边界

实施方按 Ponytail 做自审，核对全部导入和调用方，并通过函数 AST 一致性检查限制迁移范围；没有发现遗留依赖或阻塞问题。本次未运行真实 TV 压测，因此不声明新的性能数据或真机采集验收。没有暂存、提交、推送或发布；保留任务前的其他工作区修改。
