# 真机返回数据验证（2026-10-08）

## 验收结论

本次在一台 Android 16 TV 上完成真实设备验证。在实际覆盖的频道设置、列表滚动和调谐器选项状态中，完整树的原始读数、可见摘要、当前焦点、焦点截图及 MCP 图片传输一致，未发现这些数据被解析错误或坐标被错误偏移。

**整体不能判定全部通过：确认一项 P2 缺陷，`source_consistency.drift` 会把 Android 消息队列变化误报为 View 树变化。** 9 份双源快照中有 4 份触发该误报。该缺陷影响观察摘要的警告与可信度判断；本轮没有发现它改写文字、焦点或坐标。

生产代码未修改。本轮新增验收报告、文档索引和忽略目录中的证据及验证脚本；未提交、推送或发布。原有 `config.json` 修改保留，验证期间文件字节未变化。电视最终恢复至原来的 `Tuner Mode / Antenna` 焦点，调谐器仍选中 Antenna，两个开关仍为开启状态。

## 对象与方法

- 代码：`main`，`6bec2e2016fd0033175bf0044f6a7e2c81c4ff68`。
- 环境：项目 `.venv`；uiautomator2 3.7.0、MCP Python SDK 1.30.0、Pillow 12.3.0、pyflakes 4.0.0。
- 设备系统：Android 16 / SDK 36。
- 分辨率：ADB 分别读到物理 3840×2160、覆盖 1920×1080；树使用逻辑 1920×1080，实际截图也是 1920×1080，两者一致。未修改分辨率。
- 操作：DOWN 四次、UP 四次、RIGHT、DOWN、UP、LEFT。没有发送确认键，没有执行频道扫描或切换调谐器。

核对依据包含设备返回的原始 XML、前后两份 `dumpsys activity top`、独立 ADB 属性与窗口查询、原始截图和最终标注 PNG。不是只比较 CLI 与 MCP 这两条共用实现的路径。

1. 使用标准库 XML 解析逐项核对全部 a11y 节点的文字、描述、资源 ID、坐标、布尔状态、顺序和父子关系。
2. 从原始 View 行独立提取实例标识、两组 flags 与局部坐标；确认每个 View 在统一树或未定位森林中恰好出现一次，原始读数保持一致。
3. 对照 XML 的 `focused=true`、dumpsys 焦点 flags、截图上的高亮控件，确认实际方向键移动后的唯一焦点。
4. 对每个可见摘要项解析其 full-tree 路径，核对来源、屏幕矩形、后代文字、操作属性与状态。逐张查看焦点截图，核对高亮、滚动后的坐标以及开关和单选状态。
5. 用独立像素带计算构造预期红框，逐像素比较最终 PNG，包括框外图像未被改动。
6. 通过真实 stdio 子进程执行 MCP initialize、tools/list 和 tools/call；并对保存的完整树执行 CLI 离线回放。

临时核对脚本最初把 `Counter(mapping)` 当成键的计数，导致 View 覆盖检查误失败；核实无缺失或多余节点后改为 `Counter(mapping.keys())`，重新对全部保存快照执行检查。该修正只涉及临时验证脚本，下面列出的是重跑后的结果。

## 真实画面与返回数据

| 快照 | 截图与原始源确认的焦点 | a11y / View / 配对 | 可见摘要项 | 焦点屏幕矩形 |
|---|---|---:|---:|---|
| initial | Tuner Mode / Antenna | 61 / 116 / 61 | 17 | [70,423,750,554] |
| down_auto_scan | Antenna Auto Scan | 40 / 79 / 40 | 10 | [70,578,750,698] |
| down_manual_scan | Antenna Manual Scan | 37 / 79 / 37 | 8 | [70,614,750,734] |
| down_lcn | LCN，开启 | 36 / 79 / 36 | 8 | [70,724,750,844] |
| down_service_scroll | Auto Service Update，开启 | 36 / 79 / 36 | 8 | [70,868,750,988] |
| restored_left | Tuner Mode / Antenna | 61 / 116 / 61 | 17 | [70,423,750,554] |
| right_antenna | Antenna，选中 | 31 / 56 / 31 | 7 | [70,268,750,388] |
| right_cable | Cable，未选中 | 31 / 56 / 31 | 7 | [70,412,750,532] |
| restored_final | Tuner Mode / Antenna | 61 / 116 / 61 | 17 | [70,423,750,554] |

每份快照的 a11y 节点全部配对，未定位 a11y 和 View 均为 0。初始统一树另外补入 55 个 dumpsys 节点；它们与原始 View 逐项对应，包含布局及 GONE 节点，不能据此把 116 个节点都称为肉眼可见控件。

右移进入调谐器面板时，画面将原右侧面板滚至左侧。31 个配对中有 25 个 `geom_check=drift`：这表示 dumpsys 累加的派生坐标与 a11y 屏幕读数不一致。a11y 焦点屏幕坐标和截图仍一致，红框正确跟随左侧的 Antenna / Cable。**这种逐节点几何差异与下面的前后采集一致性误报是两件事。** 消费者仍应使用 `bounds_kind=screen_reading` 的坐标定位画面。

`get_visible` 保留了关闭/开启状态和禁用文字；初始页面底部部分露出的 Auto Service Update 属于与屏幕相交的可见候选。结果保留 Android 返回的完整文字，不保证整段文字的全部像素都露出。

## MCP 与 CLI

真实 MCP 服务列出六个预期工具。五个读取工具共执行 9 次成功调用，另执行一次非法配置参数验证：

| 项目 | 实际核对结果 |
|---|---|
| get_full_tree | 双源和 a11y-only 均成功；原始 a11y 字段与独立采集一致 |
| observe_tv | 双源、a11y-only、max_nodes=3 均成功；焦点一致，限制只影响页面摘要 |
| get_visible | 返回值与同一已保存完整树的可见投影一致 |
| get_current_focus | 省略设备参数，真实读取当前配置；返回标题 Tuner Mode、副标题 Antenna 及正确矩形 |
| get_focus_screenshot | 两次调用均返回唯一红框和 PNG；文件路径不同；JSON Base64、原生 MCP Image 和保存文件字节完全一致 |
| set_default_device | `port=true` 被协议校验拒绝，配置未写入；合法写入与恢复行为由本轮 1140 条离线回归覆盖，未在真实配置上额外改写 |
| stdout / stderr | MCP 客户端成功解析协议；9 次实际读取调用各有一个 stderr 分阶段耗时块，工具返回不含计时日志 |
| CLI 回放 | observe、visible 与 full 投影完全一致；slim 与默认八开关剪枝结果完全一致 |

MCP 验证前后的原始 a11y 主要字段和截图像素一致，排除了页面变化导致跨调用比较失真的情况。客户端使用本机已安装 SDK 的公开 API，参考 [MCP Python SDK 1.30.0 官方客户端示例](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/docs/client.md)。

## 确认缺陷：漂移误报（P2）

位置：[capture.py](../../tvuitree/domain/tree/capture.py#L19)，`_hierarchy_lines`。

当前实现筛选整份 dumpsys 中所有同时含 `{` 与 `}` 的行，并没有限制在 `View Hierarchy` 内。Android 16 的消息队列也输出这类行，例如：

```text
Message 1: { when=+25ms what=40 target=android.view.ViewRootImpl$ViewRootHandler }
```

消息执行后该行消失，工具便报告 `View 层次行数 621 → 620`。但独立提取全部 Activity 的真实 View 行后，两份均为 415 行，且每行内容和顺序完全一致。

| 快照 | 工具报告 drift | 全部真实 View 行数，前 / 后 | View 内容是否变化 |
|---|---|---:|---|
| down_auto_scan | true | 415 / 415 | 否 |
| restored_left | true | 452 / 452 | 否 |
| right_antenna | true | 392 / 392 | 否 |
| restored_final | true | 452 / 452 | 否 |

其余 5 份快照没有误报。复现脚本返回退出码 1，表示当前产品行为不满足“只比较实际消费的 View 层次行”的契约，不能把这个失败计入通过结果。

现有离线测试只排除了不带花括号的单调时钟字段，并把任意新增的 `多出来的一行{x}` 也断言为漂移，因此没有覆盖消息队列这一真实输入格式。

后续修复应复用已有 View 段解析规则，将比较范围限定到真实 View 节点，并补充两项回归：消息队列变化不漂移，真实 View 增删或坐标变化仍漂移。本次授权范围是验证，故保留原代码并报告缺陷。

## 执行结果与边界

| 检查 | 结果 |
|---|---|
| 项目 Python 文件 py_compile | 通过 |
| 项目 Python 文件 pyflakes | 通过 |
| tests/selftest_tree.py | 1140 条断言通过 |
| 9 份真机快照原始读数、层次、焦点、可见项、PNG 核对 | 92 项通过 |
| 实际 MCP / CLI 回放核对 | 36 项通过 |
| 独立 ADB 元数据和精确 slim 投影 | 5 项通过 |
| 漂移专检 | 9 项中 5 项通过、4 项失败，对应同一个产品缺陷 |
| main.py --help / tree --prune-list | 通过 |
| git diff --check | 通过；原有 config.json 出现 LF/CRLF 提示，不属于差异错误 |

本轮真机范围是一个 Activity 的六种不同焦点/布局状态及恢复快照，未覆盖其他应用、独立对话框、输入法、无焦点、多焦点、设备断连及受保护视频截图。方向键从应用层真实发送，未另做 `main.py input` CLI 真机发送；截图通过实际 MCP 验证，未另做 `main.py shot` CLI 真机取图。这些 CLI 分发路径属于本轮已执行的离线回归范围。

“源读数一致”不意味着 Android 无障碍树能描述所有屏幕像素。可见摘要仍是基于树与坐标的候选集合，不能证明像素未被其他窗口遮挡。本轮截图核对确认的是所列设置画面。

## 本地复现证据

证据位于忽略目录 `_temp/tv_validation_20261008/`，不会随仓库分发。原始文件可能包含设备和系统运行信息，未复制进正式报告。

- [真机汇总](../../_temp/tv_validation_20261008/live_summary.json)
- [MCP 检查汇总](../../_temp/tv_validation_20261008/mcp/summary.json)
- [独立元数据检查](../../_temp/tv_validation_20261008/metadata_summary.json)
- [漂移误报证据](../../_temp/tv_validation_20261008/drift_findings.json)
- [恢复后的焦点截图](../../_temp/tv_validation_20261008/restored_final/focus.png)
- [MCP 原生图片对应 PNG](../../_temp/tv_validation_20261008/mcp/screenshot_1.png)

在保留本地证据的仓库根目录执行：

```powershell
# 离线重新核对 9 份真机数据，应返回 0。
.\.venv\Scripts\python.exe _temp/tv_validation_20261008/validate_live.py --offline

# 重现当前漂移缺陷，应返回 1。
.\.venv\Scripts\python.exe _temp/tv_validation_20261008/drift_repro.py
```
