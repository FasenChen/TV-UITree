# Channel Scan 真机自主复验（2026-10-08）

在电视当前 Channel Scan 场景重新执行完整采集、方向键移动、滚动、焦点截图与真实 stdio MCP 验证，未发现新问题。本轮只测试，未修改生产代码、设备配置或电视设置，未提交或推送。

## 结果

| 检查 | 本轮实际结果 |
|---|---|
| 九个场景的原始 XML、View 与截图核对 | 92/92 通过，含两次焦点恢复检查 |
| 九份新采集的漂移判断与独立原始 View 行比较 | 9/9 通过，均 `drift=false`、`detail=null`，无警告 |
| 五个 MCP 读取工具及 CLI 离线投影 | 36/36 通过 |
| 状态恢复、选中语义及文件保护 | 16/16 通过 |
| 项目完整离线自检 | 1155 条断言通过 |

本轮九份输入的旧花括号筛选也未触发误报，因此不能把本轮称为“再次复现旧缺陷”。修复前后缺陷的复现与闭环证据见[修复验收报告](2026-10-08-dumpsys-drift-fix-validation.md)。

## 场景与焦点

起始窗口为 `com.realtek.slices/com.realtek.tv.settings.ChannelScanActivity`，焦点在左侧 Tuner Mode，当前值 Antenna。仅使用方向键：DOWN 四次、UP 四次、RIGHT、DOWN、UP、LEFT，没有发送确认键或启动搜台。

| 场景 | 焦点 | 屏幕坐标 | 可见摘要项数 |
|---|---|---|---|
| 初始 | Tuner Mode, Antenna | `[70,423,750,554]` | 17 |
| DOWN 1 | Antenna Auto Scan | `[70,578,750,698]` | 10 |
| DOWN 2，页面滚动 | Antenna Manual Scan | `[70,614,750,734]` | 8 |
| DOWN 3 | LCN, ON, Switch | `[70,724,750,844]` | 8 |
| DOWN 4 | Auto Service Update, ON, Switch | `[70,868,750,988]` | 8 |
| UP 四次恢复 | Tuner Mode, Antenna | `[70,423,750,554]` | 17 |
| RIGHT，面板移动后 | Antenna | `[70,268,750,388]` | 7 |
| DOWN | Cable | `[70,412,750,532]` | 7 |
| UP、LEFT 恢复 | Tuner Mode, Antenna | `[70,423,750,554]` | 17 |

进入 Tuner Mode 面板时，面板移动到左侧，焦点坐标随实际画面改变。没有把初始右侧坐标当作固定值。

初始当前窗口有 61 个 a11y 节点、116 个 View 节点，61 个 a11y 节点全部配对。检查覆盖 XML 字段、节点顺序与父子关系、View 唯一覆盖、flags 和局部矩形、唯一焦点关联、visible 文案/状态/动作/矩形，以及 PNG 尺寸和独立绘制的逐像素焦点边框。初始与两个 Tuner Mode 场景的标注截图另经视觉核对。

## 焦点与选中状态

移到 Cable 后，Cable 行获得焦点，但其单选控件仍 `checked=false`；Antenna 单选控件保持 `checked=true`，Satellite 保持未选中。这是方向键移动焦点的正常结果，不能把焦点当作已确认选项。

各场景中可读取的 `checked` 状态均与基线一致，LCN 和 Auto Service Update 保持 ON。结束后窗口与所有 a11y 字段（含焦点、`selected`、`checked`、文字和坐标）与初始一致。

## MCP 与文件保护

使用当前原工作区代码启动实际 stdio 服务，五个读取工具共调用九次：`get_full_tree`、`observe_tv`、`get_visible`、`get_current_focus`、`get_focus_screenshot`。验证双源/a11y 模式、默认配置、`max_nodes` 截断、投影一致性及截图返回。两次截图各生成新路径，文件、Base64 与 MCP 原生 Image 字节相同；标注像素与当次基线一致。

另验证非法布尔端口在写配置前拒绝。每个执行工具只向 stderr 写一个计时块，协议正常；MCP 前后原始字段和原始截图像素一致。`config.json`、生产修复文件、回归脚本和文档索引的测试前后哈希相同。此后仅新增本报告及对应索引入口。

## 范围与证据

验证覆盖本场景的数据读取、方向键、滚动、焦点与截图返回。未执行实际搜台、确认更改调谐模式、切换开关或有效的配置写入，不代表这些业务操作已验收。树与几何证据也不保证每个候选控件的像素均无遮挡。本轮没有重新运行编译或静态检查，因为生产代码没有改动；已实际复跑完整离线自检。

原始数据与 PNG 留在忽略目录，不随仓库提交；正式报告不保存设备地址或账号信息。

- [九个场景验收汇总](../../_temp/tv_retest_20261008_152805/live_summary.json)
- [独立漂移核对](../../_temp/tv_retest_20261008_152805/drift_findings.json)
- [36 项 MCP 汇总](../../_temp/tv_retest_20261008_152805/mcp/summary.json)
- [状态与文件保护](../../_temp/tv_retest_20261008_152805/state_and_preservation.json)
- [离线自检日志](../../_temp/tv_retest_20261008_152805/selftest.log)
- [初始截图](../../_temp/tv_retest_20261008_152805/initial/focus.png)、[Cable 焦点截图](../../_temp/tv_retest_20261008_152805/right_cable/focus.png)
