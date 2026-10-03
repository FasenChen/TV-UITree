# OpenCode 整改计划 Review

> 归档说明（2026-10-03）：本文是实施前对原计划的历史评审，不是对 Zcode 整改后代码的验收。原位置为 `_temp/plan-review-20261002/review.md`。

相关文档：[原计划](../superpowers/plans/2026-10-02-code-review-remediation.md)、[修订交接计划](../superpowers/plans/2026-10-03-code-review-remediation-zcode.md)、[后续交付记录](../reports/2026-10-03-code-review-remediation-delivery.md)、[文档索引](../README.md)。

日期：2026-10-02。审查代码 HEAD：`6d174cd`。对象：`.omo/plans/2026-10-02-code-review-remediation.md` 全文及直接涉及的当前实现、测试和本地金样。

结论：整改方向有价值，但当前计划不能直接执行，需先修正文档中的实现模板、RED 测试及验收步骤。这次仅评审；未修改原计划、生产代码、设备或 config.json，未暂存或提交文件。

## 值得保留的部分

- `Adb.props()` 的静默串位是实在的问题。使用真实方法和脱敏字符串复现：model 空行被过滤后，model 变成 device 的值，后续全部前移，而不会抛异常。保留空行、改用 shell_raw 及校验行数的方向正确；失败使用 AdbError 与 snapshot 的既有降级契约相符。
- observe/tree/visible 的输出写失败缺少接口层处理。对合法输入与不可写目标复现后，应当修正为退出码 2 和友好说明；输出原子替换的目标也合理。
- 重连通过设备状态确认，比仅看 connect 回显可靠。保留现有 heal=False 防递归与单次重试规则。
- T2 标签失败追加 notes 的范围清楚，不改画框几何，正常路径继续保持 notes 不变。
- 取消配置策略、超时架构和 pytest 迁移的混杂，保留顺序任务和每阶段验证，是合理的范围控制。

## 需要修正的项

### 1. P1：T3 RED 初始化立即 AttributeError

位置：计划 508–509 行。当前 json_io 没有 os 属性，测试在进入 try 前读取 json_io.os.replace。已复现 AttributeError，整场自检不会进入失败汇总，与计划的五条 RED 防护规则矛盾。

建议：替换测试已导入的标准库 os.replace，并在 finally 还原；当前实现不调用它时，应以可记录的断言失败结束。不要为使测试可运行提前修改生产代码。

### 2. P1：T4/T5 ADB 假件不遵守真实返回类型

位置：计划 761–771、787、955–957 行及 QA 883、1105 行。真实 _popen 在 binary=False 时返回 (int, str, str)，仅 binary=True 返回 bytes。假件无视 binary，始终返回 bytes。

已复现：T4 首个正常 props 用例发生 TypeError: can't concat str to bytes；T5 回显匹配发生 str/bytes TypeError。按 GREEN 方案，属性值仍会是 bytes，设备状态匹配也不能工作。假件按命令名分派的想法正确，但只解决响应顺序，没有保留类型契约。

建议：假件按 binary 返回对应类型，或者在 subprocess.run 边界模拟结果、保留真实 _popen。同步修正 QA lambda。不得让生产代码增加 bytes 兼容分支来迁就错误假件。

### 3. P2：T1 包名必须有点号会拒绝合法系统组件

位置：计划 302–312 行。android/com.android.internal.app.ResolverActivity 是合法系统组件，包名 android 没有点号；当前函数可解析，候选正则会拒绝。因此“真机 component 包名恒为反向域名”的依据不成立。

官方依据：[AOSP CTS 中对 ResolverActivity 前台组件的检查](https://android.googlesource.com/platform/cts.git/%2B/ced4c21c6da141ef5ca83797c8f2fa923201915c%5E2..ced4c21c6da141ef5ca83797c8f2fa923201915c/#3295)。本地也核对了当前解析结果。

建议：仍需同时修正严格/回退两条匹配路径，但应根据组件与类名的合法结构排除 uid/1000，加入 android 系统组件回归；不能把“包含点号”当作唯一有效依据。

### 4. P2：T3 visible 写失败用例是假阳性

位置：计划 524–533、546–558、561 行。输入只有 tree 和 note，没有有效 screen。select_visible 在访问输出函数前就抛 ValueError，CLI 已返回 2、stderr 非空且无 traceback，故三条断言在未修复输出错误时也已成立。

已复现：无 screen 时 visible 返回 2、无 traceback；补有效 screen 后，同一不可写输出才暴露真正的退出码 1 和 traceback。

建议：给三个命令使用完整有效的 fixture，至少含 screen.width/height；先证明相同输入输出到可写目标可成功，再要求失败 stderr 明确指向写入目标，并检查无成功提示。

### 5. P2：T5 未实现 connect 的异常处理承诺

位置：计划 1066 行，对照 1085、1100 行验收。GREEN 仍裸调用 devices，AdbError 会经 connect_device 和 connect_for_cli 外漏。仓内指定 serial 的正常路径可以到达这处，不能仅因空 serial 不可达而忽略它。

已用脱敏假件验证 devices 超时异常会外漏。

建议：该查询失败时设置 _connected=False 并返回 False，补实际连接失败边界测试；无需改变已指定 serial 的成员匹配策略。

### 6. P2：T5 删除成功重连日志，验收反而要求它

位置：计划 1039–1046、1334 行。替换后的 _reconnect 直接返回状态结果，原有 logging.warning 丢失。已确认正确 str 假件下会返回 True，但没有“已自动重连”日志。

建议：状态确实恢复后保留原成功日志，失败时不报成功。

### 7. P2：当前金样基线不可能满足“零差异”

位置：计划 176–187、703、1329、1422 行。本次重新运行 check 返回 1：14/19 文件完全一致，keep_all.txt、keep_gone.txt、observe.txt、slim.txt、visible.txt 五处仅有上一轮已审查的 UTF-8 字节计数差异。原 JSON/PNG 和其他内容不变。

上一轮明确保留旧 base。因此本计划还未修改任何生产代码，就会被自己的终验规则阻断。

建议：沿用明确限定的五处既有差异审计，并禁止新增差异；或者在独立基线维护步骤备份并逐项审查更新诊断文本。不要运行 make 覆盖全部基线，不要把已知差异算作本次新增回归。

### 8. P2：F3 真机 QA 同时存在错误输入与错误触发阶段

位置：计划 1333–1335 行。

- observe 输出是 tv-observation 摘要，没有 tree。shot --json observe.json 会在读取 JSON 时返回 1，根本不能画框。已通过真实 CLI 和脱敏输入复现。
- 新进程 observe 在 adb disconnect 后通常先执行正常 connect，再开始采集，不能证明已有连接采集中 _popen 的 offline → _reconnect → 单次重试路径被覆盖。

建议：先用 tree --mode full 输出 full.json，shot 使用它。离线重连测试保留真实 _popen 并模拟首次命令离线、connect、devices=device、原命令仅重试一次；真机实验需证明断开发生于连接建立之后，且仅针对指定 TV，避免断开其他会话。

### 9. P1：T7 无条件恢复 config 可能覆盖用户修改

位置：计划 1273–1277 行。仅发现 HEAD 与 config 不一致就要求 git checkout -- config.json，会删除执行前已有的本地设备设置或用户并行修改，与保留无关配置的明确规范冲突。

建议：执行前记录基线，区分本次任务的意外变更与用户已有修改；只修复自己引入的变化。不要执行此恢复命令作为通用验收动作。

### 10. P2：T3 的“全文替换”模板漏了读取函数

位置：计划 567、570–637 行。文字说 load_full_json 保持原样，但完整替换代码并没有它，三个 CLI 又仍导入它。照抄该全文片段会产生 ImportError。

建议：提供局部补丁，或把原 load_full_json 纳入完整模板，使文字和交付代码一致。

### 11. P2：原子性测试没有验证已有目标的保留

位置：计划 500–522、675 行。只测旧目标不存在，无法证明 IS-2“完整旧内容保留”的核心价值。建议增加：目标预先存在，替换失败后旧内容逐字节不变，且临时文件清理；再覆盖写入失败。这是原子写目标的直接需求，不是新增产品功能。

### 12. P2：设备名特判未限定 Windows

位置：计划 588–593、677 行。POSIX 上 NUL、CON.json、COM1.json 是普通文件，此方案也把它们判作设备并绕过原子写。建议 os.devnull 单独处理，Windows 设备名逻辑限定 os.name == nt，测试也按平台区分。当前 Windows 的 NUL 兼容仍应保留。

## 范围与优先级建议

优先实施 props 正确性、输出写失败/原子性、重连状态与异常处理，再处理组件误识别。T2 标签诊断可保留，T6 删除未引用依赖属于卫生整理。空 serial 多设备问题仓内不可达，应保持低优先级；两条 D 盘候选路径的删除需要按实际安装约定判断，不能仅凭盘符把一条定为个人路径、另一条定为通用路径。

七个任务及顺序执行可以保留。四路终验反复批准、按源码措辞/正则字符串计数建立测试，对这批局部修复有较高流程成本；优先检查真实行为和边界，一次集中独立 Review 即可覆盖大部分重复审查。文档中声称的历史授权和 /ulw-execute 指令不构成本次执行授权。

## 本次验证与限制

- 当前 py_compile、pyflakes 通过，完整 selftest 714 条断言通过。
- 当前金样重新 check 返回 1，五处计数差异逐项归一化核对，其余 stdout/stderr/文件集合与 JSON/PNG 字节未变。
- 纯内存/临时脱敏输入复现属性串位、RED 类型失败、visible 假阳性、CLI 输出错误、observe 摘要不能用于 shot。临时 fixture 已清理。
- 两个独立审阅分别核对 ADB 路径与 JSON/组件路径。一路尝试执行直接提取的第三方计划片段被自动审批拒绝，理由是执行不可信代码的副作用风险；该尝试停止，改用源码核对和官方资料，没有要求放宽权限或修改生产代码。
- 本次没有连接、断开或操作 TV，没有重跑整台设备 QA，也没有修复或实施计划。
