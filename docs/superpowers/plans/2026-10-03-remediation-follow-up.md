# 整改复审补修 Implementation Plan

**后续提交授权：** 用户在终验后要求提交并推送至 `origin/main`；代码提交为 `8ca3846`，文档归档另行提交。下列“未暂存、未提交”是实施终验时的历史状态，保留用于区分两个交付阶段。

**执行状态（2026-10-03）：** T0–T6 已实施，864 条自检及静态检查通过，19 个金样文件与当前执行前基线逐字节一致；独立终审的一项测试编码问题已闭环，GBK 环境两次完整自检也通过。HEAD 保持 45064d0，差异未暂存、未提交。真实 MCP stdio 已验证协议与连接失败路径；TV 探测不可达，真机步骤待补。完整结果见 [本轮交付报告](../../reports/2026-10-03-remediation-follow-up-delivery.md)。下文保留原计划步骤，不将未运行的可选验证标成通过。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 用户已选择由 Codex 在当前会话实施；顺序完成任务，不再交给 Zcode，也不自动派发多个实现代理。

**Goal:** 关闭最新代码复审的 R1–R5，补齐普通文件原子性与单次恢复的有效回归，保留本轮已经验证有效的整改。

**Architecture:** 沿用现有分层：组件解析属于 domain，ADB 连接及恢复属于 infrastructure，设备输出分类属于 interfaces。复用现有函数和顺序自检；不创建通用恢复/文件框架，不改 CLI/MCP 数据结构。文件与连接失败继续由既有接口转换为正确退出码。

**Tech Stack:** Python 3.10+、项目 `.venv`、标准库 unittest.mock、ADB、现有 uiautomator2/Pillow/MCP 依赖。

**Spec:** [整改代码复审 R1–R5](../../reviews/2026-10-03-zcode-remediation-code-review.md)，[项目 AGENTS.md](../../../AGENTS.md)。本计划针对当前 `45064d0` 的已实施代码，不重新执行 [10-02 原计划](2026-10-02-code-review-remediation.md) 或 [早期 Zcode 交接计划](2026-10-03-code-review-remediation-zcode.md)。

## Global Constraints

- Python 3.10+、四空格、UTF-8；使用 `.venv/Scripts/python.exe`，不重建环境或全局安装依赖。
- 业务依赖流向保持现状；domain 不访问设备、文件、终端、MCP、Pillow 或 uiautomator2。
- 保持 R0–R3 证据、剪枝 OWNER_PRIORITY、full JSON generator=`tv_tree.py`。
- 截图框等于读数；“不加偏移”“不补偿”，不改坐标、线宽、颜色或焦点推断。
- 用法、文件或连接错误退出码 2；采集错误 3；shot/input 自身失败 1。
- MCP stdout 仅协议，每次调用恰好一个 stderr timing 块，耗时不进入结果。
- config 每次连接读取；显式参数逐字段覆盖。保留用户地址、本地配置及无关修改。
- 新永久回归使用脱敏输入，不连接 TV、不联网；真实设备检查单独记录。
- 长期计划、复审和验收报告存放 docs；原始 JSON/PNG/日志/金样保留 _temp，不提交。
- 不推送、不改写历史、不执行通用 config 回滚、不主动断开设备或发送按键。

## Review Focus

1. 系统包 android 没有点号仍是合法组件；UID 的数字不是类名，T1 锁定。
2. devices 超时、adb 不存在或非零退出码时，连接失败返回 False、CLI 返回 2，T2 锁定。
3. devices 失败时带有部分 stdout 不能证明恢复成功；连续 offline 最多重试一次，T3 锁定。
4. POSIX 的 NUL/CON.json 是普通文件，不能绕过原子写；Windows NUL 兼容保留，T4 锁定。
5. visible 输入须有效再验证输出失败，已有文件须经受部分写入及替换失败，T5 锁定。

## 范围与明确不做事项

| 任务 | 关闭问题 | 最小交付 |
|---|---|---|
| T1 | R1 | 修正窗口严格/回退解析及错误说明，保留系统组件 |
| T2 | R2 | connect 捕获设备查询 AdbError/非零 rc，清除陈旧状态，验证 CLI 错误通道 |
| T3 | R5 | 恢复查询检查 rc，真实 _popen 边界验证单次恢复和日志 |
| T4 | R3 | Windows 设备名限定平台，更新跨平台测试要求 |
| T5 | R4、原子性覆盖缺口 | 修复现有 CLI fixture 与断言，补已有目标的失败原子性 |
| T6 | 交付一致性 | 更新 README、文档索引与本轮验收报告，集中终验 |

本轮不重新修改 props、截图标签绘制、requirements、ADB_CANDIDATES、config 追踪策略。component_from_activity_record 与 normalize_component 不改，R1 只修已确认回归的窗口路径。connect 已指定 serial 的成员判据仍保留；把所有初始连接也改成 device 状态判据属于另外一个行为变更，此次不混入。不会用删除 D 盘路径或源码正则字符串计数来证明功能正确性。

## 文件地图

- 修改 `tvuitree/domain/component.py:component_from_window`：纯窗口组件解析。
- 修改 `tvuitree/infrastructure/adb.py:connect/_serial_is_device`：连接及恢复查询失败边界；_popen 单次恢复结构不改。
- 修改 `tvuitree/interfaces/json_io.py:_is_device_target`：输出设备的平台边界；保留 emit_json/emit_json_checked/load_full_json。
- 修改 `tests/selftest_tree.py`：现有第 15 段 fixture、设备名断言及新增补修组。
- 修改 `README.md`、`docs/README.md`：实际错误契约及报告入口。
- 创建 `docs/reports/2026-10-03-remediation-follow-up-delivery.md`：实施后实际结果，不能预先填写通过。
- 本地证据 `_temp/plan-evidence/remediation-follow-up-20261003/`：不入库。

所有任务串行，T2/T3 共用 adb.py，所有任务共用 selftest。函数名定位优先于历史行号。工作区已有 AGENTS.md、README.md 的文档归档改动，以及未跟踪 `.omo/`、`.zcodeignore`、docs 文档；实施前记录并保留，不混入修复提交。

## T0：执行基线与通用验证

- [ ] 保存 status、HEAD、config 哈希，不记录配置内容：

```powershell
$py = '.\.venv\Scripts\python.exe'
$evidence = '_temp/plan-evidence/remediation-follow-up-20261003'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
git rev-parse HEAD | Set-Content -Encoding utf8 "$evidence/head-before.txt"
git status --short | Set-Content -Encoding utf8 "$evidence/status-before.txt"
(Get-FileHash -LiteralPath config.json -Algorithm SHA256).Hash | Set-Content -Encoding utf8 "$evidence/config-hash-before.txt"
```

- [ ] 建立只限当前任务的检查函数；每个生产任务 GREEN 运行它。RED 则单独运行 selftest 并要求正常失败汇总：

```powershell
function Invoke-RemediationChecks {
    $pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
    & $py -m py_compile $pythonFiles
    if ($LASTEXITCODE -ne 0) { throw 'py_compile failed' }
    & $py -m pyflakes $pythonFiles
    if ($LASTEXITCODE -ne 0) { throw 'pyflakes failed' }
    & $py tests/selftest_tree.py
    if ($LASTEXITCODE -ne 0) { throw 'selftest failed' }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
}
Invoke-RemediationChecks
```

编写计划前的独立复审已确认自检 790 条通过；这是历史事实，执行阶段仍重新运行。最终要求所有原有效断言及新增行为断言成立，不把固定断言数量当作需求。

- [ ] 在自检标准库导入区域新增 `from unittest.mock import patch`。新测试用上下文管理器恢复 patch，预期失败宽捕获后交给 t.ok/t.eq 汇总。除 T5 指定修改，保留原有测试语义；新增段插入“收尾”之前，不迁移到 pytest。

## T1：保留合法系统组件，拒绝 UID

**Files:** Modify `tvuitree/domain/component.py:8–22`；Test `tests/selftest_tree.py`。

**Interfaces:** `component_from_window(text: Optional[str]) -> Optional[str]` 不变，返回原格式 pkg/class；不调用设备，不更改其他两个组件函数。

- [ ] 新增 RED 行为案例：

```python
t.group("补修 T1：系统组件及非类名字段")
for value, expected in [
    (None, None), ("", None),
    ("Window{abc u0 android/com.android.internal.app.ResolverActivity}",
     "android/com.android.internal.app.ResolverActivity"),
    ("mCurrentFocus=android/com.android.internal.app.ResolverActivity",
     "android/com.android.internal.app.ResolverActivity"),
    ("Window{abc u0 com.example/.Main}", "com.example/.Main"),
    ("com.example/com.example.Outer$Inner", "com.example/com.example.Outer$Inner"),
    ("Window{abc u0 uid/1000}", None), ("mCurrentFocus=uid/1000", None),
    ("Window{abc u0 com.example/1000}", None),
    ("noise uid/1000 then com.example/.Main trailing", "com.example/.Main"),
]:
    t.eq(component.component_from_window(value), expected, "窗口组件合法结构")
```

- [ ] Run `& $py tests/selftest_tree.py`。系统包两种形状及数字类名用例应失败，原有第 13 段 UID 用例仍绿；脚本必须正常汇总。
- [ ] 增加一个局部模式常量，替换窗口函数；删除“包名恒为反向域名”的错误解释：

```python
# 系统包 android 合法；类名每段以标识符字符开头，不能是 UID 数字。
_WINDOW_COMPONENT = (r"([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)/"
                     r"(\.?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")

def component_from_window(text: Optional[str]) -> Optional[str]:
    """解析窗口组件，保留系统包并排除 UID 等非类名字段。"""
    if not text:
        return None
    match = re.search(r"\s" + _WINDOW_COMPONENT + r"\}", text)
    if not match:
        match = re.search(r"(?<![\w.$/])" + _WINDOW_COMPONENT + r"(?![\w.$/])", text)
    return f"{match.group(1)}/{match.group(2)}" if match else None
```

- [ ] Run `Invoke-RemediationChecks`。原组件和树配对用例继续通过；不按正则源文本中的量词个数写测试。
- [ ] 完成检查后记录阶段差异；若当前执行授权包含本地提交，使用 `fix(component): 保留系统组件并排除数字类名`，仅包含 component.py 与本任务自检改动。

## T2：连接查询失败进入退出码 2 通道

**Files:** Modify `tvuitree/infrastructure/adb.py:connect`；Test `tests/selftest_tree.py`。核对现有 application/connection.py 与 interfaces/connection.py，不扩展其职责。

**Interfaces:** connect(quiet: bool=False) -> bool；_popen(binary=False) 返回 int/str/str。AdbError 在连接入口消化为 False，再由既有调用链变成 None 与 CLI 2。

- [ ] 新增 RED，保留真实 _popen，仅模拟 subprocess.run；不能用始终 bytes 的 _popen 替身：

```python
t.group("补修 T2：设备查询失败不外漏")
for failure in [subprocess.TimeoutExpired(["adb", "devices"], 20), FileNotFoundError("adb")]:
    review_device = adb.Adb("adb", "fixture:5555", auto_connect=False)
    review_device._connected = True
    with patch.object(adb.subprocess, "run", side_effect=failure):
        try:
            review_result = review_device.connect(quiet=True)
        except Exception as error:
            t.ok(False, "连接异常返回 False", repr(error))
        else:
            t.eq(review_result, False, "连接失败不能报告成功")
    t.eq(review_device._connected, False, "失败清除陈旧连接状态")

    with patch.object(adb.subprocess, "run", side_effect=failure), \
         contextlib.redirect_stdout(io.StringIO()) as review_stdout, \
         contextlib.redirect_stderr(io.StringIO()) as review_stderr:
        try:
            review_rc = cli.main(["observe", "--TV_IP_Address", "fixture", "--port", "5555",
                                  "--no-connect", "--no-color", "--quiet"])
        except Exception as error:
            t.ok(False, "CLI 连接错误不外漏", repr(error))
        else:
            t.eq(review_rc, 2, "CLI 连接错误返回 2")
            t.ok("无法连接" in review_stderr.getvalue(), "CLI 保留中文错误说明")
            t.eq(review_stdout.getvalue(), "", "连接失败不输出观察 JSON")

def review_failed_devices(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, 1,
        b"List of devices attached\nfixture:5555\tdevice\n", b"query failed")

with patch.object(adb.subprocess, "run", side_effect=review_failed_devices):
    review_device = adb.Adb("adb", "fixture:5555", auto_connect=False)
    t.eq(review_device.connect(quiet=True), False, "非零查询退出码不能证明连接成功")
```

- [ ] Run 完整 RED。旧实现异常和非零 rc 断言失败，不得实际访问 ADB。
- [ ] connect 开头插入 `self._connected = False`；仅将原设备查询与 targets 之间的裸调用替换为：

```python
try:
    rc, out, _ = self._popen(["devices"], timeout=20, heal=False)
except AdbError:
    return False
if rc != 0:
    return False
```

已指定目标的成员判据、空 serial 单设备选择、多设备拒绝及 quiet 文案保留。此查询只核验连接，使用 heal=False 避免查询自身递归引发恢复；前面的初始 connect 行为不改。

- [ ] Run `Invoke-RemediationChecks`。既有第 0/8/17 段 CLI/MCP、单/多设备断言继续成立。可在隔离子进程复核同一超时场景，须 rc=2 且无 traceback。
- [ ] 阶段提交信息（仅允许本地提交时）：`fix(adb): 将连接查询失败转换为明确失败状态`。

## T3：恢复查询检查退出码，锁定真实单次恢复链

**Files:** Modify `tvuitree/infrastructure/adb.py:_serial_is_device`；Test `tests/selftest_tree.py`。保留 _reconnect 成功日志和 _popen 的 heal=False 重试结构。

**Interfaces:** _serial_is_device() -> bool，只在查询 rc=0 且目标列为 device 时 True；异常/非零 rc/缺失目标/offline 均 False。

- [ ] 先加非零 rc 的 RED：

```python
t.group("补修 T3：恢复查询成功判据")
def review_reconnect_nonzero(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    if command[3:] == ["connect", "fixture:5555"]:
        return subprocess.CompletedProcess(command, 0, b"connected", b"")
    return subprocess.CompletedProcess(command, 1,
        b"List of devices attached\nfixture:5555\tdevice\n", b"query failed")

review_device = adb.Adb("adb", "fixture:5555")
with patch.object(adb.subprocess, "run", side_effect=review_reconnect_nonzero), \
     patch.object(adb.logging, "warning") as review_warning:
    t.eq(review_device._reconnect(), False, "恢复查询失败不能判成功")
    t.eq(review_warning.call_count, 0, "查询失败不打印恢复成功日志")
t.eq(review_device._healing, False, "失败后恢复防递归标志")
```

- [ ] Run RED。旧实现返回 True 且 warning=1，两个断言应失败。
- [ ] _serial_is_device 中 `_rc` 改为 `rc`，在异常处理之后、遍历设备清单之前新增：

```python
if rc != 0:
    return False
```

- [ ] 补真实 _popen 链的永久回归。它是已有保证的覆盖补强，加入时可能全部通过，不伪造 RED：

```python
for review_mode in ["restored", "still_offline", "retry_offline"]:
    review_calls: list[list[str]] = []
    def review_heal_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        args = command[3:]
        review_calls.append(args)
        if args == ["shell", "echo ok"]:
            if review_calls.count(args) == 1 or review_mode == "retry_offline":
                return subprocess.CompletedProcess(command, 1, b"", b"device offline")
            return subprocess.CompletedProcess(command, 0, b"ok\n", b"")
        if args == ["connect", "fixture:5555"]:
            return subprocess.CompletedProcess(command, 0, b"connected", b"")
        if args == ["devices"]:
            state = "offline" if review_mode == "still_offline" else "device"
            return subprocess.CompletedProcess(command, 0,
                f"List of devices attached\nfixture:5555\t{state}\n".encode(), b"")
        raise AssertionError(f"意外的 ADB 命令：{args!r}")
    review_device = adb.Adb("adb", "fixture:5555")
    with patch.object(adb.subprocess, "run", side_effect=review_heal_run), \
         patch.object(adb.logging, "warning") as review_warning:
        review_rc, review_out, review_err = review_device._popen(["shell", "echo ok"])
    t.eq(review_rc, 0 if review_mode == "restored" else 1, "原命令返回实际恢复结果")
    t.eq(review_calls.count(["shell", "echo ok"]), 1 if review_mode == "still_offline" else 2,
         "成功只重试一次，恢复失败不重试")
    t.eq(review_calls.count(["connect", "fixture:5555"]), 1, "仅一次恢复连接")
    t.eq(review_calls.count(["devices"]), 1, "仅一次恢复状态查询")
    t.eq(review_warning.call_count, 0 if review_mode == "still_offline" else 1,
         "成功确认连接后才打印恢复日志")
    t.eq(review_device._healing, False, "恢复链结束后解除标志")
```

retry_offline 表示设备查询当时恢复，随后原命令又失败；成功日志只描述连接恢复，不承诺原命令成功。不要为取得日志断言绿色擅改既有语义。

- [ ] Run `Invoke-RemediationChecks`。确认执行的是实际 _popen，不是旧 _FakeAdbPopen 重写方法。
- [ ] 阶段提交信息：`fix(adb): 拒绝失败的恢复查询并锁定单次重试`。

## T4：设备名特判限定 Windows

**Files:** Modify `tvuitree/interfaces/json_io.py:_is_device_target`；Test `tests/selftest_tree.py:2258–2263` 及新增组。

**Interfaces:** _is_device_target(out_path: str) -> bool 保持私有分类用途；emit_json 的普通文件原子写不变，Windows NUL 和实际 os.devnull 继续直写。

- [ ] RED：只在纯分类调用期间模拟平台；模拟期间不创建 Path、不访问真实设备文件：

```python
t.group("补修 T4：设备名的平台边界")
for review_platform in ["nt", "posix"]:
    with patch.object(json_io.os, "name", review_platform):
        for review_name in ["NUL", "CON.json", "COM1.json", "LPT1"]:
            t.eq(json_io._is_device_target(review_name), review_platform == "nt",
                 "保留设备名只属于 Windows")
t.eq(json_io._is_device_target(os.devnull), True, "实际平台的空设备保持兼容")
```

- [ ] Run 完整 RED。posix 四条断言失败，Windows 和 devnull 继续绿；这是平台分支模拟，不称为 Linux 真机验收。
- [ ] 仅在现有函数的 os.devnull 判断之后增加平台条件：

```python
if os.name != "nt":
    return False
```

- [ ] 同步修正现有无条件设备名断言，保留普通文件案例：

```python
_is_dev = getattr(json_io, "_is_device_target", lambda _p: False)
t.ok(_is_dev(os.devnull), "os.devnull 被识别为设备目标")
for _dev in ["NUL", "CON", "PRN", "AUX", "COM1", "LPT1"]:
    t.eq(_is_dev(_dev), os.name == "nt", f"{_dev} 的设备语义受平台限定")
```

- [ ] 实际宿主为 POSIX 时增加真实同名文件路径，用 wraps=os.replace 检查 CON.json 走替换一次；Windows 时不创建这样的文件：

```python
if os.name != "nt":
    review_posix_path = Path(TD) / "CON.json"
    with patch.object(json_io.os, "replace", wraps=json_io.os.replace) as review_replace:
        with contextlib.redirect_stderr(io.StringIO()):
            json_io.emit_json({"tree": []}, str(review_posix_path))
    t.eq(review_replace.call_count, 1, "POSIX 同名普通文件使用原子替换")
```

- [ ] Run `Invoke-RemediationChecks`；Windows 可离线运行 observe --from-json 有效full --out NUL 作兼容冒烟，不新增生产回退分支。
- [ ] 阶段提交信息：`fix(json): 将保留设备名限制在 Windows 平台`。

## T5：修复输出用例的假阳性，补已有目标的原子性

**Files:** Modify `tests/selftest_tree.py:第15段`；不更改已经通过补充复现的 emit_json、三个 CLI 或 visible 的业务逻辑。

**Interfaces:** 输入 full JSON 必须包含 tree 列表及正整数 screen.width/height；emit_json_checked 失败返回 2、stderr 含目标说明，成功返回 None。

- [ ] 首先在第 15 段现有 CLI for 循环前插入路径覆盖 RED，使用原 _ok_out，明确证明旧测试没进入输出。该测试只调 CLI，输入是本地 JSON：

```python
with patch.object(visible_interface, "emit_json_checked", wraps=json_io.emit_json_checked) as review_emit, \
     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    review_visible_rc = cli.main(["visible", "--from-json", str(_ok_out),
                                  "--out", _bad_out, "--no-color", "--quiet"])
t.eq(review_emit.call_count, 1, "visible 写失败用例必须到达输出边界")
t.eq(review_visible_rc, 2, "有效输入的输出失败返回 2")
```

- [ ] Run RED：旧 fixture 的 call_count=0，应失败；这次 RED 是暴露测试路径错误，不是伪造新的产品缺陷。
- [ ] 创建独立有效 fixture，不改原 UTF-8 序列化测试的数据与期望。将上面 probe 以及三命令 for 的输入统一换成 review_valid_full：

```python
review_valid_full = Path(TD) / "review_valid_full.json"
review_valid_full.write_text(json.dumps({"tree": [], "screen": {"width": 400, "height": 300}},
                                        ensure_ascii=False), encoding="utf-8")
with patch.object(visible_interface, "emit_json_checked", wraps=json_io.emit_json_checked) as review_emit, \
     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    review_visible_rc = cli.main(["visible", "--from-json", str(review_valid_full),
                                  "--out", _bad_out, "--no-color", "--quiet"])
t.eq(review_emit.call_count, 1, "visible 写失败用例必须到达输出边界")
t.eq(review_visible_rc, 2, "有效输入的输出失败返回 2")
```

- [ ] 用下列完整循环替换第 15 段原三命令循环（新增 imports 已在 T0）。同一有效输入先输出成功，再要求输出阶段失败；三条原断言的含义都保留并加强：

```python
for review_args in [["observe"], ["visible"], ["tree", "--mode", "slim"]]:
    review_output = Path(TD) / (review_args[0] + "_valid_output.json")
    for review_target, review_expected in [(str(review_output), 0), (_bad_out, 2)]:
        review_proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "main.py"), *review_args,
             "--from-json", str(review_valid_full), "--out", review_target, "--no-color", "--quiet"],
            cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        t.eq(review_proc.returncode, review_expected, "有效输入的输出退出码")
        t.ok("Traceback" not in review_proc.stderr, "输出失败无 traceback")
        if review_expected == 0:
            t.ok(review_output.exists(), "正向对照实际生成文件")
        else:
            t.ok("写不了" in review_proc.stderr and review_target in review_proc.stderr,
                 "失败明确指向写入目标")
            t.ok("screen.width" not in review_proc.stderr, "不是输入校验提前失败")
            t.ok("[out] 已写入" not in review_proc.stderr and "[observe]" not in review_proc.stderr
                 and "[visible]" not in review_proc.stderr and "[tree]" not in review_proc.stderr,
                 "输出失败后没有成功摘要")
```

- [ ] 增加旧目标失败保留回归。这两种行为已经在本次复审补充验证通过，所以加入永久自检时应直接绿，不为了宣称 RED 改坏实现：

```python
t.group("补修 T5：已有目标的失败原子性")
review_atomic = Path(TD) / "review_atomic"
review_atomic.mkdir()
review_existing = review_atomic / "existing.json"
review_old_bytes = b"previous complete content\n"
review_existing.write_bytes(review_old_bytes)
review_names = {p.name for p in review_atomic.iterdir()}
with patch.object(json_io.os, "replace", side_effect=OSError("injected replace failure")):
    try:
        json_io.emit_json({"tree": []}, str(review_existing))
    except Exception as error:
        t.ok(isinstance(error, OSError), "替换失败仍抛 OSError", repr(error))
    else:
        t.ok(False, "替换失败必须被报告")
t.eq(review_existing.read_bytes(), review_old_bytes, "替换失败旧字节保持完整")
t.eq({p.name for p in review_atomic.iterdir()}, review_names, "替换失败临时文件清理")

review_fdopen = os.fdopen
def review_partial_writer(fd: int, *args, **kwargs):
    opened = review_fdopen(fd, *args, **kwargs)
    class PartialWriter:
        def __enter__(self) -> PartialWriter:
            return self
        def write(self, text: str) -> None:
            opened.write(text[:1])
            raise OSError("injected partial write")
        def __exit__(self, exc_type, exc, traceback) -> None:
            opened.close()
    return PartialWriter()

with patch.object(json_io.os, "fdopen", side_effect=review_partial_writer):
    try:
        json_io.emit_json({"tree": []}, str(review_existing))
    except Exception as error:
        t.ok(isinstance(error, OSError), "部分写入失败仍抛 OSError", repr(error))
    else:
        t.ok(False, "部分写入失败必须被报告")
t.eq(review_existing.read_bytes(), review_old_bytes, "部分写入失败旧字节保持完整")
t.eq({p.name for p in review_atomic.iterdir()}, review_names, "部分写入失败临时文件清理")
```

- [ ] Run `Invoke-RemediationChecks`。如果这些原子性用例意外失败，先按真实契约定位实现，不以删除断言或增加无关回退处理解决。
- [ ] 阶段提交信息：`test(cli): 验证真实输出失败及已有文件的原子性`，仅包含自检本任务差异。

## T6：文档与集中终验

**Files:** README.md、docs/README.md、新建 docs/reports/2026-10-03-remediation-follow-up-delivery.md。保持旧 Zcode 报告为历史声明，不把本轮结果冒充它的原执行结果。

- [ ] 修正 README 既有退出码说明，用如下文字替换错误句子：

```text
observe、tree、visible 的用法、文件或连接错误返回退出码 2；连接后的采集失败返回 3。shot 和 input 自身失败返回 1，连接失败返回 2。
```

- [ ] 将原子写的范围限定为普通文件，并明确 NUL 例外：

```text
--out 写普通 JSON 文件时先写同目录临时文件再替换目标；写入或替换失败时旧文件保持完整，临时文件清理。设备输出（如 Windows NUL、os.devnull）直接写入，不提供普通文件的原子替换保证。
```

- [ ] 更新 docs/README.md，列入本文及新的验收报告。报告包含实际基线与最终 HEAD、文件边界、R1–R5 证据表、真实断言总数、金样/真机/MCP 分别状态、未运行检查及原因、配置哈希保护结果。不要预填写 APPROVE 或固定断言数。
- [ ] 最终运行 `Invoke-RemediationChecks`，再运行 help/prune-list；所有结果记录真实退出码：

```powershell
& $py main.py --help
if ($LASTEXITCODE -ne 0) { throw 'help failed' }
& $py main.py tree --prune-list
if ($LASTEXITCODE -ne 0) { throw 'prune list failed' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
```

- [ ] 集中核对差异：只修改任务文件；既有属性及标签修复保留、组件备用来源仍存在、CLI/MCP schema 和 timing 不变。核对每个问题能对应到具体行为断言，不再依据源码词语计数作功能验收。
- [ ] 比对 config SHA256；变化时判断是否属于用户并行修改，不执行 git restore/checkout config。保留 `.omo/`、`.zcodeignore` 与先前文档整理差异。

## 金样与真实环境规则

旧 base 不是本轮当前基线；不运行 make，不以全局替换数字的 golden_equiv.py 声称严格等价。

- [ ] 若本地 golden/raw/e2e 素材存在，执行前核对 _temp/golden/now 只包含该工具产物，然后生成一次当前输出，审查旧差异并把当前 now 复制到新的执行证据 baseline；后续比较 now 与这份 baseline 的文件集合及每个文件原始字节。若 now 中混有用户资料，不让工具清理它。
- [ ] 审查或生成工具脚本后才运行；旧 check=1 的原因逐项说明，不能把任意差异自动归为既有。缺失素材时记录具体缺项；不宣称未跑的金样通过。
- [ ] T0 在生产代码修改前运行以下基线动作；先完成上面的目录与脚本审查。若本地素材缺失则明确跳过，不运行这段。该操作建立新的当前输出基线，不改旧 base：

```powershell
$env:PYTHONUTF8 = '1'
& $py _temp/golden/golden.py check
$legacyCheckRc = $LASTEXITCODE
if ($legacyCheckRc -notin @(0, 1)) { throw '金样工具异常退出' }
# 对 rc=1 的实际差异逐项审查，确认来源后才执行下面的复制；不能直接接受任意差异。
$currentBaseline = Join-Path $evidence 'baseline'
if (Test-Path -LiteralPath $currentBaseline) { throw '当前执行基线已存在，先核对续跑状态，禁止覆盖' }
New-Item -ItemType Directory -Path $currentBaseline | Out-Null
Get-ChildItem -LiteralPath '_temp/golden/now' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $currentBaseline
}
Get-ChildItem -LiteralPath $currentBaseline -File | Get-FileHash -Algorithm SHA256 |
    Select-Object Path, Hash | ConvertTo-Json | Set-Content -Encoding utf8 "$evidence/baseline-hashes.json"
```

终验在相同 PYTHONUTF8 环境重跑 `& $py _temp/golden/golden.py check`，核对真实退出码仍只为 0/1、文件存在且各 CLI 记录返回 0，再运行下面的当前基线精确比较。首次执行基线的各命令记录也必须 rc=0，不能冻结一个已经失败的输出作为金样。
- [ ] 通过的精确比较命令：

```powershell
& $py -c 'from pathlib import Path; import sys; a=Path(sys.argv[1]); b=Path(sys.argv[2]); assert {p.name for p in a.iterdir()} == {p.name for p in b.iterdir()}; changed=[p.name for p in a.iterdir() if p.read_bytes() != (b/p.name).read_bytes()]; assert not changed, changed; print("当前基线无新增差异")' "$evidence/baseline" '_temp/golden/now'
if ($LASTEXITCODE -ne 0) { throw '金样出现新差异' }
```

- [ ] 真实设备沿用用户之前的只读实验授权，执行时核对当前配置和 devices；设备可用时捕获 full JSON 与截图，再离线生成 observe/visible。shot 输入必须是 full JSON。所有产物位于本轮 _temp 证据目录，不改变配置、页面或按键。
- [ ] 设备不可达时记录未完成真机验证，不阻碍离线修复，但不得写成“真机已通过”。不主动 disconnect 制造故障；T3 已在真实 subprocess 边界确定性验证恢复执行链。
- [ ] 已有自检覆盖 MCP 接口和耗时；若有可用真实 stdio 宿主，补协议调用。没有宿主时报告仅完成离线覆盖，不把直接函数调用称作真实 MCP 协议测试。

## 提交与交付

用户本次明确指定实施者，未指定 push/merge 或历史改写。默认不自动暂存/提交；若执行阶段用户授权本地提交，采用下表范围，并在每次提交前检查 staged diff、help/prune-list 和 diff-check，严禁 git add .。README/AGENTS 的既有归档改动不得混入补修提交。

| 阶段 | 可提交文件 | Conventional Commit |
|---|---|---|
| T1 | component.py、当前任务自检差异 | fix(component): 保留系统组件并排除数字类名 |
| T2 | adb.py、当前任务自检差异 | fix(adb): 将连接查询失败转换为明确失败状态 |
| T3 | adb.py、当前任务自检差异 | fix(adb): 拒绝失败的恢复查询并锁定单次重试 |
| T4 | json_io.py、当前任务自检差异 | fix(json): 将保留设备名限制在 Windows 平台 |
| T5 | 自检当前任务差异 | test(cli): 验证真实输出失败及已有文件的原子性 |
| T6 | 本轮新增/修改的文档差异 | docs(remediation): 记录补修行为与实际验收 |

如需暂存同一文件的部分差异，先审查再按块处理；不能为了方便提交回滚用户修改。无提交授权时以完整 diff 和验收报告交付，不反复询问提交权限。

## 自审与实施交接

- [ ] 逐项确认 R1–R5 与五项 Review Focus 均有任务及测试对应。
- [ ] 所有代码片段语法可解析，文件和相对链接存在；没有占位步骤。
- [ ] 测试替身位于真实契约边界；纯覆盖补强不伪造 RED；坏 fixture 的 RED 验证其路径。
- [ ] 先前文档整理改动保留，生产文件未在计划编写阶段修改。
- [ ] 执行方式已保存为 Codex 本会话顺序实施。按用户指定 writing-plans 的交接要求，先呈现完整计划供确认，收到计划反馈后使用 executing-plans；不再次要求选择执行方式。
