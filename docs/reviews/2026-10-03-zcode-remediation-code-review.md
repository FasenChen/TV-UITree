# Zcode 整改代码复审

日期：2026-10-03。审查区间：`6d174cd..45064d0`，当前 HEAD：`45064d04053990c67c87a90104b6a4f660b5d66a`。

结论：部分修复有效，现有离线检查通过；不能据此接受“全部缺陷关闭、终验全部通过”的整体结论。仍存在组件解析回归、连接异常契约未落实、设备名特判的平台问题及新增测试覆盖缺口。此次为只读复审，未修改生产代码、测试或 config.json，未提交或推送。

相关材料：[Zcode 交付声明](../reports/2026-10-03-code-review-remediation-delivery.md)、[实际采用的原计划](../superpowers/plans/2026-10-02-code-review-remediation.md)、[Codex 修订交接计划](../superpowers/plans/2026-10-03-code-review-remediation-zcode.md)、[实施前评审](2026-10-02-code-review-remediation-review.md)。

## 发现

### R1 · P1：窗口解析拒绝合法 android 系统组件

位置：`tvuitree/domain/component.py:18`、`:21`。

修复将包名改为必须至少包含一个点号。因此以下合法组件被解析为 None：

```python
component_from_window("Window{abc u0 android/com.android.internal.app.ResolverActivity}")
# 实际：None
# 应当：android/com.android.internal.app.ResolverActivity
```

[AOSP CTS](https://android.googlesource.com/platform/cts.git/%2B/ced4c21c6da141ef5ca83797c8f2fa923201915c%5E2..ced4c21c6da141ef5ca83797c8f2fa923201915c/) 明确检查该系统组件的前台状态，故“真机包名恒为反向域名”的代码注释不成立。拒绝 uid/1000 应依据组件和类名结构，不能以包名含点号作为唯一条件。

当 mFocusedApp 存在可解析记录时，`window_focus()` 的现有备用来源可能补回组件；因此不能声称该问题在所有系统窗口都会造成选错树。但窗口来源的合法读数已被丢弃；mFocusedApp 缺失或不可解析时，会失去用于 pick_block 的匹配目标并进入回退路径。

建议：同时修正严格和回退路径，保留 android 包；补上述系统组件和纯数字类名用例。当前第 13 段只覆盖带点号包，没有覆盖这个回归。此问题在实施前评审及修订交接计划中已明确提出。

### R2 · P1：connect 查询失败仍以 traceback 和退出码 1 外漏

位置：`tvuitree/infrastructure/adb.py:147`；调用链 `application/connection.py:77` → `interfaces/connection.py:34`。

connect 只捕获了前面的 connect 命令异常，随后 devices 查询仍裸调用。保留真实 `_popen`，仅让底层 subprocess.run 抛 TimeoutExpired，实际子进程结果为：

```text
cli_connection_timeout_process.rc = 1
cli_connection_timeout_process.traceback = true
cli_connection_timeout_process.adb_error = true
```

复现使用已指定的 fixture:5555，并开启 --no-connect；不依赖空 serial 分支，不访问真实设备。该错误应按项目连接失败契约进入退出码 2 通道。

这是原有问题未修复，不是本轮新增回归。但原计划第 1085、1100 行、质量验收第 1316 行均明确要求 connect 不外漏异常，Zcode 的交付和 F4 也声称“全程不抛异常”。F2 又把该行解释为既有非目标，不能同时成立。原计划明确的非目标是“已指定 serial 的成员判据保持不变”，并不是“设备查询异常可外漏”。

建议：devices 查询 AdbError 转为 False，并清理陈旧连接状态；补超时、缺失 adb 和真实 CLI 错误通道用例。无需先改变已指定目标的状态判据才能完成此修复。

### R3 · P2：Windows 设备名规则没有平台边界

位置：`tvuitree/interfaces/json_io.py:20–25`；`tests/selftest_tree.py:2258–2261`。

分类函数无条件把 NUL、CON、COM1 等识别为设备名；新增测试也无条件要求其为 True。POSIX 上这些名字可以是普通文件，当前逻辑会绕过原子替换而直接截断写入，与普通输出文件原子性要求冲突。

本次是 Windows 环境，未声称跑过 Linux 集成；只在分类调用期间模拟 os.name=posix，CON.json 仍被判 True。源码也没有任何平台分支，因此错误的平台适用范围已明确。

建议：os.devnull 单独识别，Windows 保留设备名分支限定 os.name == nt；测试按实际平台区分。保留 Windows --out NUL 的既有兼容用途。

### R4 · P2：visible 写失败测试仍是假阳性

位置：`tests/selftest_tree.py:2251`、`:2269–2281`；实际输入校验 `tvuitree/domain/visible.py:43–47`。

三个命令复用的 _ok_out 只有 tree/note，没有 screen。visible 在输出之前就因输入缺少有效 screen 而返回 2，stderr 非空且无 traceback，恰好满足新增的三条断言。该用例无法证明 visible 的输出异常处理接入正确。

本次分别用相同形状和有效 screen 的输入实测：

| 输入 | rc | 写入错误说明 | screen 输入错误 |
|---|---|---|---|
| 只有 tree/note | 2 | 否 | 是 |
| 增加 width=400、height=300 | 2 | 是 | 否 |

当前 visible 的生产修复实际有效，本次正向写入与失败目标的对照均确认了这一点。问题在于永久回归测试无法锁住它，不能把原用例的全绿当作证明。

建议：使用有效 screen 的 fixture，先确认相同输入可成功输出，再检查失败 stderr 包含“写不了”及目标路径、没有成功摘要。无需降低或删除原断言。

### R5 · P2：新增恢复状态查询忽略命令返回码

位置：`tvuitree/infrastructure/adb.py:111–119`。

新增 _serial_is_device 把设备查询返回码存入 _rc，却不检查它；stdout 中存在 device 行就会返回 True。保留真实 _popen，模拟 devices 返回 `(rc=1, stdout=目标device行, stderr=query failed)`，_reconnect 返回 True 并打印成功日志。

失败的进程输出不应作为“查询成功、恢复已确认”的依据。此复现是标准进程边界的失败响应，未声称真实 TV 本次出现过这种组合。

建议：查询 rc != 0 返回 False，不打印成功恢复日志；补非零返回码伴随部分 stdout 的回归。实际恢复一次、随后原命令最多重试一次的执行链也应在 subprocess.run 边界覆盖，当前新增 ADB 假件重写整个 _popen，不能证明这条执行链。

## 已确认有效的部分

- props 正常空行不串位：中间空值、最后空值及八个值全部为空的脱敏响应均保持位置和字符串类型。
- observe/tree/visible：有效 full JSON 写可用目标均返回 0；写不可用目标均返回 2，明确报告写入失败，无 traceback。
- 普通文件原子替换：已有目标预置完整字节，替换失败及临时文件部分写入失败均保留旧内容；临时文件已清理。当前生产实现通过这些补充复现，但永久测试只覆盖“旧目标不存在”的替换失败，仍需把这两条补入回归。
- 截图标签异常分支追加中文 notes，原有绘制几何没有改动；现有完整自检的像素与正常 notes 用例通过。
- 重连成功日志保留，假件修正了 binary=False 的 str 契约；load_full_json 保留，没有发生早期原计划全文模板导致的导入缺失。
- uiautodev 已从 requirements 删除；提交区间确有 8 个提交，Conventional Commits 格式与 scope 均符合约定。

## 范围差异与交付文字

1. Zcode 执行的是 10-02 原计划，未完成 10-03 修订计划的全部要求。系统包、平台规则、有效 visible fixture 和连接异常等修订没有被落实。
2. 已指定 serial 的 connect 状态仍仅检查是否在列表中；device/offline/unauthorized 三个脱敏清单均返回 True。该行为原计划明确保留，所以此次不作为“违反原计划”的独立发现；修订计划则要求状态确为 device，不能混用两份计划的验收结论。
3. D 盘候选已删除，这是原计划任务范围。是否应仅按盘符认定个人路径仍缺乏业务依据，不能把源码不包含 D 盘字符串当作设备工具正确性的证明；本次不擅自恢复路径。
4. 实际 `git diff 6d174cd..45064d0 --stat` 为 11 文件、+1909/−32，包含归档计划的 +1437。交付说明“同一区间、11 文件、+471/−31”的统计口径不准确，应明确是否排除计划并使用实际统计。
5. F3 的结果是离线通过、真机待补，并不是已完成真机验证；TV 不可达是 Zcode 执行时的记录，本次没有再次探测。三个代理报告 APPROVE 是外部审阅结果，不等于每项边界均被独立证明。
6. golden_equiv.py 对所有 txt 全局替换“（数字 字节）”，不限定五个既有 stderr 行；因此它是放宽后的等效检查，不能称为“严格度不低于零差异”。没有证据表明当前已有其他差异被它掩盖，但该判据可能漏报新数字变化。建议按修订计划保存本次执行前基线，后续逐字节比对。本次没有重新运行第三方金样生成或归一脚本，不宣称金样复验通过。

## 实际验证及证据

本次从仓库根目录使用 `.venv/Scripts/python.exe`，独立执行：

- main.py、tvuitree、tests 全部 Python 文件的 py_compile：通过。
- 相同范围的 pyflakes：通过。
- tests/selftest_tree.py：790 条断言通过，所有分组执行。
- main.py --help、tree --prune-list：通过。
- git diff --check：通过；Git 对已有文档给出的 LF/CRLF 提示不是检查失败。
- 本次编写的隔离复现：ADB subprocess 全部使用标准库替身；真实子进程仅运行离线 from-json CLI 和模拟超时的 CLI 入口。没有连接、断开 TV，没有发送按键。

复现材料仅在本地：[脚本](../../_temp/zcode-review-20261003/reproduce.py)、[结果 JSON](../../_temp/zcode-review-20261003/results.json)。运行：

```powershell
$env:PYTHONUTF8 = '1'
& .\.venv\Scripts\python.exe _temp/zcode-review-20261003/reproduce.py
```

脚本运行成功意味着完成边界检查，不意味着记录中的所有产品行为满足要求；结果 JSON 同时包含已确认通过和已复现失败。临时 fixture 在仓库 _temp 下创建并清理，原始审查结果保留。脚本与 JSON 不随仓库提交。

建议先修复 R1/R2/R3/R5 并补 R4 及已有目标原子性的永久回归，再做一次集中验收；保留此次已验证的有效修复。此次没有授权实施进一步修复。
