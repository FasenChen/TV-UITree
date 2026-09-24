# tv-uitree

`tv-uitree` 为 TV 自助测试模型提供当前界面的结构化观察结果。模型调用观察工具后，可以知道当前焦点在哪、焦点周围有哪些控件、这次判断依据哪些数据，以及哪些信息仍不确定。本项目也保留完整控件树、遥控器按键和截图核对工具，供开发与人工排查使用。

项目通过根目录唯一的 main.py 启动，没有打包或构建步骤。

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

在 MCP 客户端中选择 stdio 传输，将第一条路径设为启动命令，第二条路径设为第一个参数，并将 `mcp` 设为第二个参数，工作目录设为仓库根目录。启动后服务等待客户端请求，终端没有页面输出是正常现象；客户端应能列出 `observe_tv`、`get_full_tree`、`get_current_focus` 和 `get_focus_screenshot`。若启动时报缺少 `mcp`，在仓库根目录执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。

| 工具 | 返回内容 | 常用参数 |
|---|---|---|
| `observe_tv` | 焦点、页面摘要和判断证据 | `TV_IP_Address`、`port`、`no_dumpsys`、`max_nodes` |
| `get_full_tree` | 当次采集的完整控件树 | `TV_IP_Address`、`port`、`no_dumpsys` |
| `get_current_focus` | 只返回当前焦点状态、节点、候选和上下文 | `TV_IP_Address`、`port`、`no_dumpsys` |
| `get_focus_screenshot` | 返回实时 PNG 图像，并用红框标出焦点位置 | `TV_IP_Address`、`port`、`no_dumpsys` |

### MCP 工具参数

四个工具都从仓库根目录的 `config.json` 读取默认设备参数。调用时传入的值优先于配置文件；可以只覆盖其中一个值。MCP 参数 `TV_IP_Address` 对应 CLI 的 `--TV_IP_Address`。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `TV_IP_Address` | string 或 null | `null` | 电视的 IP 或主机名；省略时读取 `config.json` 的同名字段，不包含端口。 |
| `port` | integer 或 null | `null` | ADB TCP 端口；省略时读取 `config.json` 的 `port`，有效范围 1–65535。 |
| `adb` | string 或 null | `null` | 运行 MCP 服务的电脑上的 ADB 可执行文件路径；省略时读取 `config.json` 的 `adb`。显式传入时覆盖配置。 |
| `no_connect` | boolean | `false` | 为 `true` 时不执行 `adb connect`，但仍会检查目标是否已经出现在 `adb devices` 中。适合已提前连接的设备。 |
| `no_dumpsys` | boolean | 见下文 | 为 `true` 时只读取 uiautomator2 无障碍树；为 `false` 时同时读取 `dumpsys activity top`，用于补充 View 节点和 R0–R3 配对证据。 |

`observe_tv` 和 `get_full_tree` 的 `no_dumpsys` 默认是 `false`；两个焦点专用工具默认是 `true`，只读取焦点所需的 a11y 树。需要双源诊断时，可显式设为 `false`。

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

`get_current_focus` 直接返回与 `observe_tv.focus` 相同的对象，不附带页面摘要。`get_focus_screenshot` 返回文本元数据和可直接显示的 MCP `image/png` 内容，不要求客户端打开本地路径。红框只使用 a11y 的 `bounds_screen` 读数，线宽为 3 像素；不会用 dumpsys 派生坐标猜位置。元数据包含焦点状态、取树和截图时刻、画出/跳过的框数以及提示。若没有焦点或坐标，仍返回截图，但明确说明未加框；若焦点框无法绘制或采集失败，则返回错误。两个时间戳可以帮助判断画面变化造成的错位。

## 用 MCP Inspector 网页调试

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

连接成功后，在工具列表中选择所需的四个工具。临时覆盖目标电视时可以这样填写参数：

```json
{
  "TV_IP_Address": "192.168.1.148",
  "no_dumpsys": false,
  "max_nodes": 20
}
```

`get_full_tree` 不接受 `max_nodes`；如果只验证 a11y 读取，可以把 `no_dumpsys` 设为 `true`。`get_current_focus` 和 `get_focus_screenshot` 也不接受 `max_nodes`。Inspector 网页本身只调试 MCP 协议和工具参数；所有工具都是只读采集，不会发送遥控器按键。

stdio 服务的标准输出专用于 MCP 协议，诊断信息写入标准错误；不要在 `main.py mcp` 服务中增加普通标准输出日志，否则可能导致 Inspector 连接失败。更完整的协议、CLI 和网页选项见 [MCP Inspector 官方文档](https://github.com/modelcontextprotocol/docs/blob/main/docs/tools/inspector.mdx)。

## 其他命令

```powershell
python main.py tree --mode full --out full.json
python main.py tree --TV_IP_Address 192.168.1.148 --port 5555 --mode slim --out slim.json
python main.py tree --from-json full.json --mode slim --out slim.json
python main.py tree --mode slim --keep empty,offscreen --out kept.json
python main.py tree --prune-list

python main.py input DOWN,RIGHT,OK --delay 0.6
python main.py shot --json full.json --source both --out focus.png
```

`full` 是未剪枝的一体式 JSON，`slim` 是对同一份全量树进行剪枝，`observe` 是给模型的焦点与页面摘要。`--from-json` 应传入已有的全量 JSON，并用于 `tree --mode slim` 或 `observe`；程序只检查输入包含 `tree` 列表，已剪掉的信息无法从 `slim` 恢复。`--keep` 只用于 `slim`。`--no-dumpsys` 可明确选择只采集 a11y；正常双源采集失败时不会悄悄切换到单源结果。CLI 用法或文件错误返回退出码 `2`，设备或采集失败返回 `3`。不传子命令时只显示帮助，不连接 TV。

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
| R1 | 预测可见矩形、资源 ID 和类名条件同时满足，且候选唯一 |
| R2 | 两侧各有唯一焦点节点，且类名条件满足 |
| R3 | 已配对的父节点下，子节点保序映射只有唯一解 |

无法唯一配对的 dumpsys 节点保留在全量 JSON 的 `dumpsys_only`，不猜它在 a11y 树中的位置。a11y 的 `bounds_screen` 和 dumpsys 的 `bounds_local` 是各自数据源的**读数**；`bounds_abs_unclipped`、`pred_visible_rect` 是**派生值**。后者受滚动偏移等限制，不能当作真实屏幕坐标。`dumpsys activity top` 也无法覆盖所有独立窗口，例如某些对话框和输入法界面；结果中的 `segment_match_note` 会提示窗口段匹配问题。

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

`tests/selftest_tree.py` 覆盖解析、R0–R3 配对、剪枝、CLI、观察摘要和截图几何；不需要连接 TV。已有 `full.json` 时，可运行 `python main.py observe --from-json full.json --out observe.json` 检查离线观察。MCP 接入时，在客户端确认能列出四个工具，并检查 `get_focus_screenshot` 的 PNG 是否有红色焦点框。

真实设备验收时，先在 TV 上打开一个有焦点的页面，再采集 `observe`；需要验证按键后的焦点变化时，发送一个遥控器按键并重新采集。`adb devices -l` 只说明 ADB 连接状态：若报 `device offline`，先恢复 ADB 连接；若报“dumpsys 里没有可用的 ACTIVITY 段”，当前画面没有可用的补充树，可明确使用 `--no-dumpsys` 只读 a11y。若 uiautomator2 同时报告 `dump empty`，应切换到有无障碍节点的页面后重试。
