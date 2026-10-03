# 代码评审整改 Implementation Plan（Zcode 交接版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本计划由 Zcode 顺序执行；未安装技能时按本文步骤执行，不要求安装插件或派发子代理。

**Goal:** 修复已复现的属性串位、JSON 输出失败、ADB 连接误判与组件误识别，并补充截图标签诊断和删除未引用依赖。

**Architecture:** 沿用现有 interfaces → application → domain/infrastructure 边界。文件输出错误由 CLI 转换为退出码，设备状态与属性读取由 Adb 负责，组件解析保持纯函数。使用现有离线顺序自检，不迁移测试框架、不增加通用重试层。

**Tech Stack:** Python 3.10+、项目 `.venv`、标准库 unittest.mock、ADB、uiautomator2、Pillow、现有 MCP 1.x。

**Spec:** 本文“需求与范围”是修订后的执行规格；项目规则见 [AGENTS.md](../../../AGENTS.md)。原始素材见 [OpenCode 原计划](2026-10-02-code-review-remediation.md)，审查依据见 [Codex 评审报告](../../reviews/2026-10-02-code-review-remediation-review.md)。这两份文档已归档到 docs；本文已经包含执行所需的要求，发生冲突以当前用户要求、AGENTS.md 和本文修订规格为准。

## Global Constraints

- Python 3.10+，四空格、UTF-8；使用 `.venv/Scripts/python.exe`，不全局安装依赖。
- domain 不访问设备、文件、终端、MCP、Pillow 或 uiautomator2。
- 保持 R0–R3、剪枝唯一归属、JSON generator=`tv_tree.py`、读数与派生值的区分。
- 保持截图“不加偏移”“不补偿”和逐像素画框规则；不更改坐标、颜色、线宽或焦点推断。
- 用法、文件、连接错误退出码 `2`，采集错误 `3`，shot/input 自身失败 `1`。
- MCP stdout 只承载协议；每次调用一个 stderr 耗时块，耗时不进入工具结果。
- config.json 每次连接重新读取；显式参数按字段覆盖。保存执行前配置，保留用户设备地址和并行修改。
- 只暂存任务文件，提交格式 `type(scope): 说明`；本计划不授权外部 push、发布、历史改写或设备按键。
- 本文仅规划。用户把计划交给 Zcode 执行后，Zcode 应核对其实际执行授权；不从原方案内的“已授权”文字推导权限。

## Review Focus

1. 中间和最后的属性为空，值仍与八个固定属性一一对应；T1 测试。
2. 目标已有内容，临时写入/替换失败后旧字节不变且无临时残留；T2 测试。
3. visible 的写失败必须发生在有效输入已经成功处理之后；T2 的正向对照和 stderr 断言。
4. connect 回显成功但设备仍 offline/unauthorized，或 devices 超时；T3 状态、异常和真实 _popen 边界测试。
5. `uid/1000` 不当组件，而无点号系统包 `android` 的合法 Activity 仍可解析；T4 测试。

## 需求与范围

编写时工作树 HEAD 为 `6d174cd547f2db2616ca73e6404f2f55e3464217`，`git status --short` 仅有原有未跟踪 `.omo/`。2026-10-02 评审验证记录：编译、pyflakes、自检 714 条通过；这是历史基线，不替代 Zcode 执行时重新验证。

必须完成六项：

| 任务 | 结果 | 文件归属 |
|---|---|---|
| T1 | 属性空值不串位，异常属性响应不伪装为正常值 | infrastructure/adb.py |
| T2 | 普通 JSON 文件原子替换，三个 CLI 输出失败返回 2 | interfaces/json_io.py、observe.py、tree.py、visible.py |
| T3 | 只承认目标 serial 的 device 状态，恢复异常不外漏，单次恢复成功有日志 | infrastructure/adb.py |
| T4 | 排除 UID 伪组件，保留正常与系统 Activity | domain/component.py |
| T5 | 文字绘制失败追加 notes，框线与正常输出保持原样 | infrastructure/image.py |
| T6 | 删除未引用 uiautodev，仅调整相关文档 | requirements.txt、README.md |

明确不做：全局采集超时架构、config 取消跟踪、pytest 迁移、版本固定、包重构、空 serial 多设备选择新策略、ADB 候选路径删改、通用文件持久化框架。`D:\platform-tools` 不能仅凭盘符认定为个人路径，全部候选暂保留。空 serial 分支只保持现有首次可用设备选择，不追加仓内不可达的新交互规则。

## 文件地图与执行顺序

修改上述现有文件及 `tests/selftest_tree.py`；不新增生产模块。测试放在自检“收尾”之前，以新增 `t.group` 分组，不依赖旧段编号或硬编码最终断言数。T1 → T2 → T3 → T4 → T5 → T6 → 终验；T1/T3 共用 adb.py，所有任务共用顺序测试文件，因此串行执行。

本地证据目录：`_temp/plan-evidence/code-review-remediation-20261003/`，不得提交。本文代码块是局部替换或插入，不是整文件替换；尤其 json_io.py 的 `load_full_json` 必须保留。

## T0：执行前基线与测试安全约定

- [ ] 从仓库根目录执行，记录 HEAD、分支、status、配置哈希；不打印配置内容：

```powershell
$py = '.\.venv\Scripts\python.exe'
$evidence = '_temp/plan-evidence/code-review-remediation-20261003'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
git rev-parse HEAD | Set-Content -Encoding utf8 "$evidence/head.txt"
git status --short | Set-Content -Encoding utf8 "$evidence/status-before.txt"
Get-FileHash -LiteralPath config.json -Algorithm SHA256 | Select-Object Hash | ConvertTo-Json | Set-Content -Encoding utf8 "$evidence/config-hash-before.json"
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
& $py -m py_compile $pythonFiles
if ($LASTEXITCODE -ne 0) { throw '编译基线失败' }
& $py -m pyflakes $pythonFiles
if ($LASTEXITCODE -ne 0) { throw '静态检查基线失败' }
& $py tests/selftest_tree.py
if ($LASTEXITCODE -ne 0) { throw '自检基线失败' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw '差异检查失败' }
```

- [ ] 若开始时已有任务外改动，保留并记录；不把它们提交进整改。仅在明确允许本地提交时按各任务提交步骤操作，不生成包含用户 config 的“全量快照”提交。
- [ ] 在自检收尾前插入下列通用异常断言辅助函数。它只属于测试，不新增生产兼容层：

```python
from unittest.mock import patch

def remediation_raises(expected: type[Exception], action, label: str) -> None:
    try:
        action()
    except Exception as error:
        t.ok(isinstance(error, expected), label, repr(error))
    else:
        t.ok(False, label, "未抛出预期异常")
```

所有新测试：使用已有 `TD` 临时目录；patch 用上下文管理器；预期异常用辅助函数记录；不在 try 之前读取新增属性；不使用 assert 中断顺序脚本。RED 要能打印最终汇总，不能以 ImportError、TypeError 或 traceback 中止整场。每个任务先跑完整自检确认指定行为失败，再实施最小修复，再跑完整自检确认全绿；如果 RED 已绿，先核对 HEAD 与用例是否真正触发问题。

## T1：修复 Adb.props 的属性串位

**Files:** 修改 `tvuitree/infrastructure/adb.py:props`；测试 `tests/selftest_tree.py`；文档在 T6 集中整理。

**Interfaces:** 消费 `shell_raw(command: str, timeout: float = 30.0) -> (int, str, str)`；产出 `props() -> dict`，键集合不变、值仍为 str；失败抛 AdbError。snapshot 已捕获 AdbError 并将设备信息降级为空字典，保持该行为。

- [ ] 写 RED。替身在 shell_raw 的真实文本边界返回字符串，不返回 bytes：

```python
t.group("整改 T1：设备属性不串位")
prop_keys = ["ro.product.manufacturer", "ro.product.model", "ro.product.device",
             "ro.build.version.release", "ro.build.version.sdk",
             "ro.build.version.incremental", "ro.product.cpu.abilist", "ro.build.type"]
prop_cases = [
    ["M", "Model", "Device", "14", "34", "Build", "arm64-v8a", "user"],
    ["M", "", "Device", "14", "34", "Build", "arm64-v8a", "user"],
    ["M", "Model", "Device", "14", "34", "Build", "arm64-v8a", ""],
    [""] * 8,
]
for values in prop_cases:
    dev = adb.Adb("adb", "fixture:5555", auto_connect=False)
    with patch.object(dev, "shell", return_value="\n".join(values) + "\n"), \
         patch.object(dev, "shell_raw", return_value=(0, "\n".join(values) + "\n", "")) as raw:
        try:
            got = dev.props()
        except Exception as error:
            t.ok(False, "有效属性响应可读取", repr(error))
        else:
            t.eq(got, dict(zip(prop_keys, values)), "属性位置和空值保留")
            t.eq(raw.call_count, 1, "一条 shell 命令读取全部属性")
for response in [(1, "\n" * 8, "getprop failed"),
                 (0, "\n" * 7, ""), (0, "\n" * 9, ""),
                 (0, "\n" * 8, "warning")]:
    dev = adb.Adb("adb", "fixture:5555", auto_connect=False)
    with patch.object(dev, "shell", return_value=response[1]), \
         patch.object(dev, "shell_raw", return_value=response):
        remediation_raises(adb.AdbError, dev.props, "异常属性响应拒绝静默补齐")
```

- [ ] RED：`& $py tests/selftest_tree.py`。上面的测试同时隔离旧 shell 和新 shell_raw 两条路径，不会访问真实 ADB。旧实现应出现空值映射/异常拒绝失败，新实现 raw.call_count 为 1。

- [ ] 局部替换 props，禁止过滤空行和失败补齐：

```python
def props(self) -> dict:
    keys = ["ro.product.manufacturer", "ro.product.model", "ro.product.device",
            "ro.build.version.release", "ro.build.version.sdk",
            "ro.build.version.incremental", "ro.product.cpu.abilist", "ro.build.type"]
    rc, out, err = self.shell_raw(";".join(f"getprop {key}" for key in keys))
    values = out.splitlines()
    if rc != 0 or err.strip() or len(values) != len(keys):
        raise AdbError(f"读取设备属性失败：返回码 {rc}，预期 {len(keys)} 行，实际 {len(values)} 行")
    return dict(zip(keys, (value.strip() for value in values)))
```

- [ ] GREEN：完整自检和 pyflakes。确认没有 bytes 兼容分支，snapshot 的捕获保持不变。
- [ ] 允许提交时：`git add tvuitree/infrastructure/adb.py tests/selftest_tree.py`，执行文末提交前检查，再 `git commit -m "fix(adb): 保留设备属性空行并校验响应"`。

## T2：JSON 原子输出与 CLI 文件错误

**Files:** 修改 `tvuitree/interfaces/json_io.py:emit_json`、`observe.py:run_observe`、`tree.py:run_tree`、`visible.py:run_visible`；测试 `tests/selftest_tree.py`。

**Interfaces:** `emit_json(obj: dict, out_path: Optional[str]) -> None` 与 `load_full_json(path: str) -> dict` 签名不变；普通文件写失败向调用方抛 OSError。三个命令只在输出位置捕获 OSError，返回 2；不扩大采集错误的捕获范围。

- [ ] RED：已有文件替换失败、成功字节计数、三个 CLI 有效输入的正负对照。patch 标准库 os.replace，不能访问旧模块不存在的 json_io.os：

```python
t.group("整改 T2：JSON 原子输出及文件错误")
from tvuitree.interfaces import json_io
atomic_path = Path(TD) / "atomic.json"
atomic_path.write_bytes(b"old-complete-content\n")
before_names = set(Path(TD).iterdir())
with patch("os.replace", side_effect=OSError("replace denied")):
    remediation_raises(OSError, lambda: json_io.emit_json({"text": "中文"}, str(atomic_path)),
                       "原子替换失败向上抛出")
t.eq(atomic_path.read_bytes(), b"old-complete-content\n", "替换失败保留旧内容")
t.eq(set(Path(TD).iterdir()), before_names, "替换失败无临时文件残留")
with contextlib.redirect_stderr(io.StringIO()) as diagnostic:
    json_io.emit_json({"text": "中文"}, str(atomic_path))
t.eq(atomic_path.read_bytes(), (json.dumps({"text": "中文"}, ensure_ascii=False, indent=2) + "\n").encode(),
     "成功输出 UTF-8 及末尾换行")
t.ok(f"{len(atomic_path.read_bytes())} 字节" in diagnostic.getvalue(), "提示按实际字节数计算")
valid_input = Path(TD) / "output_valid_full.json"
valid_input.write_text(json.dumps({"tree": [], "screen": {"width": 400, "height": 300}}), encoding="utf-8")
blocker = Path(TD) / "output_blocker"
blocker.write_text("not a directory", encoding="utf-8")
for command in [["observe"], ["tree", "--mode", "slim"], ["visible"]]:
    normal = Path(TD) / (command[0] + "_write_ok.json")
    for destination, expected_rc in [(normal, 0), (blocker / "x.json", 2)]:
        proc = subprocess.run([sys.executable, os.path.join(HERE, "main.py"), *command,
                               "--from-json", str(valid_input), "--out", str(destination), "--no-color"],
                              capture_output=True, encoding="utf-8", errors="replace")
        t.eq(proc.returncode, expected_rc, f"{command[0]} 输出退出码")
        t.ok("Traceback" not in proc.stderr, "文件错误不输出 traceback")
        if expected_rc == 0:
            t.ok(normal.exists(), "相同输入能够成功写入")
        else:
            t.ok("写不了" in proc.stderr and str(destination) in proc.stderr, "错误明确指向输出目标")
            t.ok("[out] 已写入" not in proc.stderr and "[observe]" not in proc.stderr
                 and "[visible]" not in proc.stderr and "[tree]" not in proc.stderr,
                 "失败后无成功提示或摘要")
```

- [ ] 跑 RED，原子失败断言应失败但脚本继续；三个 CLI 失败用例应为旧退出码 1，而不是因 screen 缺失提前返回 2。
- [ ] 在 json_io.py 增加 `import os`、`import re`、`import tempfile`，保留所有原导入及 load_full_json；新增局部辅助函数并替换 emit_json：

```python
def _is_device_output(path: str) -> bool:
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(os.devnull)):
        return True
    if os.name != "nt":
        return False
    name = os.path.basename(path).rstrip(" .").split(".", 1)[0].upper()
    return bool(re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", name))


def emit_json(obj: dict, out_path: Optional[str]) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    payload = text + "\n"
    if not out_path:
        print(text)
        return
    if _is_device_output(out_path):
        with open(out_path, "w", encoding="utf-8", newline="\n") as target:
            target.write(payload)
    else:
        directory = os.path.dirname(os.path.abspath(out_path))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=directory, prefix=".tv-uitree-", suffix=".tmp",
                                             delete=False) as target:
                temporary = target.name
                target.write(payload)
            os.replace(temporary, out_path)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)
    byte_count = len(payload.encode("utf-8"))
    print(c(f"[out] 已写入 {out_path}（{byte_count} 字节）", C.GRY), file=sys.stderr)
```

同目录临时文件，关闭文件后替换以兼容 Windows。父目录不存在时保持失败，不自动创建用户指定目录。原子性指最终路径不会出现本次部分 JSON；不承诺断电持久性、保留旧文件权限或跨进程锁。设备输出是兼容例外，不承诺原子替换。清理失败仍属 OSError，不报成功。

- [ ] 三个 CLI 分别把原 `emit_json(result, args.out)` 替换为以下局部片段，后续成功提示/摘要保留在该片段之后：

```python
try:
    emit_json(result, args.out)
except OSError as error:
    print(c(f"写不了 {args.out}：{type(error).__name__}: {error}", C.RED), file=sys.stderr)
    return 2
```

- [ ] 增加写入阶段失败回归（先用下述完整代码 RED，再 GREEN），不只测 replace。不读取私有 tempfile 实现：

```python
def failing_tempfile(*args, **kwargs):
    created = real_named_tempfile(*args, **kwargs)
    class FailingWriter:
        name = created.name
        def __enter__(self):
            return self
        def write(self, text):
            created.write(text[:1])
            raise OSError("injected partial write")
        def __exit__(self, exc_type, exc, traceback):
            created.close()
    return FailingWriter()

real_named_tempfile = tempfile.NamedTemporaryFile
atomic_path.write_bytes(b"old-complete-content\n")
before_names = set(Path(TD).iterdir())
with patch("tempfile.NamedTemporaryFile", side_effect=failing_tempfile):
    remediation_raises(OSError, lambda: json_io.emit_json({"text": "中文"}, str(atomic_path)),
                       "临时文件部分写入失败向上抛出")
t.eq(atomic_path.read_bytes(), b"old-complete-content\n", "写入失败保留旧内容")
t.eq(set(Path(TD).iterdir()), before_names, "部分写入失败也清理临时文件")
with contextlib.redirect_stdout(io.StringIO()) as stdout_json:
    json_io.emit_json({"text": "中文"}, None)
t.eq(json.loads(stdout_json.getvalue()), {"text": "中文"}, "stdout 仍输出 JSON")
with contextlib.redirect_stderr(io.StringIO()):
    json_io.emit_json({"tree": []}, os.devnull)
classify_output = getattr(json_io, "_is_device_output", None)
t.ok(callable(classify_output), "设备输出分类函数可调用")
if callable(classify_output):
    for name in ["NUL", "CON.json", "COM1.json"]:
        t.eq(classify_output(name), os.name == "nt", "Windows 设备名特判有平台边界")
if os.name != "nt":
    posix_normal = Path(TD) / "CON.json"
    with patch("os.replace", wraps=os.replace) as replace_file:
        json_io.emit_json({"tree": []}, str(posix_normal))
        t.eq(replace_file.call_count, 1, "POSIX 同名普通文件仍原子写")
```

- [ ] GREEN：完整自检、pyflakes；确认读取函数仍存在，三 CLI 导入正常，已有 stdout 格式和中文字节计数稳定。
- [ ] 提交前检查后，允许提交时显式暂存上述五个接口文件和自检：`fix(cli): 原子写入 JSON 并统一输出错误退出码`。

## T3：以真实设备状态确认连接和恢复

**Files:** 修改 `tvuitree/infrastructure/adb.py:connect/_reconnect`；测试 `tests/selftest_tree.py`；核对 application/connection.py、interfaces/connection.py 及 MCP 既有错误结果，不改变其接口。

**Interfaces:** `_popen(binary=False)` 返回 `(int,str,str)`、`binary=True` 返回 `(int,bytes,bytes)`；connect/reconnect 返回 bool。`_popen` 原始命令最多自动重试一次，恢复阶段命令使用 heal=False。

- [ ] RED：真实 subprocess 边界模拟，避免错误的 bytes _popen 假件；全部返回 CompletedProcess 的 bytes，使真实 _popen 自己解码：

```python
t.group("整改 T3：连接状态与单次恢复")
serial = "fixture:5555"
for state in ["device", "offline", "unauthorized"]:
    dev = adb.Adb("adb", serial)
    def connect_run(cmd, **kwargs):
        args = cmd[3:]  # adb -s fixture:5555 后面的参数
        if args == ["connect", serial]:
            return subprocess.CompletedProcess(cmd, 0, b"already connected\n", b"")
        if args == ["devices"]:
            return subprocess.CompletedProcess(cmd, 0,
                f"List of devices attached\n{serial}\t{state}\n".encode(), b"")
        raise AssertionError(f"意外命令 {args!r}")
    with patch.object(adb.subprocess, "run", side_effect=connect_run):
        try:
            connected = dev.connect(quiet=True)
        except Exception as error:
            t.ok(False, "连接状态查询不意外抛出", repr(error))
        else:
            t.eq(connected, state == "device", "连接必须处于 device 状态")
            t.eq(dev._connected, connected, "内部连接状态同步")
dev = adb.Adb("adb", serial, auto_connect=False)
dev._connected = True
with patch.object(adb.subprocess, "run", side_effect=subprocess.TimeoutExpired(["adb", "devices"], 20)):
    try:
        failed_connection = dev.connect(quiet=True)
    except Exception as error:
        t.ok(False, "devices 超时返回 False", repr(error))
    else:
        t.eq(failed_connection, False, "devices 超时返回 False")
t.eq(dev._connected, False, "连接失败清除陈旧状态")
for recovery_state in ["device", "offline"]:
    calls = []
    def heal_run(cmd, **kwargs):
        args = cmd[3:]
        calls.append(args)
        if args == ["shell", "echo ok"]:
            if calls.count(args) == 1 or recovery_state == "offline":
                return subprocess.CompletedProcess(cmd, 1, b"", b"error: device offline")
            return subprocess.CompletedProcess(cmd, 0, b"ok\n", b"")
        if args == ["connect", serial]:
            return subprocess.CompletedProcess(cmd, 0, b"connected\n", b"")
        if args == ["devices"]:
            return subprocess.CompletedProcess(cmd, 0,
                f"List of devices attached\n{serial}\t{recovery_state}\n".encode(), b"")
        raise AssertionError(f"意外命令 {args!r}")
    dev = adb.Adb("adb", serial)
    with patch.object(adb.subprocess, "run", side_effect=heal_run), patch.object(adb.logging, "warning") as warning:
        rc, out, err = dev._popen(["shell", "echo ok"])
    t.eq(rc, 0 if recovery_state == "device" else 1, "恢复结果由设备状态确认")
    t.eq(calls.count(["shell", "echo ok"]), 2 if recovery_state == "device" else 1,
         "成功只重试一次，失败不重试")
    t.eq(calls.count(["connect", serial]), 1, "只执行一次恢复连接")
    t.eq(calls.count(["devices"]), 1, "恢复后检查目标状态")
    t.eq(warning.call_count, 1 if recovery_state == "device" else 0, "仅成功恢复打印成功日志")
    t.eq(dev._healing, False, "恢复后解除防递归标志")
```

- [ ] 跑完整 RED。第一次连接判断的 offline/unauthorized 和超时断言应失败，整场仍汇总。恢复失败时旧实现可能重试原命令，但 heal=False 仍保证不递归。
- [ ] 在 Adb 类增加一个状态解析函数，复用在两个入口；替换 connect/_reconnect，保留 _popen 的原单次重试实现：

```python
def _ready_serials(self) -> list[str]:
    rc, out, _ = self._popen(["devices"], timeout=20, heal=False)
    if rc != 0:
        return []
    ready = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            ready.append(fields[0])
    return ready

def connect(self, quiet: bool = False) -> bool:
    self._connected = False
    if self.serial and ":" in self.serial and self.auto_connect:
        try:
            _, out, err = self._popen(["connect", self.serial], timeout=20, heal=False)
            msg = (out + err).strip()
            if not quiet and msg:
                logging.info("[adb] %s", msg)
        except AdbError:
            pass
    try:
        ready = self._ready_serials()
    except AdbError:
        return False
    if not self.serial and ready:
        self.serial = ready[0]
    self._connected = bool(self.serial) and self.serial in ready
    return self._connected

def _reconnect(self) -> bool:
    if self._healing or not (self.serial and ":" in self.serial and self.auto_connect):
        return False
    self._healing = True
    self._connected = False
    try:
        try:
            self._popen(["connect", self.serial], timeout=25, heal=False)
            ready = self._ready_serials()
        except AdbError:
            return False
        self._connected = self.serial in ready
        if self._connected:
            logging.warning("[adb] 连接中断，已自动重连 %s", self.serial)
        return self._connected
    finally:
        self._healing = False
```

connect 文本不是成功判据；devices 的退出码和目标状态才是判据。保留 no_connect/auto_connect=False 的检查逻辑。辅助函数仅复用现有设备状态判断，不新增重试或通用连接管理。

- [ ] 补以下边界用例，先 RED 后 GREEN：缺失目标、devices 非零、找不到 adb、恢复后原命令再次 offline、恢复查询异常、no_connect 与串行 USB 禁止自动恢复：

```python
for response in [(0, "List of devices attached\nother:5555\tdevice\n", ""),
                 (1, f"List of devices attached\n{serial}\tdevice\n", "failure")]:
    dev = adb.Adb("adb", serial, auto_connect=False)
    with patch.object(dev, "_popen", return_value=response):
        t.eq(dev.connect(quiet=True), False, "非目标或失败的设备清单不能连接")
dev = adb.Adb("missing-adb", serial, auto_connect=False)
with patch.object(adb.subprocess, "run", side_effect=FileNotFoundError("adb")):
    try:
        result = dev.connect(quiet=True)
    except Exception as error:
        t.ok(False, "缺少 adb 返回 False", repr(error))
    else:
        t.eq(result, False, "缺少 adb 返回 False")
for target, enabled in [(serial, False), ("USB_SERIAL", True)]:
    dev = adb.Adb("adb", target, auto_connect=enabled)
    with patch.object(dev, "_popen") as no_call:
        t.eq(dev._reconnect(), False, "禁用连接或 USB 不自动 TCP 恢复")
        t.eq(no_call.call_count, 0, "恢复禁用时不执行命令")
dev = adb.Adb("adb", serial)
with patch.object(dev, "_popen", side_effect=[(0, "connected", ""), adb.AdbError("devices timeout")]):
    t.eq(dev._reconnect(), False, "恢复状态查询异常返回 False")
t.eq(dev._healing, False, "异常恢复解除标志")
attempts = []
def twice_offline(cmd, **kwargs):
    args = cmd[3:]
    attempts.append(args)
    if args == ["connect", serial]:
        return subprocess.CompletedProcess(cmd, 0, b"connected", b"")
    if args == ["devices"]:
        return subprocess.CompletedProcess(cmd, 0, f"List of devices attached\n{serial}\tdevice\n".encode(), b"")
    return subprocess.CompletedProcess(cmd, 1, b"", b"device offline")
with patch.object(adb.subprocess, "run", side_effect=twice_offline):
    dev = adb.Adb("adb", serial)
    t.eq(dev._popen(["shell", "echo ok"])[0], 1, "重试仍离线返回原始失败")
t.eq(attempts.count(["shell", "echo ok"]), 2, "连续离线不出现第三次原命令")
t.eq(attempts.count(["connect", serial]), 1, "连续离线不出现第二次恢复")
```

- [ ] GREEN：完整自检验证 CLI/MCP 现有连接错误通道仍成立；不改变 MCP schema 或 timing。提交前检查后，允许提交时提交 `fix(adb): 按设备状态确认连接及单次恢复`，只暂存 adb.py 和自检。

## T4：组件解析排除 UID，保留 android 系统包

**Files:** 修改 `tvuitree/domain/component.py`；测试 `tests/selftest_tree.py`。

**Interfaces:** 两个解析函数仍接受 Optional[str]，返回 Optional[str]；normalize_component 不改。拒绝纯数字类名，包名不强制含点号；严格和回退路径都需覆盖。

- [ ] RED：

```python
t.group("整改 T4：组件格式与 UID 区分")
for text, expected in [
    (None, None), ("Window{abc u0 uid/1000}", None),
    ("noise uid/1000 trailing", None),
    ("Window{abc u0 com.example/.Main}", "com.example/.Main"),
    ("noise com.example/com.example.Main trailing", "com.example/com.example.Main"),
    ("Window{abc u0 android/com.android.internal.app.ResolverActivity}",
     "android/com.android.internal.app.ResolverActivity"),
    ("Window{abc u0 com.example/.Outer$Inner}", "com.example/.Outer$Inner"),
    ("noise uid/1000 then com.example/.Main trailing", "com.example/.Main"),
]:
    t.eq(component.component_from_window(text), expected, "窗口组件解析")
for text, expected in [
    ("ActivityRecord{abc u0 uid/1000 t42}", None),
    ("ActivityRecord{abc u0 com.example/.Main t42}", "com.example/.Main"),
    ("ActivityRecord{abc u0 android/com.android.internal.app.ResolverActivity t42}",
     "android/com.android.internal.app.ResolverActivity"),
]:
    t.eq(component.component_from_activity_record(text), expected, "ActivityRecord 组件解析")
```

- [ ] 完整 RED 汇总应出现 UID 误识别。局部增加公共模式常量，替换三个 re.search 模式：

```python
# 包名允许 android；类名每段以标识符字符开头，避免把 UID 数字当成类名。
_COMPONENT_PATTERN = (r"([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)/"
                      r"(\.?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")

def component_from_window(text: Optional[str]) -> Optional[str]:
    """读取窗口文本里的 Android 组件，排除 UID 等非类名字段。"""
    if not text:
        return None
    match = re.search(r"\s" + _COMPONENT_PATTERN + r"\}", text)
    if not match:
        match = re.search(r"(?<![\w.$/])" + _COMPONENT_PATTERN + r"(?![\w.$/])", text)
    return f"{match.group(1)}/{match.group(2)}" if match else None

def component_from_activity_record(text: Optional[str]) -> Optional[str]:
    """读取 ActivityRecord 中的 Android 组件。"""
    if not text:
        return None
    match = re.search(r"\s" + _COMPONENT_PATTERN + r"\s", text + " ")
    return f"{match.group(1)}/{match.group(2)}" if match else None
```

不添加“正则源码必须包含两个加号”之类测试；断言用户可观察的行为。系统包样例的官方来源为 [AOSP CTS](https://android.googlesource.com/platform/cts.git/%2B/ced4c21c6da141ef5ca83797c8f2fa923201915c%5E2..ced4c21c6da141ef5ca83797c8f2fa923201915c/)，其中明确检查 `android/com.android.internal.app.ResolverActivity`。

- [ ] GREEN：完整自检；金样原始 dumpsys 重建结果不得新增差异。允许提交时提交 `fix(component): 排除 UID 字段并保留系统组件解析`，暂存 component.py 和自检。

## T5：标签绘制失败追加说明

**Files:** 修改 `tvuitree/infrastructure/image.py:draw_boxes` 的 dr.text 异常分支；测试 `tests/selftest_tree.py`。

**Interfaces:** draw_boxes/draw_boxes_png 签名、(drawn,skipped,notes) 元组不变。只在文字失败时追加 notes；正常路径 notes 保持现状，画框仍成功。

- [ ] RED（缺少 Pillow 明确记为未验证，不伪报通过）：

```python
t.group("整改 T5：标签失败可解释")
try:
    from PIL import Image, ImageDraw
except ImportError:
    t.ok(False, "标签绘制回归需要项目 Pillow", "当前环境缺少 Pillow，不能验收此任务")
else:
    blank = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(blank, format="PNG")
    boxes = [(20, 20, 60, 60, "TextView#title", "reading")]
    canvas = {"width": 100, "height": 100}
    target = os.path.join(TD, "label_failure.png")
    with patch.object(ImageDraw.ImageDraw, "text", side_effect=OSError("font unavailable")):
        drawn, skipped, notes = image.draw_boxes(blank.getvalue(), boxes, target, canvas)
    t.eq((drawn, skipped), (1, 0), "标签失败不影响画框计数")
    t.ok(any("标签绘制失败" in note and "TextView#title" in note and "OSError" in note
             for note in notes), "说明包含失败标签和异常类型")
    result_image = Image.open(target)
    t.eq(result_image.getpixel((20, 20)), image.COLOR_READING, "文字失败仍按读数画框")
    result_image.close()
    drawn, skipped, notes = image.draw_boxes(blank.getvalue(),
        [(20, 20, 60, 60, "", "reading")], target, canvas)
    t.eq((drawn, skipped, notes), (1, 0, []), "正常空标签不新增 note")
```

- [ ] 完整 RED 后，局部替换 dr.text 的整个 try/except 片段：

```python
try:
    dr.text((rect[0] + 2, max(0, rect[1] - 13)), label, fill=color)
except Exception as error:
    notes.append(f"框标签绘制失败：{label}（{type(error).__name__}: {error}）；框线仍已绘制")
```

保留当前广义文字异常处理，因为辅助标签不能导致整个截图丢失；不吞其他阶段的异常。其余绘制逻辑不动。

- [ ] GREEN：完整自检及金样 PNG 字节比对。允许提交时提交 `fix(image): 在标签绘制失败时返回诊断说明`，暂存 image.py 和自检。

## T6：依赖与接口文档收尾

**Files:** 修改 requirements.txt 和 README.md；不动 ADB_CANDIDATES，不卸载当前环境依赖，不创建新环境。

- [ ] 核查真实代码/脚本无 uiautodev 使用：`rg -n "uiautodev" tvuitree main.py scripts tests requirements.txt`。若新增实际引用，停止删依赖并报告差异；文档提及不算运行依赖。
- [ ] requirements.txt 仅删除 uiautodev 一行，结果：

```text
uiautomator2
Pillow
pyflakes
mcp>=1.28,<2
```

- [ ] README 保留现有截图约定、剪枝和层级介绍，修正现有“设备或采集失败返回 3”的错误表述，并加入下列最终行为说明：

```text
observe、tree、visible 的用法、输入文件、输出文件或连接错误返回退出码 2；连接后采集失败返回 3。shot 和 input 自身失败返回 1，连接失败返回 2。

observe、tree、visible 使用 --out 写普通 JSON 文件时，先写同目录临时文件，再替换目标；写入或替换失败时旧文件保持完整，不输出成功提示。设备输出（如 Windows NUL）直接写入，不提供文件原子替换保证。输出大小按 UTF-8 字节数计算，包含末尾换行。

设备属性空值按原位置保留；读取失败时不返回串位数据，现有采集流程允许设备属性信息缺失。ADB 连接与自动恢复以目标 serial 在设备列表中的 device 状态为准，offline 和 unauthorized 不算已连接；采集命令最多自动恢复并重试一次。

截图标签文字绘制失败时，框线仍保留，并在 notes 中说明标签及失败原因。坐标换算和逐像素画框规则保持不变。
```

- [ ] 不给纯依赖删行添加“源码必须不包含某字符串”的永久测试。执行 `& $py -m pip check` 并解释实际问题：旧环境残留 uiautodev 不能证明新 requirements 错误，不通过卸载用户环境来取得绿色。
- [ ] 完整必要检查通过后，允许提交时提交 `chore(deps): 删除未引用依赖并更新错误处理说明`，只暂存 requirements.txt/README.md。

## 金样：区分既有差异和本次回归

旧 base 有 19 个文件。2026-10-02 已审查的五个计数字段差异：keep_all.txt、keep_gone.txt、observe.txt、slim.txt、visible.txt；其余 14 个文件一致。不得要求这份旧 base 零差异，不运行 `golden.py make`，也不修改 base。

- [ ] 若 `_temp/golden/golden.py`、`base`、`_temp/e2e` 和 `_temp/raw` 均存在，在 T0 修改前执行 `& $py _temp/golden/golden.py check`，记录其真实返回值和差异。工具会清理自己的 now 目录，先核对 now 只包含该工具生成的临时文件；若有人在 now 放入其他资料，先选择新的独立输出目录并局部调整本地工具，不删除资料。
- [ ] 用以下只读审计核对旧差异，保存为 `$evidence/audit_legacy_golden.py`；仅允许 stderr 的单个 `[out] 已写入` 行里的字节数字变动，不忽略 stdout、路径、返回码或其他诊断：

```python
from pathlib import Path
import re

root = Path.cwd()
base = root / "_temp/golden/base"
now = root / "_temp/golden/now"
allowed = {"keep_all.txt", "keep_gone.txt", "observe.txt", "slim.txt", "visible.txt"}
assert {p.name for p in base.iterdir()} == {p.name for p in now.iterdir()}, "文件集合不同"
def normalize(data: bytes) -> bytes:
    stdout, marker, stderr = data.partition(b"\n--- stderr ---\n")
    assert marker, "缺少 stderr 分隔符"
    for encoding in ("utf-8", "gb18030"):
        try:
            text = stderr.decode(encoding)
        except UnicodeDecodeError:
            continue
        normalized, count = re.subn(r"(?m)(^.*\[out\] 已写入 [^\r\n]*（)\d+( 字节）)", r"\1<COUNT>\2", text)
        if count == 1:
            return stdout + marker + normalized.encode("utf-8")
    raise AssertionError("没有唯一的字节计数提示")
for old in sorted(base.iterdir()):
    current = now / old.name
    if old.read_bytes() == current.read_bytes():
        continue
    assert old.name in allowed, f"非白名单变化：{old.name}"
    assert normalize(old.read_bytes()) == normalize(current.read_bytes()), old.name
print("旧基线差异仅限已审查的五个计数字段")
```

- [ ] T0 审计通过后把当前 now 全部文件复制到新的证据子目录 `execution-baseline`（该目录此前不能存在）。此目录是“当前执行基线”，不能反向覆盖旧 base。记录 JSON/PNG 的 SHA256。

```powershell
& $py "$evidence/audit_legacy_golden.py"
if ($LASTEXITCODE -ne 0) { throw '旧金样差异超出许可范围' }
$executionBaseline = Join-Path $evidence 'execution-baseline'
if (Test-Path -LiteralPath $executionBaseline) { throw '执行基线已存在，不能覆盖；先核对是否续跑同一执行' }
New-Item -ItemType Directory -Path $executionBaseline | Out-Null
Get-ChildItem -LiteralPath '_temp/golden/now' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $executionBaseline
}
Get-ChildItem -LiteralPath $executionBaseline -File | Get-FileHash -Algorithm SHA256 |
    Select-Object Path, Hash | ConvertTo-Json | Set-Content -Encoding utf8 "$evidence/golden-hashes.json"
```
- [ ] T2/T4/T5 和终验重新 check，然后要求 now 与 execution-baseline 文件集合及每个文件逐字节一致，不继续对本次差异归一化。检查命令：

```powershell
& $py -c 'from pathlib import Path; import sys; a=Path(sys.argv[1]); b=Path(sys.argv[2]); assert {p.name for p in a.iterdir()} == {p.name for p in b.iterdir()}; changed=[p.name for p in a.iterdir() if p.read_bytes() != (b/p.name).read_bytes()]; assert not changed, changed; print("当前执行基线无新增差异")' "$evidence/execution-baseline" '_temp/golden/now'
if ($LASTEXITCODE -ne 0) { throw '产生新的金样差异，必须定位' }
```

本地金样缺失时记录缺哪些文件，使用项目自检替代，不伪造金样通过。不要把旧 base 的 expected 退出码 1 当作新任务失败，也不要把任意 check=1 直接视为可接受。

## 最终验证与交付

每个任务的 GREEN 包含完整自检和针对当前全部 Python 文件的 pyflakes；生产代码任务还运行 py_compile。T0 和终验运行完整检查；提交前运行 help/prune-list/diff-check。这批变更跨公共 ADB、三 CLI 和截图入口，完整顺序自检是必要范围，不使用不存在的 pytest 单测选择器。

允许本地提交时，各任务在上述检查通过后执行对应命令；否则保留未提交差异交付。不要使用 `git add .`：

```powershell
# T1
git add tvuitree/infrastructure/adb.py tests/selftest_tree.py
git commit -m "fix(adb): 保留设备属性空行并校验响应"
# T2
git add tvuitree/interfaces/json_io.py tvuitree/interfaces/observe.py tvuitree/interfaces/tree.py tvuitree/interfaces/visible.py tests/selftest_tree.py
git commit -m "fix(cli): 原子写入 JSON 并统一输出错误退出码"
# T3
git add tvuitree/infrastructure/adb.py tests/selftest_tree.py
git commit -m "fix(adb): 按设备状态确认连接及单次恢复"
# T4
git add tvuitree/domain/component.py tests/selftest_tree.py
git commit -m "fix(component): 排除 UID 字段并保留系统组件解析"
# T5
git add tvuitree/infrastructure/image.py tests/selftest_tree.py
git commit -m "fix(image): 在标签绘制失败时返回诊断说明"
# T6
git add requirements.txt README.md
git commit -m "chore(deps): 删除未引用依赖并更新错误处理说明"
```

每次只执行当前任务的那一对命令，检查 git 命令真实退出码，失败即停止，不整块执行六次提交。先查看暂存 diff，发现任务外改动即从本次暂存排除，不改变文件内容。

- [ ] 最后一次运行 T0 的编译、pyflakes、自检、diff-check；新增断言全部成立，不能只维持旧 714 条数量。
- [ ] 提交前必跑：

```powershell
& $py main.py --help
if ($LASTEXITCODE -ne 0) { throw '帮助命令失败' }
& $py main.py tree --prune-list
if ($LASTEXITCODE -ne 0) { throw '剪枝列表失败' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw '差异检查失败' }
git diff --cached --stat
```

- [ ] 检查当前 config SHA256 与 T0 对照。若不一致，先区分用户修改与任务引入；只撤销明确属于执行者的意外修改，**禁止 `git checkout -- config.json` / `git restore config.json` 作为通用收尾**。不要打印设备配置内容到交付记录。
- [ ] 有可用且已授权的 TV 时做只读真机验收；先看 `adb devices -l`。当前可用地址以执行时已有配置/用户授权为准，历史地址不能当作在线事实。下面命令从现有配置取目标，不修改 config：

```powershell
& $py main.py tree --mode full --out "$evidence/live-full.json"
if ($LASTEXITCODE -ne 0) { throw '真机全量采集失败' }
& $py main.py observe --from-json "$evidence/live-full.json" --out "$evidence/live-observe.json"
if ($LASTEXITCODE -ne 0) { throw '离线观察生成失败' }
& $py main.py visible --from-json "$evidence/live-full.json" --out "$evidence/live-visible.json"
if ($LASTEXITCODE -ne 0) { throw '离线可见摘要生成失败' }
& $py main.py shot --json "$evidence/live-full.json" --out "$evidence/live-shot.png"
if ($LASTEXITCODE -ne 0) { throw '真机截图失败' }
```

shot 使用 full JSON，不能用 observe 摘要。截图和树采集相隔期间画面可能变化，记录漂移，不把视觉不重合直接认定为坐标错误。逐像素验证以既有确定性离线测试/PNG 金样为准，不用全图红色 bbox 推断边框，因为标签和中心标记也可能是红色。

- [ ] 不为验证自动恢复主动执行 `adb disconnect`，更不执行全局 disconnect。新进程初始 connect 不能证明采集恢复路径；T3 真实 _popen + subprocess 替身已确定性覆盖该路径。真机若自然掉线则记录，不强制制造。
- [ ] 若 Zcode 的宿主可直接调用本项目 MCP，实际调用 get_full_tree/observe_tv/get_visible/get_current_focus/get_focus_screenshot，检查已有错误 schema、每次一个 stderr timing 块及截图内容；无法提供 MCP 宿主时明确“实际 stdio 集成未运行”，以自检现有 MCP 用例作为离线覆盖。不得将直接 Python 调函数称作真实协议验收。
- [ ] 最后集中审查一次差异，核对六个任务及原报告 12 项全部有对应处理：

| 原 Review 问题 | 本计划处理 |
|---|---|
| json_io.os 不存在导致 RED 中止 | T2 patch 标准库 os.replace |
| _popen 假件始终 bytes | T1 文本 shell_raw；T3 真实 subprocess 边界 |
| android 包被点号规则拒绝 | T4 正则与系统组件案例 |
| visible 输出用例缺 screen | T2 有效 fixture 与成功对照 |
| connect devices 异常外漏 | T3 返回 False 并清理状态 |
| 恢复成功日志被删除 | T3 状态确认后保留 warning |
| 旧金样无法零差异 | 旧差异严审 + 当前执行基线精确比对 |
| shot 输入错误/重连触发错误 | full JSON；离线确定性恢复，不主动断 TV |
| config 通用回滚覆盖用户设置 | T0 哈希及只修复自己的变化 |
| 全文模板漏 load_full_json | T2 局部替换，读取函数保留 |
| 原子测试未覆盖旧目标 | T2 已有内容、部分写入与替换失败 |
| 设备名特判污染 POSIX | T2 os.name 限定及平台条件测试 |

- [ ] 交付结果列出：任务完成状态、实际自检断言数、静态检查、金样与真机/MCP 分别结果、未运行的检查和具体原因、配置保护结果、本地提交 SHA（若有）。不提交 _temp/.omo/config；不推送。若中途失败，停止依赖该结果的下一任务，保留已验证成果和证据，不以整体回滚删除用户数据。

## 计划自身验收

- [ ] 实施前 Zcode 核对路径和真实接口，若 HEAD 已变按函数定位而非旧行号执行。
- [ ] 实施后所有 RED 都经过行为失败 → 最小修复 → GREEN，异常不终止顺序自检。
- [ ] 最终代码变更局限六项；既有 JSON、MCP timing 和画框语义没有新增差异。
- [ ] 本地提交须经过检查且暂存范围明确；外部操作须另有用户明确授权。
