# USB 有线 ADB 支持交付与验证

## 当前结果

USB 设备序列号已接入 CLI、五个读取 MCP 工具、默认设备配置和 MCP 压测入口。现有网络配置及调用保持兼容，真实本地 config.json 的字节未改变。独立计划审核通过；独立代码终审发现 1 项 NUL 输入校验缺口，已完成 RED→GREEN 补修，最终 1255 条离线断言全部通过。本次 USB 真机验收未完成。

## 使用方式

先在支持 USB 调试的 TV 接口连接数据线，开启 USB 调试并允许电脑访问。使用本机 ADB 执行 `adb devices`，将下面的 USB_SERIAL 换成状态为 device 的完整设备序列号：

```powershell
.\.venv\Scripts\python.exe main.py observe --serial USB_SERIAL
.\.venv\Scripts\python.exe main.py visible --serial USB_SERIAL
.\.venv\Scripts\python.exe main.py tree --serial USB_SERIAL --out _temp/usb-full.json
.\.venv\Scripts\python.exe main.py shot --serial USB_SERIAL --json _temp/usb-full.json --out _temp/usb-shot.png
.\.venv\Scripts\python.exe scripts/bench_mcp.py --serial USB_SERIAL --count 2 --warmup 1
```

五个读取 MCP 工具使用参数 `{"serial": "USB_SERIAL"}`。默认切到 USB 可调用 `set_default_device` 传 `{"serial": "USB_SERIAL"}`；切回网络传 `{"TV_IP_Address": "192.0.2.10", "port": 5555}`。新增 serial 的 MCP 工具 schema 需要客户端重新发现。

配置可仅包含 serial 和可选 adb，不要求 IP/port；保存 USB 默认值会保留原网络字段。显式 serial 与显式 IP/port 互斥；显式网络参数覆盖已保存的 USB 默认值，没有显式目标时优先配置 serial。切回网络默认值时删除 serial，网络 previous/current 返回字段保持原样，USB 目标为 `{serial}`。

USB 路径只按指定 serial 查询及访问设备，不执行网络 adb connect；offline、unauthorized 或缺失目标不会回退其他在线设备。现有低层 ADB 和 uiautomator2 已接受序列号，本次没有增加设备自动选择、热插拔恢复或依赖。

## 修改范围

- application/connection.py：共享参数选择、serial 校验、默认目标保存。
- interfaces/connection.py：五个 CLI 实时命令新增 --serial，USB 失败提示改为数据线、接口、驱动、调试授权及 devices 状态。
- interfaces/mcp.py：所有工具接入 serial；读取参数追加到原 Python 签名末尾，写配置参数保留 strict 校验。
- scripts/bench_mcp.py：解析及固定 USB/网络目标，直接截图和 MCP 使用同一目标参数。
- tests/selftest_tree.py：序列号优先级、配置切换、原子失败、设备状态、CLI/MCP/uiautomator2/压测透传，以及 USB-only 默认配置下完整自检。
- README、AGENTS、docs/bench-mcp.md、文档索引：更新用法和契约。

本次还局部修正一项已有测试：Section 8 将先前保存的树离线投影与新一次实时投影直接比较时，采集时间跨秒会偶发失败。两者业务字段一致；改用已用于相邻测试的 `_without_capture_time`，继续完整比较其余结果。生产投影逻辑未修改。

## 实际验证

| 检查 | 实际结果 |
|---|---|
| 修改前基线 selftest | 1155 条断言，1 项时间戳跨秒导致的既有测试失败；已定位并按上文修正 |
| 新增 USB 回归 RED | 1230 条断言，48 项失败，覆盖缺失 serial 参数/目标选择和旧 schema；无语法或导入失败 |
| 终审补修 RED | NUL/控制字符连接、保存及 CLI 错误出口回归：1255 条断言，9 项失败，复现审核问题 |
| 最终网络默认配置完整 selftest | 1255 条断言全部通过，退出 0 |
| 最终注入 USB-only 配置完整 selftest | 仅含 serial，不含 IP/port/adb；1255 条断言全部通过，真实配置未修改 |
| py_compile、pyflakes | main.py、tvuitree/、tests/ 和修改的 scripts/bench_mcp.py 全部通过 |
| CLI 检查 | main.py --help、tree --prune-list、observe --help、bench_mcp.py --help 全部退出 0，相关帮助包含 --serial |
| 真实 stdio MCP | 通过官方 SDK 启动本项目服务并发现 6 个 serial schema；非法 serial、混合目标、指定缺失 USB 目标 3 条错误路径均返回受控 visible 错误 |
| 配置保护 | 配置字节及 SHA-256 与任务开始时一致；保存类测试只使用临时配置文件 |
| git diff --check | 通过 |

验证使用项目 .venv：uiautomator2 3.7.0、mcp 1.30.0、pydantic 2.13.5。根目录配置已有用户修改，本次未覆盖或暂存。没有创建提交、推送、发布，也没有对真实设备发送按键。

## 真机边界

只读执行本机 adb devices -l，发现 USB 在线设备 0 台，USB offline/unauthorized 设备 0 台，其他连接 1 台。没有可用 USB 目标，因此 USB 真机 observe/visible/截图/MCP 读取未完成；离线 subprocess、uiautomator2 和采集替身证明软件目标选择与透传契约，不能证明真实驱动、TV 调试接口、授权和有线采集已经通过。已有网络设备未额外连接或操作。

## 审核与证据

- [实施计划](../superpowers/plans/2026-10-09-usb-adb.md)。
- [独立 Ponytail 计划审核](../reviews/2026-10-09-usb-adb-plan-review.md)：通过，无阻塞问题。
- [独立 Ponytail 代码终审](../reviews/2026-10-09-usb-adb-code-review.md)：独立复跑当时的 1246 条断言及静态/帮助检查，通过；发现 NUL 序列号可保存并导致 CLI 漏出 subprocess 的 ValueError，要求先修再交付。
- 实施方已确认根因并在唯一共享 `_check_serial` 中拒绝非打印字符，连接和保存都在 subprocess/原子写入前校验；新增 NUL/BEL 的参数拒绝与配置字节保留、NUL 默认配置的 CLI 退出 2/不启动 subprocess/中文诊断回归。先复现 9 项失败，再完成补修；最终网络及 USB-only 两次完整 suite 各 1255 条通过，静态和 stdio 复验通过。没有新增抽象或重试层，没有遗留阻塞项；未另行要求 reviewer 复审，关闭依据为上述实施方回归证据。
- 本地证据在忽略的 `_temp/usb_adb/`：baseline.log、red.log、green.log、usb-only-suite.log、control-char-red.log、final-green.log、final-usb-only-suite.log、final-review-suite.log、check_stdio.py、stdio.stderr.log、设备列表及帮助输出。证据不随仓库交付；上述结果可独立阅读，不包含真实设备地址或序列号。
