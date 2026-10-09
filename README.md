# tv-uitree

`tv-uitree` 为 TV 自助测试模型提供当前界面的结构化观察结果。模型调用观察工具后，可以知道当前焦点在哪、焦点周围有哪些控件、这次判断依据哪些数据，以及哪些信息仍不确定。本项目也保留完整控件树、遥控器按键和截图核对工具，供开发与人工排查使用。

项目通过根目录唯一的 main.py 启动，没有打包或构建步骤。

实施计划、评审报告和交付记录统一见 [在线项目文档索引](https://github.com/FasenChen/TV-UITree/blob/main/docs/README.md)。后续 Release 的源码运行 ZIP 不包含 `docs/` 目录，文档保留在仓库中。

## 下载版本

固定版本见 [GitHub Releases](https://github.com/FasenChen/TV-UITree/releases)。当前版本为 `v0.2.0`，建议下载附件 `tv-uitree-v0.2.0.zip`，其中设备配置和相关文档示例已替换为占位值。解压后先修改 `config.json` 的 `TV_IP_Address`；`adb` 默认设为 `adb`，需要将 ADB 加入 PATH 或填写本机完整路径，再按下方步骤安装依赖。

这是源码运行包，需要 Python 和 ADB。版本范围和检查结果见 [v0.2.0 发布记录](https://github.com/FasenChen/TV-UITree/blob/v0.2.0/docs/reports/2026-10-08-v0.2.0-release.md)，后续发布步骤见 [首次发布记录](https://github.com/FasenChen/TV-UITree/blob/main/docs/reports/2026-10-05-v0.1.0-release.md)。

## 快速开始

需要 Python 3.10+、ADB 和已开启 ADB 调试的 TV。在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py observe --out observe.json
```

可用 `--max-nodes` 限制页面摘要节点数（默认 80）。打开 `observe.json`，先看 `focus.status` 和 `focus.node`，再看 `focus.context`、`page.nodes` 与 `warnings`。未指定 `--out` 时，JSON 写到标准输出。默认目标从仓库根目录的 `config.json` 读取。按需修改 `TV_IP_Address` 和 `port`：

```json
{
  "TV_IP_Address": "192.168.1.147",
  "port": 5555,
  "adb": "D:\\\\platform-tools\\\\adb.exe"
}
```

连接时直接使用配置文件；临时切换电视可传入 `--TV_IP_Address 192.168.1.148 --port 5555`。显式参数优先于配置文件；只传其中一个时，另一个仍从配置文件读取。`TV_IP_Address` 只填 IP 或主机名，不包含端口。`adb` 设置本机 ADB 可执行文件路径；命令行或 MCP 显式传入 `adb` 时优先。配置文件缺失或值无效时会明确报错。

### 使用 USB 有线 ADB

电视需要开启 USB 调试，并通过支持调试的 USB 接口及数据线连接电脑；电脑需要相应驱动，电视上需要允许本电脑调试。先执行 `adb devices`，复制状态为 `device` 的设备序列号。若 ADB 不在 PATH 中，用 `config.json` 的 `adb` 路径执行该命令。`offline`、`unauthorized` 或未列出的设备不能使用。步骤依据 [Android 官方 ADB 文档](https://developer.android.com/tools/adb)。

```powershell
adb devices
python main.py observe --serial USB_SERIAL
python main.py visible --serial USB_SERIAL
python main.py tree --serial USB_SERIAL --out _temp/usb-full.json
python main.py shot --serial USB_SERIAL --json _temp/usb-full.json --out _temp/usb-shot.png
python main.py input DOWN --serial USB_SERIAL
```

将 `USB_SERIAL` 替换为完整序列号；`input` 会实际发送按键。USB 按序列号直接访问设备，不执行网络 `adb connect`，不要求 TV IP 和 TCP 端口。多台设备同时连接时仍只操作指定序列号，目标不可用时不会选用其他在线设备。现有 uiautomator2 采集服务复用同一序列号，符合 [uiautomator2 连接 API](https://github.com/openatx/uiautomator2#connecting-to-device)。

默认使用 USB 时，`config.json` 可以设置为：

```json
{
  "serial": "USB_SERIAL",
  "adb": "adb"
}
```

也可以只在已有网络配置中添加 `serial`，保留 IP/port 供切换使用。serial 必须为非空字符串，不含空白、控制字符或冒号；字段缺失或为 `null` 时使用网络配置，空字符串会报错。

目标选择规则：显式 `--serial` 覆盖网络默认值；显式 `--TV_IP_Address` 或 `--port` 覆盖已保存的 USB 默认值，未指定的网络字段仍从配置读取。同一次调用不能同时传 `--serial` 与 IP/port。没有显式目标时优先配置 serial，否则使用 IP/port。USB-only 配置切换到网络时，需要提供完整的 IP 和端口。`--no-connect` 只控制网络连接命令，不能将网络目标改选 USB。USB 断线时按现有错误处理返回失败，重新插线并授权后可再次调用。

如果手头已有本工具产生的全量 JSON，可以不连接 TV：

```powershell
python main.py observe --from-json full.json --out observe.json
```

## 模型观察结果

`--mode observe` 输出 `tv-observation/v1`。这是给模型使用的页面摘要，默认最多列出 80 个有信息的页面节点；完整树可按需另取。以下是字段形状示例，具体值来自当次采集：

```json
{
  "schema_version": "tv-observation/v1",
  "mode": "observe",
  "focus": {
    "status": "found",
    "candidate_count": 1,
    "candidates": [
      {"path": "0/0", "source": "a11y", "class": "android.widget.TextView", "labels": ["设置"]}
    ],
    "node": {"path": "0/0", "source": "a11y", "class": "android.widget.TextView", "labels": ["设置"]},
    "context": {
      "ancestors": [{"path": "0", "source": "a11y", "class": "android.view.ViewGroup", "children_count": 1}],
      "siblings": [],
      "children": []
    }
  },
  "page": {
    "package": "com.example.tv",
    "node_count": 2,
    "summary_node_count": 1,
    "summary_truncated": false,
    "nodes": [
      {"path": "0/0", "source": "a11y", "class": "android.widget.TextView", "labels": ["设置"]}
    ]
  },
  "evidence": {"align_rules": {}, "align_stats": {}, "source_consistency": {}},
  "warnings": [],
  "full_tree_available": true
}
```

示例只展示部分字段；实际结果还包含 `captured_at`、`device`、`screen`、`window` 和 `evidence.segment_match_note`。

| 字段 | 如何使用 |
|---|---|
| `focus.status` | `found` 表示唯一焦点；`ambiguous` 表示多个候选；`missing` 表示未读到焦点；`error` 表示采集失败。 |
| `focus.node` / `focus.context` | `found` 时给出焦点节点及祖先、同级节点和子节点。 |
| `focus.candidates` | 保留所有候选；`ambiguous` 时不替模型选一个。 |
| `page.nodes` | 精简的页面节点列表，包含文字、资源 ID 或可操作属性。`summary_truncated=true` 表示列表达到上限。 |
| `evidence` / `warnings` | 记录配对规则、统计、画面漂移、窗口段回退和解析告警；出现告警时应重新观察或查看完整树。 |

节点的 `path` 是**本次快照内**的树位置，不能当成跨页面或跨采集的稳定标识。`actions` 描述节点读到的可操作属性，不表示遥控器按键后一定会跳到该节点。`bounds_kind=screen_reading` 对应 a11y 的屏幕坐标读数；`bounds_kind=local_reading` 对应 dumpsys 相对父容器的布局坐标读数，两者不能直接混用。

`error` 是 MCP 的 `observe_tv` 在采集失败时返回的状态；CLI 采集失败时打印原因并以退出码 `3` 结束，不输出观察 JSON。

## 通过 MCP 接入模型

`python main.py mcp` 启动只读 stdio MCP 服务。在仓库根目录运行下面的命令，取得当前机器上的绝对路径：

```powershell
(Resolve-Path .\.venv\Scripts\python.exe).Path
(Resolve-Path .\main.py).Path
```

在 MCP 客户端中选择 stdio 传输，将第一条路径设为启动命令，第二条路径设为第一个参数，并将 `mcp` 设为第二个参数，工作目录设为仓库根目录。启动后服务等待客户端请求，终端没有页面输出是正常现象；客户端应能列出 `observe_tv`、`get_full_tree`、`get_visible`、`get_current_focus`、`get_focus_screenshot` 和 `set_default_device`。若启动时报缺少 `mcp`，在仓库根目录执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。

| 工具 | 返回内容 | 常用参数 |
|---|---|---|
| `observe_tv` | 焦点、页面摘要和判断证据 | `serial` 或 `TV_IP_Address`、`port`；`no_dumpsys`、`max_nodes` |
| `get_full_tree` | 当次采集的完整控件树 | `serial` 或 `TV_IP_Address`、`port`；`no_dumpsys` |
| `get_visible` | 当前屏幕的控件摘要、焦点及操作属性 | `serial` 或 `TV_IP_Address`、`port`；`no_connect` |
| `get_current_focus` | 精简的焦点状态和焦点节点信息 | `serial` 或 `TV_IP_Address`、`port` |
| `get_focus_screenshot` | 返回截图结果、本地 PNG 路径和可直接显示的图片 | `serial` 或 `TV_IP_Address`、`port` |
| `set_default_device` | 修改 `config.json` 的默认设备，返回切换前后的目标 | `serial` 或 `TV_IP_Address`（二选一）；网络可带 `port` |

### MCP 工具参数

五个读取工具都从仓库根目录的 `config.json` 读取默认设备参数。调用时传入的值优先于配置文件；可以只覆盖其中一个值。MCP 参数 `TV_IP_Address` 对应 CLI 的 `--TV_IP_Address`。以下参数对这五个读取工具都适用：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `TV_IP_Address` | string 或 null | `null` | 电视的 IP 或主机名；省略时读取 `config.json` 的同名字段，不包含端口。 |
| `serial` | string 或 null | `null` | USB 设备序列号；不能与显式 IP/port 同时指定。目标选择优先级与 CLI 相同。 |
| `port` | integer 或 null | `null` | ADB TCP 端口；省略时读取 `config.json` 的 `port`，有效范围 1–65535。 |
| `adb` | string 或 null | `null` | 运行 MCP 服务的电脑上的 ADB 可执行文件路径；省略时读取 `config.json` 的 `adb`。显式传入时覆盖配置。 |

`observe_tv`、`get_full_tree` 和 `get_visible` 支持 `no_connect`；`no_dumpsys` 仅适用于 `observe_tv` 和 `get_full_tree`：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `no_connect` | boolean | `false` | 为 `true` 时不执行 `adb connect`，但仍会查询 `adb devices`，且只接受目标状态为 `device`；`offline` 和 `unauthorized` 不视为可用连接。适合已提前连接的设备。 |
| `no_dumpsys` | boolean | `false` | `observe_tv` 和 `get_full_tree` 使用。为 `true` 时只读取 uiautomator2 无障碍树；为 `false` 时同时读取 `dumpsys activity top`，用于补充 View 节点和 R0–R3 配对证据。 |

`get_current_focus` 和 `get_focus_screenshot` 按默认配置连接 TV，只读取焦点所需的 a11y 树，不提供这两个诊断参数。需要双源诊断时使用 `observe_tv` 或 `get_full_tree`。

USB 的五个读取工具调用参数均可为 `{"serial": "USB_SERIAL"}`。`set_default_device` 必须传入 serial 或 TV_IP_Address 二选一：`{"serial": "USB_SERIAL"}` 保存默认 USB 序列号，保留旧网络字段；`{"TV_IP_Address": "192.0.2.10", "port": 5555}` 切回网络并删除 serial，省略 port 时保留配置原端口。不能单独传 port。adb 等其他配置不变；非法目标或写入失败不修改原文件，保存仍为原子操作。配置每次连接时重新读取，切换无需重启 MCP；新增 serial 参数的 schema 需要客户端重新发现工具。

工具只改配置、不连接设备；成功返回 previous、current 和 config_path，失败返回 error 与 error_type。previous/current 的网络目标仍为 `{"TV_IP_Address": "192.0.2.10", "port": 5555}`，USB 目标为 `{"serial": "USB_SERIAL"}`。`config.json` 受 git 跟踪，不要提交本机设备地址、序列号或私有设置。

`get_visible` 与 `python main.py visible` 共用同一观察服务，只采集 a11y，输出 `tv-visible/v1`。结构类似 `observe_tv`：`focus.status` 给出焦点状态，找到唯一焦点时 `focus.path` 指向 `page.nodes` 中的节点；`page.nodes` 包含屏幕内有内容或焦点的控件摘要，提供标签、原始树路径、屏幕坐标及可用操作。同一可操作行的标题和值合并为一个节点；无内容的布局容器不返回。无显示文字的可操作图标若有 `content_desc`，会以 `accessibility_labels` 标出，避免把无障碍描述误认为屏幕文字。只依据 a11y 的 `bounds_screen` 读数、可见属性及屏幕交集判断，保留部分进入屏幕的节点；dumpsys 派生坐标不作为当前可见的证明。省略号摘要与完整文本同时出现时，只保留完整文本。输出不包含完整树、R0–R3 诊断统计或截图 OCR，因此不能证明像素遮挡。无显示文字但有 `clickable`、`long_clickable` 或 `checkable` 明确读数的控件，也会保留已有资源 ID、坐标和操作信息；开关的 `checked=false` 是未选状态，`enabled=false` 是明确的禁用读数。缺失状态保持未知，不补成 false，也不编造文字标签。连接或采集失败时返回 `mode=visible` 与 `error`，异常时另含 `error_type`。

例如焦点位于 IP address 行时，精简结果的主要部分如下（`path` 和坐标以当次采集为准）：

```json
{
  "schema_version": "tv-visible/v1",
  "mode": "visible",
  "focus": {"status": "found", "path": "0/0/1"},
  "page": {"nodes": [
    {"path": "0/0/1", "source": "a11y", "class": "android.widget.LinearLayout",
     "bounds": [91, 418, 822, 549], "bounds_kind": "screen_reading",
     "actions": ["click", "focus"], "focused": true, "labels": ["IP address"]}
  ]}
}
```

`observe_tv` 另外支持以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `max_nodes` | integer | `80` | `page.nodes` 的最大摘要节点数。只限制页面摘要，不会删除 `focus.context`、焦点候选或 `evidence`；小于 1 的值会按 1 处理。 |

#### `observe_tv` 调用示例

使用 `config.json` 中的默认电视：

```json
{}
```

同时读取双源数据，并限制页面摘要为 20 个节点：

```json
{
  "TV_IP_Address": "192.168.1.148",
  "no_connect": false,
  "no_dumpsys": false,
  "max_nodes": 20
}
```

设备已经通过 `adb connect` 连接时，禁止工具再次执行连接：

```json
{
  "no_connect": true,
  "max_nodes": 20
}
```

只读取无障碍树，适合排查 dumpsys 不可用的页面：

```json
{
  "TV_IP_Address": "192.168.1.148",
  "no_dumpsys": true,
  "max_nodes": 20
}
```

#### `get_full_tree` 调用示例

`get_full_tree` 使用设备连接参数和 `no_dumpsys`，不接受 `max_nodes`，返回当次采集的完整树：

```json
{
  "TV_IP_Address": "192.168.1.148",
  "no_dumpsys": false
}
```

如需只检查 a11y 原始树：

```json
{
  "TV_IP_Address": "192.168.1.148",
  "no_dumpsys": true
}
```

MCP 工具没有 `--from-json`、`--out` 或按键参数；每次调用都会重新读取设备。`observe_tv` 成功时返回 `schema_version=tv-observation/v1`，失败时仍返回结构化 JSON，并将 `focus.status` 设为 `error`。`get_full_tree` 失败时返回包含 `error`、`error_type` 和 `mode=full` 的 JSON。

`get_current_focus` 返回 `status` 和精简的焦点 `node`（标签、可选摘要、控件类、资源 ID、包名、坐标及其来源）。标签和摘要会从焦点容器下可见的文本节点中提取，因此焦点落在无文字的布局容器上时，仍能返回容器所代表的项目名称；例如设置列表会返回 `label: Network & Internet` 和对应的网络摘要。工具不会返回重复的 `candidates`，也不会附带祖先、同级节点或子节点。若焦点有多个候选，则返回精简候选列表；若焦点缺失或采集失败，则返回状态和原因。完整上下文仍可通过 `observe_tv.focus` 获取。

`get_focus_screenshot` 返回精简的文本 JSON 和可直接显示的 MCP `image/png` 内容。JSON 固定包含 `focus_found`（找到唯一 a11y 焦点）、`screenshot_captured`（取得 PNG）、`focus_marked`（在截图上成功画出唯一红框）、`image_path`（服务器本机保存的 PNG 绝对路径；未保存时为 `null`）和 `image_base64`（同一张 PNG 的纯 Base64 字符串；未取得截图时为 `null`）；连接、采集、绘制或保存失败时额外包含简短的 `error`。每次调用都在 Git 忽略的 `_temp/focus_screenshots/` 下保存独立文件。红框只使用 a11y 的 `bounds_screen` 读数，1080p 线宽为 6 像素，并随图片高度缩放，不用 dumpsys 派生坐标猜位置。没有唯一焦点时仍返回未标注的截图和路径；若保存失败但已取得 PNG，仍返回 MCP 图片及 `image_base64`。`image_path` 是 MCP 服务所在电脑的本地路径，其他电脑上的客户端可使用返回的 MCP 图片内容或 `image_base64`。

每次调用 MCP 工具，服务都会向标准错误写一段耗时，工具返回内容不变。首行是开始时间、工具名和总耗时，之后每个阶段一行，列出毫秒数和占总耗时的比例：

```text
[tv-uitree] 16:08:16.975 get_focus_screenshot  total 7737.4 ms
  connect         115.4 ms    1.5%
  capture_tree   3486.3 ms   45.1%
  summarize         0.6 ms    0.0%
  screenshot     3878.8 ms   50.1%
  mark            248.3 ms    3.2%
  encode            5.5 ms    0.1%
  save              2.4 ms    0.0%
```

`total` 从进入工具函数算到函数返回，不含 MCP 库序列化结果和 stdio 传输的时间。阶段含义：`connect` 读取 `config.json` 并连接 ADB；`capture_tree` 读取设备属性、dumpsys、uiautomator2 dump 并配对；`summarize` 生成焦点、观察或可视摘要；`screenshot` 截屏；`mark` 画焦点红框；`encode` 生成 Base64；`save` 写 PNG 文件。没有执行的阶段不出现；某阶段抛出异常时，首行末尾追加 `failed at <阶段名>`。日志显示在哪里取决于宿主：在终端直接运行 `python main.py mcp` 时显示在该终端，其他宿主一般写进它的 MCP 服务日志。

## 用 MCP Inspector 网页调试

Inspector 的通用安装、启动、网页操作和排错步骤见 [MCP Inspector 通用使用指南](https://github.com/FasenChen/TV-UITree/blob/main/docs/MCP_Inspector_通用使用指南.md)；本项目六个工具的用法见上文。

仓库提供了一个可重复启动的 PowerShell 包装脚本，用官方 [MCP Inspector](https://github.com/modelcontextprotocol/inspector) 打开本地网页调试界面。Inspector 需要 Node.js 22.19 或更高版本；项目本身仍由 `.venv` 中的 Python 启动。

在仓库根目录运行：

```powershell
.\scripts\start_mcp_inspector.ps1
```

终端会打印类似下面的地址：

```text
http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=...
```

复制完整地址到浏览器。Inspector 的服务进程必须保持运行；关闭启动它的终端会同时停止网页调试服务。也可以直接使用官方命令：

```powershell
npx -y @modelcontextprotocol/inspector .\.venv\Scripts\python.exe .\main.py mcp
```

进入网页后，确认连接类型为 `STDIO`。如果界面要求手工填写启动信息，使用下面的值：

| 字段 | 值 |
|---|---|
| Command | 仓库内 `.venv\Scripts\python.exe` 的绝对路径 |
| Arguments | 仓库根目录 `main.py` 的绝对路径、`mcp` |
| Working directory | 仓库根目录 |
| Environment | 通常留空；默认设备地址从仓库根目录的 `config.json` 读取 |

连接成功后，在工具列表中选择所需的工具。临时覆盖目标电视时可以这样填写参数：

```json
{
  "TV_IP_Address": "192.168.1.148",
  "no_dumpsys": false,
  "max_nodes": 20
}
```

`get_full_tree` 和 `get_visible` 不接受 `max_nodes`；如果只验证 `get_full_tree` 的 a11y 读取，可以把 `no_dumpsys` 设为 `true`。`get_visible` 始终只采集 a11y，不需要此参数。`get_current_focus` 和 `get_focus_screenshot` 不接受 `max_nodes`、`no_connect` 或 `no_dumpsys`。Inspector 网页本身只调试 MCP 协议和工具参数；除 `set_default_device` 修改 `config.json` 外，其余工具都是只读采集；所有工具都不会发送遥控器按键。

stdio 服务的标准输出专用于 MCP 协议，诊断信息写入标准错误；不要在 `main.py mcp` 服务中增加普通标准输出日志，否则可能导致 Inspector 连接失败。更完整的协议、CLI 和网页选项见 [MCP Inspector 官方文档](https://github.com/modelcontextprotocol/docs/blob/main/docs/tools/inspector.mdx)。

## 其他命令

```powershell
python main.py tree --mode full --out full.json
python main.py visible --out visible.json
python main.py visible --from-json full.json --out visible.json
python main.py tree --TV_IP_Address 192.168.1.148 --port 5555 --mode slim --out slim.json
python main.py tree --from-json full.json --mode slim --out slim.json
python main.py tree --mode slim --keep empty,offscreen --out kept.json
python main.py tree --prune-list

python main.py input DOWN,RIGHT,OK --delay 0.6
python main.py shot --json full.json --source both --out focus.png
python scripts/bench_screencap.py 192.168.1.148 --count 50
```

`full` 是未剪枝的一体式 JSON，`slim` 是对同一份全量树进行剪枝，`observe` 是给模型的焦点与页面摘要，`visible` 是只覆盖屏幕内控件的精简观察。`--from-json` 应传入已有的全量 JSON，并用于 `tree --mode slim`、`observe` 或 `visible`；已剪掉的信息无法从 `slim` 恢复。`--keep` 只用于 `slim`。`observe` 和 `tree` 可用 `--no-dumpsys` 只采集 a11y；`visible` 始终只采集 a11y。正常双源采集失败时不会悄悄切换到单源结果。`observe`、`tree`、`visible` 的用法、文件或连接错误返回退出码 `2`，连接后的采集失败返回 `3`；`shot` 和 `input` 自身失败返回 `1`，连接失败返回 `2`。`--out` 写普通 JSON 文件时先写同目录临时文件再替换目标，写入或替换失败时旧文件保持完整并清理临时文件；设备输出（如 Windows `NUL`、`os.devnull`）直接写入，不提供普通文件的原子替换保证。不传子命令时只显示帮助，不连接 TV。

`--from-json` 在文件入口校验节点、子树、矩形和屏幕等实际消费的结构；保留合法稀疏数据及未知字段。损坏的 a11y XML 会报告采集失败，合法空 hierarchy 仍可以生成空树。`input` 在连接前验证整个键码序列，允许短名、`KEYCODE_*` 标识符和 ASCII 数字；含空格或 shell 元字符的非法键码返回 `2`，不会先发送合法前半段。实际 ADB 发送失败和 `shot` 图片解码、绘制或写入失败会输出中文说明并返回 `1`；`shot` 的 JSON/图片读取失败也保留返回 `1`。

`scripts/bench_screencap.py` 压测截图耗时：参数是一个或多个设备 IP（`ip` 或 `ip:port`，未带端口时用 `--port`，默认 `5555`）和 `-n/--count` 次数。每次计时覆盖一次完整截图（发起到 PNG 全部取回并校验），不含连接；逐次打印耗时和 PNG 大小，最后给出 min / mean / p50 / p90 / p99 / max。单次失败会记下原因并继续，Ctrl+C 会打印已完成部分的统计。退出码：`0` 全部成功，`1` 有截图失败，`2` 参数或连接错误，`130` 被中断。每次运行都会写一份 UTF-8 txt 报告（汇总、逐次记录、连接失败），默认在 `_temp/bench_screencap/bench_screencap_<时间>.txt`，可用 `--report <路径>` 指定；中断时也会写出已完成部分。报告写入失败时退出码为 `2`。

`python scripts/bench_mcp.py --count 10 --warmup 1` 比较同场景的五个 MCP 读取工具、tree/observe 的 a11y 模式与直接截图；设备默认读取配置。报告同时包含客户端总耗时、现有服务端总耗时、各阶段和同轮截图差值，写入 `_temp/bench_mcp/<时间>/` 的 UTF-8 TXT／JSON／JSONL 与原始 stderr。服务启动单列，预热与失败不进入成功统计，前后场景变化会标记比较条件不一致；不发送按键或修改配置。参数、边界及结果解读见 [MCP 与直接截图耗时压测](https://github.com/FasenChen/TV-UITree/blob/main/docs/bench-mcp.md)。

`slim` 默认启用八个剪枝开关：

| 开关 | 省略的内容 |
|---|---|
| `gone` | GONE 节点及其子树 |
| `zeroarea` | 零面积节点及其子树 |
| `offscreen` | 屏幕外节点及其子树 |
| `empty` | 没有有效信息的节点及其子树 |
| `derived` | 派生坐标字段 |
| `defaults` | 取默认值的布尔字段 |
| `meta` | 配对与解析元数据 |
| `instance` | View 实例标识 |

`--keep <开关>` 关闭对应剪枝；`--keep all` 保留全部内容。每个节点只由一个树级开关认领，具体顺序和本次剪枝数量可通过 `--prune-list` 及输出中的 `slim` 字段检查。

## 数据从哪里来

采集使用两个来源：`uiautomator2` 读取 a11y（无障碍）树，提供文字、焦点和屏幕可见矩形；`dumpsys activity top` 提供 Activity 的 View 层次、布局矩形及 a11y 未收录的节点。两次 dumpsys 中实际使用的层次行会比较；`source_consistency.drift=true` 表示采集期间界面发生变化。

Android 16 的 ViewDebug 可能把外层名称写成 `DecorView{...}[MainSettings]`。解析器同时支持名称位于实例块前后的两种格式，避免整段 View Hierarchy 被误判为空。

两棵树只按明确的 R0–R3 规则配对：

| 规则 | 依据 |
|---|---|
| R0 | 两侧唯一根节点 |
| R1 | 预测可见矩形、资源 ID 和类名条件同时满足，且双方候选都唯一 |
| R2 | 两侧各有唯一焦点节点，且类名条件满足 |
| R3 | 已配对的父节点下，子节点保序映射只有唯一解 |

无法唯一配对的 dumpsys 节点保留在全量 JSON 的 `dumpsys_only`，不猜它在 a11y 树中的位置。`dumpsys_only` 按 View 层次组成森林，每个未定位节点只出现一次；已配对的后代只在主树中出现，不在这里重复。a11y 的 `bounds_screen` 和 dumpsys 的 `bounds_local` 是各自数据源的**读数**；`bounds_abs_unclipped`、`pred_visible_rect` 是**派生值**。后者受滚动偏移等限制，不能当作真实屏幕坐标。`dumpsys activity top` 也无法覆盖所有独立窗口，例如某些对话框和输入法界面；结果中的 `segment_match_note` 会提示窗口段匹配问题。

## 代码结构与数据流

根目录只有 `main.py` 一个 Python 入口。设备与文件 I/O 位于基础设施层；应用层编排采集、按键和截图；领域层完成解析、匹配、裁剪与摘要；接口层提供 CLI 和 MCP。

```text
main.py                     唯一命令入口
tvuitree/
  __init__.py               collect_full_json、collect_observation 公开 API
  interfaces/               CLI、MCP、终端输出和设备参数
  application/              采集、观察、按键、截图工作流
  domain/
    tree/                   树模型、解析、R0–R3、输出和剪枝
    observation.py          焦点判断与页面摘要
    screenshot.py           坐标选择与对照
  infrastructure/           ADB、uiautomator2、快照读取和 PNG 画框
tests/
  selftest_tree.py          离线回归断言
```

采集数据流为：ADB 读取设备状态 → 基础设施层读取 a11y 与 dumpsys → 应用层组织快照 → 领域层解析并按 R0–R3 配对 → 生成 full JSON。slim 从同一份 full JSON 剪枝；观察摘要从 full JSON 提取焦点、上下文、页面节点和证据。CLI 与 MCP 调用同一应用服务。

按键仍是独立工作流；截图核对可用 CLI 或 MCP。需要验证真实按键焦点顺序时，先观察、用 `main.py input` 发按键，再重新观察。树的布局顺序不等于遥控器的焦点跳转顺序。`_temp/` 是调查产物，不作为源代码。

### 截图画框约定

`shot --json` 的输入文件不存在、JSON 损坏或树结构不合法时，退出码为 `1`，错误说明写入 stderr，不输出 traceback，也不连接设备或生成 PNG。JSON 根对象必须是含列表类型 `tree` 的对象。库读取接口抛出 `OSError` 或 `ValueError`，由 CLI 负责转换为退出码；JSON 输出提示的大小按实际 UTF-8 字节数计算，包含末尾换行。

`main.py shot` 用于核对读数与画面。画框约定是：框的几何来自树中的坐标，**不加偏移**，按读数**逐像素**绘制，也**不补偿**看起来的错位。`--width` 只改变线宽，不能用来修正坐标。a11y 读数与 dumpsys 派生坐标用不同样式区分；两者不一致时，差异本身就是排查信息。

## 旧命令迁移

| 旧命令 | 新命令 |
|---|---|
| `python tv_tree.py --mode observe ...` | `python main.py observe ...` |
| `python tv_tree.py --mode full ...` | `python main.py tree --mode full ...` |
| `python tv_tree.py --mode slim ...` | `python main.py tree --mode slim ...` |
| `python tv_input.py ...` | `python main.py input ...` |
| `python tv_shot.py ...` | `python main.py shot ...` |
| `python tv_mcp.py` | `python main.py mcp` |
| `python selftest_tree.py` | `python tests/selftest_tree.py` |

Python 调用方使用 `from tvuitree import collect_observation, collect_full_json`。完整树 JSON 中的 `generator` 仍为历史值 `tv_tree.py`，以维持已有数据消费者的比较结果。`collect_full_json(adb=..., serial=...)` 实时采集；`collect_observation(full_json=...)` 离线生成摘要，也可传入 `adb` 与 `serial` 实时观察。返回结构保持原样。旧根目录模块导入路径结束支持。

## 验证

从仓库根目录运行：

```powershell
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
python -m py_compile $pythonFiles
python -m pyflakes $pythonFiles
python tests/selftest_tree.py
python main.py --help
python main.py tree --prune-list
```

`tests/selftest_tree.py` 覆盖解析、R0–R3 配对、剪枝、CLI、观察摘要、可视控件摘要和截图几何；不需要连接 TV。已有 `full.json` 时，可运行 `python main.py observe --from-json full.json --out observe.json` 检查离线观察。MCP 接入时，在客户端确认能列出六个工具，并检查 `get_focus_screenshot` 的 PNG 是否有红色焦点框。调用任一 MCP 工具后，服务的标准错误中应出现一段以 `[tv-uitree]` 开头的耗时记录。

真实设备验收时，先在 TV 上打开一个有焦点的页面，再采集 `observe`；需要验证按键后的焦点变化时，发送一个遥控器按键并重新采集。`adb devices -l` 只说明 ADB 连接状态：若报 `device offline`，先恢复 ADB 连接；若报“dumpsys 里没有可用的 ACTIVITY 段”，当前画面没有可用的补充树，可明确使用 `--no-dumpsys` 只读 a11y。若 uiautomator2 同时报告 `dump empty`，应切换到有无障碍节点的页面后重试。
