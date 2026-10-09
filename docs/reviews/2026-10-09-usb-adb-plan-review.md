# USB ADB 实施计划独立审核

**审核对象：** [USB ADB 支持实施计划](../superpowers/plans/2026-10-09-usb-adb.md)。

**结论：通过，可以按计划直接执行。** 未发现必须先修正的计划问题。本结论针对设计和实施范围，不表示尚未实现的代码或 USB 真机验证已经通过。

## 计划带来的行为

CLI、五个 MCP 读取工具及默认设备配置增加可选 `serial`，从 `adb devices` 中选择指定 USB 设备。通过现有应用层连接服务和 ADB 实现完成采集与截图；USB 不执行网络 `adb connect`，指定目标不可用时也不会选用其他在线设备。

## 核对依据

- `tvuitree/application/connection.py` 是连接参数和默认设备写入的共同归属。计划把目标选择、校验和保存都放在这里，避免 CLI、MCP 和压测脚本各自实现优先级。
- `tvuitree/infrastructure/adb.py` 已按 serial 加 `-s`，只对含冒号的网络目标执行 connect 和重连；`connect()` 对明确目标只接受同名且状态为 `device` 的条目。现有实现已经提供 USB 所需边界，计划没有增加适配器、依赖或重试层。
- `tvuitree/infrastructure/uiautomator.py` 的 `fetch_u2()` 接受 serial，`snapshot.py` 和现有 CLI/MCP 都把 `device.serial` 传给采集服务。因此入口增加参数即可接通下游，树、观察摘要、截图坐标和 JSON 字段不需要修改。
- `interfaces/cli.py` 的 observe、tree、visible、input、shot 均复用 `add_conn_args()`。计划覆盖这些入口和统一错误提示，保留现有退出码。
- `interfaces/mcp.py` 五个读取工具均调用 `_connect()`，默认设备工具调用 `update_default_device()`。计划在旧签名末尾追加读取参数，并保留 `tool_timing`、配置写入 strict 校验与错误返回结构。
- `scripts/bench_mcp.py` 在主入口解析目标后，场景读数、直接截图和 MCP 调用复用同一 `arguments`。计划生成 USB 或网络参数集合，覆盖真实共享服务消费者；网络专用 `bench_screencap.py` 无需扩展。
- `device_config.save_device_config()` 已采用同目录临时文件和原子替换。计划复用这套保存流程，拒绝混合目标及非法参数后不写文件；USB 保存保留原网络字段，切回网络时删除 serial，避免后续默认连接仍落到 USB。
- `tests/selftest_tree.py` 现有 Section 0 明确拒绝 `--serial`，Section 8 固定 MCP schema，Section 11 覆盖默认设备写入。计划明确更新受需求改变的断言，并增加优先级、准确设备选择、错误状态、不执行 connect、实际参数透传和保存失败回归。

## 范围和风险判断

按本地单用户 CLI、stdio MCP 和串行压测的现有运行规模审核。无需新增设备自动选择、多设备调度、热插拔恢复或并发配置管理。

优先级明确：显式 serial 与显式 IP/port 互斥；显式网络参数覆盖已保存 serial；无显式目标时使用配置 serial。USB 模式不校验无关网络字段，支持 USB-only 配置。USB-only 配置切回网络仍必须提供可校验的地址和端口，这与现有网络校验要求一致。

工作区检查确认 `config.json` 已有用户修改；本次审核未读取或写入其设备值，未修改生产代码。执行时应继续按计划用脱敏配置和临时路径测试保存，保持真实配置字节不变。

## 验收要求

执行后必须依据实际 RED/GREEN、静态检查、帮助和 diff 检查结果交付，再做一次独立代码审核。USB 真机验收以当前是否有状态为 `device` 的 USB 目标为条件；不可用时记录具体边界，不能把离线替身结果表述为已验证真实有线采集。

**审核裁定：通过。** 用户已授权审核无问题后直接执行，无需增加批准步骤。

未运行应用测试或连接设备；本次只审核计划及调用契约。USB 驱动、设备调试接口、授权及真实 uiautomator2 采集仍需实施阶段验收。
