# MCP 与直接截图耗时压测

`scripts/bench_mcp.py` 在同一台 TV、同一画面下，串行比较实际 stdio MCP 调用和直接取回 PNG 的耗时。每次调用记录客户端完整耗时、现有服务端日志总耗时及各阶段耗时，并输出 UTF-8 TXT 报告、JSON 汇总、JSONL 逐次记录和原始 stderr。

脚本不修改配置、不发送按键、不调用 `set_default_device`。测试前后读取画面与焦点并比较像素指纹；如果发生变化，报告明确标记不能作为同场景结论。

## 运行

在项目根目录使用现有虚拟环境：

```powershell
$env:PYTHONUTF8 = '1'
# 使用 config.json 的地址、端口与 ADB 路径
.\.venv\Scripts\python.exe scripts/bench_mcp.py

# USB 有线设备：序列号来自 adb devices，状态必须为 device
.\.venv\Scripts\python.exe scripts/bench_mcp.py --serial USB_SERIAL --count 2 --warmup 1

# 指定设备，先做两轮快速验证；地址示例请替换
.\.venv\Scripts\python.exe scripts/bench_mcp.py 192.0.2.10 --count 2 --warmup 1

# 每项正式 30 次，输出到一个尚不存在的目录
.\.venv\Scripts\python.exe scripts/bench_mcp.py 192.0.2.10 --count 30 --warmup 1 --output _temp/bench_mcp/run_30
```

保持电视画面静止，不同时运行其他设备测试或使用遥控器；推荐停在无时钟、无轮播动画的设置页面。脚本不自动切换页面。使用已建立的同一 ADB 目标；各调用仍执行项目正常的连接检查，直接截图也采用相同的连接设置。

| 参数 | 默认值与含义 |
|---|---|
| `address` | 可省略，读取配置；填 IP 或主机名，不含端口 |
| `--port` | 读取配置，合法范围 1–65535 |
| `--serial` | USB 设备序列号；与显式 address/port 互斥；不填时沿用共享配置的目标选择规则 |
| `--adb` | 读取配置及项目现有 ADB 解析规则 |
| `-n` / `--count` | 每项正式调用 10 次，必须为正整数 |
| `--warmup` | 每项预热 1 次，可设为 0；不进入正式统计 |
| `--timeout` | MCP 单次响应超时 120 秒，必须为正整数；直接截图沿用现有截图函数的 60 秒超时 |
| `--output` | 默认 `_temp/bench_mcp/<时间>/`；指定目录必须不存在，避免覆盖旧报告 |

使用已安装的 MCP 1.x、Pillow 和 uiautomator2，不需要安装新依赖。脚本使用 SDK 的公开 `ClientSession`、`StdioServerParameters` 和 `stdio_client`；核对依据为项目实际 MCP 1.30.0 及 [SDK v1 文档](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/README.md)。

## 待测项与条件

| 报告中的名称 | 实际调用 | 模式 |
|---|---|---|
| `get_full_tree` | MCP `get_full_tree` | 默认 a11y + dumpsys |
| `get_full_tree_a11y` | MCP `get_full_tree` | `no_dumpsys=true` |
| `get_screen_summary` | MCP `get_screen_summary` | 默认 a11y + dumpsys |
| `get_screen_summary_a11y` | MCP `get_screen_summary` | `no_dumpsys=true` |
| `get_visible_controls` | MCP `get_visible_controls` | 按现有契约仅采 a11y |
| `get_current_focus` | MCP `get_current_focus` | 按现有契约仅采 a11y |
| `get_focus_screenshot` | MCP `get_focus_screenshot` | a11y 焦点 + PNG + 标注 + 编码 + 文件 + MCP 图片返回 |
| `direct_screenshot` | 同一连接配置下调用 `image.capture` | 直接取回原始 PNG，不读树、不标注、不做 MCP 封装 |

MCP 服务只启动一次，启动到 initialize 完成的耗时单列；工具发现、场景核对、结果校验和写压测报告不计入单次调用。默认八项各正式十次、预热一次，共 80 次正式调用和 8 次预热。预热和正式调用均串行，每轮把调用顺序循环移一位，减少固定顺序的影响。这是单设备顺序延迟测试，不是并发容量测试；前后指纹一致也不能证明期间每一帧都不变。

直接 PNG 与带语义树／焦点标注的工具完成的工作不同。比较结果说明这些获取路径的实际等待时间，不能把两者总耗时差全部归因于 MCP 协议。原始 PNG 返回也不包含大模型看图、推理或上传到模型平台的耗时。

## 时间口径

所有耗时单位为毫秒，客户端使用 `perf_counter`。

| 字段 | 计时边界 |
|---|---|
| `client_ms` | MCP 从 `call_tool` 发起到 SDK 返回完整响应；直接截图从连接检查开始到 PNG 返回及该次计时日志写完 |
| `server_ms` | 现有 `[tv-uitree] ... total ... ms` 的工具体时间；直接截图使用相同 `tool_timing` 记录 |
| `extra_ms` | `client_ms - server_ms`；含序列化、stdio 传输、SDK 处理和调度等，不能解释为纯网络耗时 |
| `stages_ms` | 从本次调用唯一日志块提取各阶段，不跨调用拼接 |
| `startup_ms` | MCP 子进程启动至 initialize 完成，不摊入正式样本 |

服务端日志保留一位小数；极小的负差值可能来自舍入，脚本不强行改成零。

| 阶段 | 含义 |
|---|---|
| `connect` | 配置读取与连接检查 |
| `capture_tree` | 当前已有埋点覆盖的树采集与构建整体；双源包含 dumpsys，a11y 模式不包含 |
| `summarize` | 生成观察／可见摘要或提取焦点 |
| `screenshot` | 发起截图、取回完整 PNG 字节并通过项目现有 PNG 签名检查；不含连接 |
| `mark` | 渲染焦点框 |
| `encode` | 状态 JSON 中 PNG 的 Base64 编码 |
| `save` | 工具自身保存焦点截图文件 |

没有的阶段不会显示为伪造的零值。`capture_tree` 内部没有独立埋点的步骤不会被拆出估算时间；原生 MCP 图片的后续封装／序列化可能出现在客户端与服务端总耗时差中。

## 输出与解读

| 文件 | 内容 |
|---|---|
| `report.txt` | 汇总、每项总耗时统计、每个阶段统计、同轮直接截图差值／倍数、全部逐次记录 |
| `report.json` | 运行设置、环境版本、各项实际参数、启动时间、前后场景指纹、配置是否改动、逐次样本和汇总 |
| `samples.jsonl` | 每次完成调用即追加并 flush；包括预热、失败、阶段及原始日志字节偏移 |
| `stderr.log` | SDK／服务日志与直接截图的原始计时块；MCP stdout 仍只用于协议 |

每项给出正式样本的成功率、成功与失败数，以及成功样本的 min、mean、p50、p90、p99、max。分位数复用现有截图压测脚本的最近秩法；10 个样本的 p99 通常等于最大值，不能当作稳定的尾部延迟估计。

比较使用同一正式轮次中两项均成功的样本。平均差是这些样本中 `工具 client_ms - 直接截图 client_ms` 的平均值；倍数是这些配对样本的两组均值之比。直接截图该轮失败时，不用别轮替代。汇总 `extra_ms` 由每个成功样本先做差再统计。

预热、协议错误、返回 JSON 内的业务错误、失败阶段、计时块缺失／重复／错配／损坏均不算成功样本。工具级失败会记录后继续；MCP 传输异常会停止后续调用，避免超时未结束的调用与下一次日志混淆。不自动重试或切换采集模式。

Ctrl+C 会保留已经完成的样本并尝试写出报告，stdio 上下文负责关闭子进程；强制结束进程时至少可以查看已 flush 的 JSONL 和原始日志，但不保证生成最终报告。焦点截图工具按原有契约写入 `_temp/focus_screenshots/`，脚本不会自动删除图片。运行产物可能含当前页面文本或本地路径，保留在忽略目录，不提交原始产物。

退出码：`0` 完成、全部样本成功且前后场景及配置不变；`1` 工具级失败、场景变化或配置字节变化；`2` 参数、初始化、传输或报告写入错误；`130` Ctrl+C 中断。预热失败也会使完整运行返回 `1`，但预热不计入正式统计。

## 离线验证

```powershell
.\.venv\Scripts\python.exe tests/selftest_bench_mcp.py
.\.venv\Scripts\python.exe scripts/bench_mcp.py --help
.\.venv\Scripts\python.exe -m py_compile scripts/bench_mcp.py tests/selftest_bench_mcp.py
.\.venv\Scripts\python.exe -m pyflakes scripts/bench_mcp.py tests/selftest_bench_mcp.py
```

专用离线自检不连接 TV，覆盖 LF／CRLF、日志唯一归属、损坏阶段、失败阶段、预热与失败排除、同轮比较、空样本、MCP 业务错误及未确认场景时的报告提示。
