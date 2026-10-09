# USB ADB 支持独立代码终审

**本次变更：** CLI、五个 MCP 读取工具、默认设备配置及 MCP 压测入口增加 USB `serial`。目标选择和保存规则集中在现有应用层连接服务；设备状态检查、采集、截图及按键执行继续使用原有实现。

**审核结论：先修复问题 1，再交付。** 离线回归全部通过，但独立边界复现发现含 NUL 的 serial 可写入配置并导致 CLI 非受控异常。本结论不代表 USB 真机采集已经验收。

**实施方后续状态：** 问题 1 已按 RED→GREEN 补修，最终网络/USB-only 两套自检各 1255 条通过；关闭证据见 [交付报告](../reports/2026-10-09-usb-adb-delivery.md)。以下保留原始独立审核结论与发现，不表示 reviewer 已对补修再次验收。

## 审核范围

审核基线为 `main` 的 `c5f96fb`，对象为 USB 支持的未提交差异。检查了 `application/connection.py`、CLI 共用连接参数及所有实时调用方、五个读取 MCP 工具和默认设备工具、`scripts/bench_mcp.py`、自检与文档差异；同时追踪 `Adb`、`device_config`、`snapshot`、`uiautomator`、观察服务、截图和输入服务的实际调用契约。

按本地单用户 CLI、stdio MCP 和串行压测的现有规模判断。用户已有 `config.json` 差异排除在审查之外；未输出设备值，未修改真实配置，未修改生产代码，未提交或推送。

## 关键核对结果

1. **目标选择一致。** 显式 USB 使用完整 serial，不拼接端口；配置 USB 不要求 IP/port。显式 IP 或 port 能覆盖配置 serial，显式 USB 与网络参数混用在共享服务中拒绝。空 serial 报错，缺失或 null 沿用网络配置。
2. **指定目标不会被替换。** `Adb.connect()` 仅接受设备列表中同一 serial 且状态为 `device` 的条目。offline、unauthorized 或缺失时，即便另有在线设备也返回连接失败；USB 不进入带冒号的网络 connect 或重连分支。后续 ADB 命令继续使用同一 `-s` 参数。
3. **配置写入保留契约。** USB 保存只增加 serial，保留原网络及其他字段；切回网络删除 serial，省略端口保留原端口。已覆盖的无目标、仅端口、非法输入及混合目标在保存前拒绝，MCP 写参数保持 strict，但 NUL 校验存在下述缺口。继续复用同目录临时文件与原子替换，失败时原配置字节不变，网络与 USB 的 previous/current 形状符合计划。
4. **调用方完整接入。** observe、tree、visible、input、shot 共用参数解析，MCP 五个读取工具均传递 serial；采集把 `device.serial` 继续传到 uiautomator2，截图及按键使用同一 Adb 实例。检查了本地安装的 uiautomator2 `connect()` 和设备等待实现，显式 serial 始终用于同名设备匹配，不会改选其他设备。
5. **MCP 与压测保持边界。** serial 追加到旧读取签名末尾，保留位置参数顺序、原返回结构及现有计时上下文。CLI 诊断仍写 stderr，USB 排查提示对应数据线、调试授权和状态。压测在入口选择 USB 或网络参数集合，场景检查、直接截图与 MCP 调用复用该集合。
6. **实现范围适当。** 没有增加依赖、USB 适配层、自动设备选择或重试机制。新增校验、目标分支和接口透传均对应已确认需求。离线 visible 比较排除两次实时采集的 captured_at 与既有比较辅助函数一致，仍保留其余输出的完整比较。

## 必须修复

1. **含 NUL 的 serial 可保存并使 CLI 抛出未捕获异常**（`tvuitree/application/connection.py:39`）
   - **职责：** `_check_serial()` 是连接参数和默认设备保存共同使用的 USB 输入校验。
   - **问题：** `"USB\u0000FIXTURE"` 是合法 JSON 字符串，但 NUL 既不是空白也不是冒号，因此当前校验接受它。保存工具会写入此值；下一次 CLI 连接把它传给 subprocess，产生未捕获的 `ValueError: embedded null character`，违背非法目标不保存和连接错误受控退出的约定。
   - **最小修复：** 在 `_check_serial()` 中明确拒绝 `"\x00"`，无需另增校验层。补充含 NUL 的连接参数、配置默认值、保存字节不变和 CLI 受控退出回归。
   - **不修复的后果：** MCP 默认设备写入可保存无法执行的目标；后续默认 CLI 调用出现 traceback 并退出 1，用户必须手动修改配置才能恢复。

该问题已独立复现：仅替换配置加载及保存函数，使用脱敏 serial；共享参数构造接受 NUL，保存函数被调用，`connect_for_cli()` 漏出上述 ValueError。未访问真实设备或写入真实配置。

## 独立执行的验证

- `.\.venv\Scripts\python.exe -X utf8 tests/selftest_tree.py`：退出 0，1246 条断言全部成立，日志为 `_temp/usb_adb/final-review-suite.log`。覆盖 USB/网络优先级、USB-only 配置、非法目标、准确状态匹配、CLI/MCP 透传、配置保存与失败保留、uiautomator2 参数和压测入口目标锁定。
- `.venv` 的 `py_compile` 和 `pyflakes`：覆盖 `main.py`、`tvuitree/`、`tests/` 及修改的 `scripts/bench_mcp.py`，均退出 0。
- `main.py --help`、`main.py tree --prune-list`、`main.py observe --help`、`scripts/bench_mcp.py --help`：均退出 0，日志保存于忽略的 `_temp/usb_adb/final-review-*.log`。
- `git diff --check -- . ':!config.json'`：退出 0。Git 的 LF/CRLF 提示不属于差异错误。

另外阅读了实施阶段的真实 stdio 校验脚本与 stderr 证据，确认检查对象包含六个 serial schema 和三个受控连接错误；本次终审未重新执行该脚本。离线 suite 中独立执行了 FastMCP 注册及 call_tool 路径，配置写入使用临时文件和脱敏目标。

**审核裁定：先修复问题 1，再交付。**

未执行 USB 真机采集或实际发送按键；实施阶段报告当前没有可用 USB 目标，本次未重新枚举设备或额外连接网络 TV。USB 驱动、电视调试接口与授权、真实 uiautomator2 采集及截图仍未验收。
