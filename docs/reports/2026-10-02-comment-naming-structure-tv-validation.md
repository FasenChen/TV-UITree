# TV 真机验证记录

> 归档说明（2026-10-03）：本文记录上一轮注释、命名和结构清理的真机验证，不覆盖后续 Zcode 整改，也不代表设备当前在线。原位置为 `_temp/live-cleanup-20261002/report.md`；报告中的提交号为实验时记录，后续历史改写后不应直接当作当前 HEAD。

相关文档：[该轮清理计划](../superpowers/plans/2026-10-02-comment-naming-structure.md)、[文档索引](../README.md)。

日期：2026-10-02。代码提交：0ec469b。只读验证；未发送遥控按键、修改 TV 设置或 config.json。

## 结果

检查通过 43/43。真实 ADB 连接、CLI 与真实 MCP stdio 均成功。

- CLI：tree full、observe、visible、shot focus 和三种 from-json 离线入口成功；UTF-8 输出字节数与文件长度一致。
- 同一份真机 full JSON 的 observe/visible 离线结果与应用层完全一致。
- 当前稳定画面下，CLI/MCP observe 与 visible 排除 captured_at 后完全一致，完整树节点及配对统计一致。
- MCP：get_full_tree、observe_tv、get_visible、get_current_focus、get_focus_screenshot 五个实际协议调用成功；stderr 每次恰好一个 timing 块，阶段正确，结果中没有 timing 内容。
- 焦点：IP address，屏幕读数 [91, 418, 822, 549]；CLI 一像素红框的像素范围与读数精确一致，MCP 加粗焦点框已人工看图核对。
- MCP 截图：Base64 解码、原生图片块、保存 PNG 三者逐字节一致。PNG 为 1920×1080。

## 采集证据及限制

a11y 43 个节点，dumpsys 85 个节点，配对 40 个：R0=1、R1=5、R2=1、R3=33。统一树 81 个节点；visible 摘要 8 项。两次完整采集均 source_consistency.drift=false，表示前后 dumpsys 层次稳定。

geom_drift=34 表示 dumpsys 推导坐标与 a11y 读数的空间差异，不等同于时间上的画面漂移；还保留两个未解释可见候选与两个有歧义而拒绝的顺序配对。本次没有改变这些判定、加偏移或用容差消除差异。

树和截图仍是分次观察；此次画面稳定及各接口结果一致，不代表所有动态屏幕都不会漂移。实验覆盖当前网络详情设置页面，未改变页面去验证其他场景。

## 本地证据

- [完整检查明细](../../_temp/live-cleanup-20261002/summary.json)
- [CLI 完整树](../../_temp/live-cleanup-20261002/cli-full.json)
- [MCP 焦点截图](../../_temp/live-cleanup-20261002/mcp-focus.png)
- [CLI 焦点截图](../../_temp/live-cleanup-20261002/cli-focus.png)
- [MCP stderr](../../_temp/live-cleanup-20261002/mcp-stderr.log)
- [raw 原始捕获目录](../../_temp/live-cleanup-20261002/raw/)：本次原始 dumpsys 与 a11y 捕获

原始实验产物位于 gitignore 的 `_temp/live-cleanup-20261002/`，仅在当前工作区可用，不随仓库提供；长期报告归档于 docs，没有归档设备地址或截图。

## 实验断言修正

初次像素检查得到 42/43：该检查把 CLI 红色说明文字也纳入全图红色像素外接范围，且把 Pillow 外接范围右/下的排他边界当作画框坐标。根因是实验断言口径错误。核对已有 _stroke_rect、CLI show_details 与原 PNG 后，改为逐像素检查四条边恰在读数指定的行/列，及框外相邻像素干净；没有改动生产绘制代码。初测事实和修正原因保留在 summary.json 的 audit_history。
