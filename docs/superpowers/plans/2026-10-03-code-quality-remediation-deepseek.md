# 观测质量与边界补修 Implementation Plan（原 DeepSeek 交接版，Codex 执行）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task when available. Steps use checkbox (`- [ ]`) syntax for tracking. 用户最初指定 DeepSeek；2026-10-03 改为 Codex 本会话执行，并选择独立 worktree。所有任务顺序实施，尤其不能并发编辑共享自检、visible.py 或 input.py。

**Goal:** 关闭当前代码质量评审的 Q1–Q9，优先保证观测证据、控件状态及失败结果可信。

**Architecture:** 保留 interfaces → application → domain 的现有职责与 infrastructure 外部适配。R1、状态摘要、截图判据及解析规则在各自 domain 模块修复；full JSON 文件入口复用一个纯结构校验函数；ADB 状态及 CLI 错误在原边界处理。保留 full JSON 为投影中心，不引入通用框架、重试系统或全量模型迁移。

**Tech Stack:** Python 3.10+、项目 `.venv`、标准库 unittest.mock / xml.etree / math / re、当前 Pillow/uiautomator2/MCP。当前验证环境为 uiautomator2 3.7.0、Pillow 12.3.0、mcp 1.30.0、pyflakes 4.0.0；本轮不升级、重装或锁定依赖。

**Spec:** [当前代码质量与架构评审 Q1–Q9](../../reviews/2026-10-03-current-code-quality-and-architecture.md)，[AGENTS.md](../../../AGENTS.md)。用户已采用“观测可信度 → 输入与错误边界 → 可见摘要完整性”的三批方案；此处将其细化为顺序任务。

**Baseline:** `c5eb108494b8a221eba0cf5074bd162c6676cf28`。计划编写前最近一次当前版本检查为 compile/pyflakes/selftest/diff 全绿、864 条断言；这是历史验证，执行者必须重新建立基线。

## Codex 执行记录

2026-10-03 用户改由 Codex 执行，并明确选择独立 worktree。基线 HEAD 为 c5eb108；实现验收时未提交、推送或合并。2026-10-04 用户另授权推送，实际批次提交和快照验证见交付报告；不自动合并。T0–T10 已完成，2026-10-04 集中终审的一项 Important 亦已闭环，最终 1087 条自检通过；主要实现遵照本计划，执行裁定及最终结果见 [交付报告](../../reports/2026-10-03-code-quality-remediation-delivery.md)。原 DeepSeek 文件名保留，避免已有引用失效。

| 任务 | RED | GREEN 自检断言数 |
|---|---|---|
| T1 | 双向歧义匹配失败 | 869 |
| T2 | 共享摘要及四接口禁用字段遗漏 | 890 |
| T3 | 非原点父容器两种数据来源误判 | 898 |
| T4 | 坏 XML 伪正常空树及接口错误缺失 | 907 |
| T5 | 嵌套数据错误未拒绝或异常外漏 | 993 |
| T6 | offline/unauthorized 与混合目标误判 | 1024 |
| T7 | ADB/图片异常与时区 TypeError 外漏 | 1035 |
| T8 | 非法序列执行产生部分副作用 | 1052 |
| T9 | 无标签开关及 False 读数遗漏 | 1079 |

各 GREEN 均包括 compile、pyflakes、全量 selftest 和 diff check。独立终审补充第 33 组“缺少焦点坐标保持未知”：RED 为 6 项正常失败，GREEN 为 1087 条断言；具体裁定及未验证范围见交付与终审报告。原任务中条件提交步骤保留设计依据；后续授权的实际提交按三批、终审补修、文档归档组织，每批暂存快照独立验证；下述内容仍作为设计与验收依据保存，不以未勾选框代替本执行记录。

## Global Constraints

- Python 3.10+、四空格、UTF-8；优先使用 `.venv/Scripts/python.exe`，不把 selftest 当 pytest。
- domain 不访问设备、文件、终端、MCP、Pillow 或 uiautomator2；纯校验只检查数据，不执行 I/O。
- CLI 和 MCP 必须复用 application observation service；保留 generator=`tv_tree.py`。
- 保持 R0–R3、merge_children 与 geom_of 的现有职责；R1 只修逆向唯一性，不改 R0/R2/R3 谓词。
- 保留来源读数与派生值区别，不从 focusable 单独推断焦点或可见性，不创造标签。
- 坐标绘制保持“不加偏移”“不补偿”“逐像素”；T3 只修告警判据，不修改绘制几何、线宽、颜色或分辨率换算。
- observe/tree/visible 的用法、文件、连接错误为 2，采集错误为 3；shot/input 自身工作流失败为 1，连接错误为 2。shot 既有 JSON/图片文件失败为 1，本计划保留该命令行为，不能顺手改成 2。
- MCP stdout 只承载协议，诊断进 stderr；每个工具调用恰好一个 timing 块，耗时不进入返回结果。不新增 MCP 工具、不改参数 schema。
- 配置逐次读取、显式参数逐字段覆盖。保留 config.json、个人地址、`.omo/`、`.zcodeignore` 和所有无关改动。
- 用真实外部边界的替身，不连接 TV 的测试不得触发 adb/u2/network。不制造掉线，不发送真机按键验证 T8。
- 本轮允许的输出行为变化：歧义 R1 不再绑定；明确 enabled=False；修正告警；解析失败转采集错误；非法输入转受控错误；不可用连接拒绝；无标签操作控件保留。对应变化必须记录，不能以“JSON 完全不变”阻止正确修复。
- 原子 JSON 写入、Windows 设备输出、props 行对位、恢复单次重试、源码卫生与既有 GBK 测试子进程修复均保留。
- 正式计划/评审/报告放 docs，原始输入、PNG、日志和验证脚本放 ignored `_temp`；正式报告不含本地设备地址或敏感输出。
- 当前授权已改为 Codex 实施，并于 2026-10-04 授权本地提交和推送隔离分支；不自动合并或改写历史。提交步骤只在执行阶段用户授权提交时使用，见末尾。

## Review Focus

1. 兼容图中一个 a11y 有两候选、另一个只有其中一候选时，不能因立即占用把歧义变成唯一；T1 测试静态候选图。
2. enabled 缺失/None 与明确 False 不同；合法空 hierarchy 与解析失败不同；T2/T4 分别锁定。
3. 旧/稀疏 full JSON 可以缺 screen、children 或附带未知字段；校验不能把缺失读数补成 False，也不能要求所有生产字段都存在；T5 锁定。
4. 按键序列后半段非法时不能先发前半段；offline/unauthorized 不能因 no_connect 被视为可用；T6/T8 锁定。
5. 无标签 Switch 的 checked=False 是读数，而空布局/focusable-only 容器应继续省略；T9 锁定，保留 T2 的禁用结果。

## 批次、依赖与文件边界

| 批次 | 任务 | 问题 | 文件 |
|---|---|---|---|
| 1 | T1 | Q1：R1 双向唯一 | domain/tree/matching.py、domain/tree/output.py（规则说明） |
| 1 | T2 | Q2：禁用状态 | domain/observation.py |
| 1 | T3 | Q3：局部坐标告警 | domain/screenshot.py |
| 1 | T4 | Q4：错误 XML | domain/tree/parsing.py |
| 2 | T5 | Q6：JSON 结构 | domain/tree/output.py、interfaces/json_io.py |
| 2 | T6 | Q7：初始设备状态 | infrastructure/adb.py |
| 2 | T7 | Q5：CLI 异常出口 | interfaces/input.py、interfaces/shot.py |
| 2 | T8 | Q8：键码校验 | application/input.py、interfaces/input.py |
| 3 | T9 | Q9：无标签操作控件 | domain/visible.py |
| 收尾 | T10 | 文档与终验 | README.md、docs/README.md、docs/reports/2026-10-03-code-quality-remediation-delivery.md |

每个 T1–T9 均修改 tests/selftest_tree.py。T8 消费 T7 的 input 异常边界；T9 消费 T2 的 enabled 状态。T5 的校验函数放在既有 full JSON 格式归属 output.py，不另建万能校验模块。T4 不导入 AdbError，纯 domain 抛 ValueError，现有接口负责转换。

**明确排除：** 不升级依赖、不拆测试框架、不建 CI、不处理 config 追踪策略、不修 image.load_tree 重复加载、不重构 MCP 焦点工具。README“四个工具”改为“六个工具”可在 T10 局部修正。这些维护项不影响 Q1–Q9 关闭。

## T0：基线、执行记录与公共测试工具

- [ ] 在仓库根目录检查 status/HEAD/分支。若生产代码已不同于上述版本，先核对各问题是否已修复，不能覆盖并行修改或重做已完成任务。
- [ ] 保留现有未提交 docs 索引/评审。本计划、评审及索引是交接材料，不当作可删除的脏工作树；没有提交授权不自动 checkpoint。
- [ ] 新建 `_temp/plan-evidence/code-quality-remediation-20261003/`；记录每任务命令、返回码、失败原因及 GREEN 结果到 progress.md。目录已存在时核对续跑身份，不覆盖证据。

```powershell
$py = '.\.venv\Scripts\python.exe'
$evidence = '_temp/plan-evidence/code-quality-remediation-20261003'
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
git status --short | Set-Content -Encoding utf8 "$evidence/status-before.txt"
git rev-parse HEAD | Set-Content -Encoding utf8 "$evidence/head-before.txt"
(Get-FileHash -LiteralPath config.json -Algorithm SHA256).Hash |
    Set-Content -Encoding utf8 "$evidence/config-before.sha256"
function Invoke-QualityChecks {
    $files = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse |
        ForEach-Object { $_.FullName })
    & $py -m py_compile $files
    if ($LASTEXITCODE -ne 0) { throw 'compile failed' }
    & $py -m pyflakes $files
    if ($LASTEXITCODE -ne 0) { throw 'pyflakes failed' }
    & $py tests/selftest_tree.py
    if ($LASTEXITCODE -ne 0) { throw 'selftest failed' }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'diff check failed' }
}
Invoke-QualityChecks
```

- [ ] 在 tests 原有“收尾”之前追加组，不改已有有效断言；仅修改受本轮正常输出变化直接影响的 EXP 常量，并记录原因。测试替身在上下文结束恢复。
- [ ] 追加以下测试工具；已有 imports 有 contextlib/io/json/os/subprocess/Path/patch，无需提前添加未使用导入。新增组会使用这些函数，首次加入与首个用例同时进行。

```python
def quality_cli(args: list[str]) -> tuple[int, str, str]:
    """保留实际 CLI，异常也交给断言收集，防止 RED 中断整场。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(args)
        except Exception as error:
            rc = -999
            err.write(f"ESCAPED {type(error).__name__}: {error}")
    return rc, out.getvalue(), err.getvalue()


def quality_value_error(call, what: str) -> None:
    """宽捕获后核对目标错误，RED 仍能正常汇总。"""
    try:
        call()
    except Exception as error:
        t.ok(isinstance(error, ValueError), what, repr(error))
    else:
        t.ok(False, what, "未报告 ValueError")
```

RED 每次运行完整 selftest，预期 rc=1 且有正常汇总；不能接受语法错误、NameError、替身队列耗尽或无关失败。GREEN 每次运行 Invoke-QualityChecks，预期全部 rc=0。不要用固定断言总数作为目标。

T2 首次使用时再加入以下接口测试工具。复用第 8 段已定义的 `SimpleNamespace`、`mcp_interface`、`_timing_calls`，每次单独恢复连接、采集和日志替身。不修改已有真实格式夹具；这里只替换共享 full JSON 采集入口，实际摘要函数和 CLI/MCP 函数仍运行。属于离线接口测试，不代表真实 MCP stdio 握手或真机验证。

```python
def quality_projection_interfaces(full: dict) -> tuple[dict, dict, dict, dict]:
    """同一 full JSON 经实际 CLI/MCP 投影，全部设备边界用替身隔离。"""
    device = SimpleNamespace(serial="fixture")
    with patch.object(application_observation, "collect_full_json", return_value=full), \
         patch.object(mcp_interface, "collect_full_json", return_value=full), \
         patch.object(observe_interface, "connect_for_cli", return_value=device), \
         patch.object(visible_interface, "connect_for_cli", return_value=device), \
         patch.object(mcp_interface, "_connect", return_value=(device, "fixture")), \
         patch.object(timing, "LOG_STREAM", io.StringIO()):
        rc, out, err = quality_cli(["observe", "--no-dumpsys", "--quiet", "--no-color"])
        t.eq(rc, 0, "CLI observe 离线接口成功")
        cli_observation = json.loads(out) if rc == 0 else {}
        mcp_observation = mcp_interface.observe_tv(no_dumpsys=True)
        t.eq(_timing_calls(), [("observe_tv", ["connect", "capture_tree", "summarize"], None)],
             "observe 恰好一个 timing 块")
        rc, out, err = quality_cli(["visible", "--quiet", "--no-color"])
        t.eq(rc, 0, "CLI visible 离线接口成功")
        cli_visible = json.loads(out) if rc == 0 else {}
        mcp_visible = mcp_interface.get_visible()
        t.eq(_timing_calls(), [("get_visible", ["connect", "capture_tree", "summarize"], None)],
             "visible 恰好一个 timing 块")
    t.eq(cli_observation, mcp_observation, "observe 接口投影一致")
    t.eq(cli_visible, mcp_visible, "visible 接口投影一致")
    return cli_observation, mcp_observation, cli_visible, mcp_visible
```

## T1：几何锚定采用静态双向唯一候选（Q1）

**Files:** tvuitree/domain/tree/matching.py:align 的 R1 区段；tvuitree/domain/tree/output.py:build_full_json 的 R1 说明；tests/selftest_tree.py。
**Interfaces:** align(roots, roots, pkg, screen, max_rounds=6) -> AlignStats 不变；只改变 MATCH_GEOM 的绑定资格，bind/R0/R2/R3/统计结构保留。

- [ ] 添加以下 RED；使用真实父子结构及新对象，避免 align 修改节点后的状态被下一轮复用。

```python
t.group("质量 T1：R1 逆向唯一及遍历不变性")
for names in [("A", "B"), ("B", "A")]:
    ur = models.U2Node(raw={}, cls="android.widget.FrameLayout", bounds=(0, 0, 400, 300))
    vr = models.Node(cls="android.widget.FrameLayout", bounds=(0, 0, 400, 300))
    vc = models.Node(cls="android.widget.Button", res_id="pkg:id/key",
                     bounds=(10, 10, 40, 40), parent=vr)
    vr.children = [vc]
    ur.children = [models.U2Node(raw={}, cls=vc.cls, text=name, res_id=vc.res_id,
                               bounds=vc.bounds, parent=ur) for name in names]
    st = matching.align([ur], [vr], "pkg", (0, 0, 400, 300))
    t.eq(sum(child.match_reason == models.MATCH_GEOM for child in ur.children), 0,
         "两 a11y 争一 View，R1 不抢占")
    t.eq(st.paired, 1, "仅保留无歧义的 R0 根")

# Button a11y 兼容 custom/Button 两个 View；TextView a11y 仅兼容 custom View。
# 逆向统计必须包括前者，不能仅统计各自唯一的候选。
ur = models.U2Node(raw={}, cls="android.widget.FrameLayout", bounds=(0, 0, 400, 300))
vr = models.Node(cls=ur.cls, bounds=ur.bounds)
vr.children = [models.Node(cls="app.CustomButton", bounds=(10, 10, 40, 40), parent=vr),
               models.Node(cls="android.widget.Button", bounds=(10, 10, 40, 40), parent=vr)]
ur.children = [models.U2Node(raw={}, cls="android.widget.Button", bounds=(10, 10, 40, 40), parent=ur),
               models.U2Node(raw={}, cls="android.widget.TextView", bounds=(10, 10, 40, 40), parent=ur)]
matching.align([ur], [vr], "pkg", (0, 0, 400, 300))
t.eq(sum(child.match_reason == models.MATCH_GEOM for child in ur.children), 0,
     "候选图含歧义时不产生伪唯一几何绑定")
```

上例 class_ok 对 custom View 兼容任意 a11y，框架 Button 仅匹配 Button；两 a11y 的候选分别为 `{custom,button}`、`{custom}`。R3 仍可根据唯一序列匹配部分节点，所以只断言不标 MATCH_GEOM，不禁止其他合法证据。

- [ ] Run RED：旧实现至少前两轮按顺序绑定一个子节点，测试应失败。
- [ ] 在 R1 中先建立不可随 bind 改变的兼容图，再绑定双向度数都为 1 的边。保持原 resid/class/pred 谓词：

```python
by_rect = {}
for v in v_nodes:
    r = pred[id(v)]
    if r is not None and id(v) not in paired_v:
        by_rect.setdefault(r, []).append(v)
candidates, reverse_count = {}, {}
for u in u_nodes:
    if id(u) in paired_u or u.bounds is None:
        continue
    values = [v for v in by_rect.get(u.bounds, [])
              if resid_ok(v, u, pkg) and class_ok(v, u)[0]]
    candidates[id(u)] = values
    for v in values:
        reverse_count[id(v)] = reverse_count.get(id(v), 0) + 1
for u in u_nodes:
    values = candidates.get(id(u), [])
    if len(values) == 1 and reverse_count[id(values[0])] == 1:
        bind(values[0], u, MATCH_GEOM)
```

- [ ] 将 output.py:build_full_json 返回字典中 align_rules 的 R1 值替换为 `"pred_visible_rect(view)==a11y bounds 且 res-id/class 谓词成立且双向候选唯一"`，其余规则值原样保留。这是匹配规则说明同步，金样 rebuilt_full.json 中对应字符串差异需单独记录。
- [ ] Run GREEN；已有唯一几何、res-id/class 谓词、R2 焦点、R3 序列和节点守恒用例保持通过。若既有夹具曾依赖任意抢占，先核对其实际歧义，不能仅改 EXP 数量。
- [ ] 若获提交授权：`fix(matching): 仅绑定双向唯一的几何候选`。

## T2：保留明确的禁用状态（Q2）

**Files:** domain/observation.py:node_summary；tests。
**Interfaces:** node_summary(node, path, include_children=False) -> dict，字段名不变。False 为读数；缺失/None 保持未知。

- [ ] RED：

```python
t.group("质量 T2：enabled False 不是未知")
for enabled in [True, False, None]:
    node = {"source": "a11y", "class": "android.widget.Button", "text": "Control",
            "bounds_screen": [0, 0, 20, 20], "clickable": True, "enabled": enabled}
    summary = domain_observation.node_summary(node, (0,))
    if enabled is None:
        t.not_has(summary, "enabled", "未知状态不补成 False")
    else:
        t.eq(summary.get("enabled"), enabled, "共享摘要保留布尔读数")
    full = {"tree": [node], "screen": {"width": 100, "height": 100}}
    item = application_observation.collect_visible(full_json=full)["page"]["nodes"][0]
    if enabled is False:
        t.eq(item.get("enabled"), False, "visible 显式保留禁用状态")
    t.eq(summary.get("actions"), ["click"], "clickable 读数不被 enabled 改写")
```

- [ ] Run RED，禁用读数断言失败。
- [ ] 将原状态循环条件改为显式 bool；原本 focused/selected/checked 的 False 继续保留，只新增 enabled False：

```python
for key in ("focused", "selected", "checked", "enabled", "visible", "visible_to_user"):
    value = node.get(key)
    if value is True or (value is False and key in ("focused", "selected", "checked", "enabled")):
        result[key] = value
```

- [ ] 在同组追加以下接口 RED，加入 T0 的共享测试工具后运行；不能因返回值一致就接受两个接口同时漏字段：

```python
disabled = {"source": "a11y", "class": "android.widget.Button", "text": "Control",
            "bounds_screen": [0, 0, 20, 20], "clickable": True, "enabled": False}
full = {"tree": [disabled], "screen": {"width": 100, "height": 100}}
for projected in quality_projection_interfaces(full):
    items = projected.get("page", {}).get("nodes", [])
    t.ok(bool(items), "各接口返回禁用控件")
    if items:
        t.eq(items[0].get("enabled"), False, "各接口明确返回禁用读数")
```

- [ ] Run GREEN，保留第 8 段原有 patch/restore/timing 测试结构和夹具。
- [ ] 若获授权：`fix(observation): 保留控件明确的禁用状态`。

## T3：祖先链告警统一坐标系（Q3）

**Files:** domain/screenshot.py:JsonNode.chain_overflow；tests。
**Interfaces:** 返回 None 或告警字符串，画框 collect/render 的接口、PNG 几何不变。

- [ ] RED：

```python
t.group("质量 T3：非原点父容器的局部范围")
for bounds, expected in [([0, 0, 50, 50], False), ([100, 100, 250, 250], True),
                         ([-1, 0, 10, 10], True), ([0, 0, 200, 200], False)]:
    parent = screenshot.JsonNode({"source": "dumpsys", "class": "Parent",
        "bounds_local": [100, 100, 300, 300], "children": [
            {"source": "dumpsys", "class": "Child", "bounds_local": bounds}]})
    t.eq(parent.children[0].chain_overflow() is not None, expected, "统一到父局部坐标系")
    nested = screenshot.JsonNode({"source": "a11y", "class": "Parent",
        "dumpsys": {"bounds_local": [100, 100, 300, 300]}, "children": [
            {"source": "a11y", "class": "Child", "dumpsys": {"bounds_local": bounds}}]})
    t.eq(nested.children[0].chain_overflow() is not None, expected, "嵌套 dumpsys 同判据")
```

- [ ] Run RED；内含/超出反例失败。
- [ ] 替换比较，告警打印的父范围也改为 parent_rect，不输出另一坐标系的 pb 原值；祖先遍历保留：

```python
b, pb = cur.rect_local(), cur.parent.rect_local()
parent_rect = (0, 0, pb[2] - pb[0], pb[3] - pb[1]) if pb else None
if b and parent_rect and (b[0] < 0 or b[1] < 0
                         or b[2] > parent_rect[2] or b[3] > parent_rect[3]):
    name = (cur["class"] or "?").rsplit(".", 1)[-1]
    rid = cur["resource_id"]
    return (f"祖先 {name}{('#' + rid.split('/')[-1]) if rid else ''} 的矩形 "
            f"{b[0]},{b[1]}-{b[2]},{b[3]} 超出其父容器局部范围 "
            f"0,0-{parent_rect[2]},{parent_rect[3]}（该容器有溢出内容）。"
            "dump 不含 scrollX/scrollY，这条链上的累加坐标无法验证")
```

- [ ] Run GREEN；继承祖先超界、缺失 bounds 不猜、顶层/嵌套来源和已有像素测试全绿。告警字句变化允许，PNG 应保持原字节，除非输入选择由其他任务产生明确变化。
- [ ] 若获授权：`fix(screenshot): 在同一局部坐标系检查父子溢出`。

## T4：区分损坏 XML 与合法空树（Q4）

**Files:** domain/tree/parsing.py:parse_u2_xml；tests。
**Interfaces:** parse_u2_xml(text) -> list，XML 格式损坏时改为 ValueError；collect_full_json 等签名不变，既有 CLI/MCP 异常边界转换结果。

- [ ] RED：

```python
t.group("质量 T4：损坏 XML 必须报告采集失败")
quality_value_error(lambda: parsing.parse_u2_xml("<hierarchy><node"), "纯解析报告失败")
t.eq(parsing.parse_u2_xml("<hierarchy/>"), [], "合法空 hierarchy 仍是空树")
snap = {"xml": "<hierarchy><node", "block": None, "pkg": None,
        "screen": {"width": 100, "height": 100}, "u2_meta": {}, "dev": {}, "win": {},
        "pick_note": None, "drift": False, "drift_detail": None}
with patch("tvuitree.infrastructure.snapshot.snapshot", return_value=snap):
    quality_value_error(lambda: application_observation.collect_full_json(
        adb=object(), serial="fixture", use_dumpsys=False), "采集不返回伪正常空树")
    with patch.object(observe_interface, "connect_for_cli", return_value=adb.Adb("adb", "fixture")):
        rc, out, err = quality_cli(["observe", "--no-dumpsys", "--quiet", "--no-color"])
    t.eq(rc, 3, "实时解析失败进入采集错误通道")
    t.eq(out, "", "失败不输出成功 JSON")
    t.ok("解析失败" in err and "ESCAPED" not in err, "中文受控诊断")
```

- [ ] Run RED。替身拦截实际 snapshot，不能访问设备。
- [ ] 修改捕获：

```python
try:
    root = ET.fromstring(xml_text)
except ET.ParseError as error:
    raise ValueError(f"a11y XML 解析失败：{error}") from error
```

- [ ] 同组追加以下 MCP RED，仍使用上面的 `snap`，之后 Run GREEN；已有空树正常输出保留：

```python
with patch("tvuitree.infrastructure.snapshot.snapshot", return_value=snap), \
     patch.object(mcp_interface, "_connect", return_value=(SimpleNamespace(serial="fixture"), "fixture")), \
     patch.object(timing, "LOG_STREAM", io.StringIO()):
    result = mcp_interface.observe_tv(no_dumpsys=True)
    calls = _timing_calls()
t.eq(result.get("focus", {}).get("status"), "error", "MCP 不伪报正常观察")
t.eq(result.get("full_tree_available"), False, "失败树不可用")
t.eq(calls, [("observe_tv", ["connect", "capture_tree"], "capture_tree")],
     "MCP 一次计时并定位解析失败阶段")
```
- [ ] 若获授权：`fix(parsing): 将损坏的主源 XML 明确报告为失败`。

## T5：full JSON 文件入口的最小结构契约（Q6）

**Files:** domain/tree/output.py 新增 validate_full_json；interfaces/json_io.py:load_full_json；tests。
**Interfaces:** validate_full_json(obj: object) -> dict，合法时返回同一对象且不改字段；不合法抛带字段路径的 ValueError。load_full_json(path: str) -> dict 保持签名。校验归属既有 full JSON 格式模块，文件读取留 interfaces。

接受规则：tree 必须为列表；node 必须为对象；children 缺失/None/列表均可；screen 缺失/None/对象均可，其宽高若给出为非负整数（visible 自行要求正数）；数值 bounds 非 bool、有限数、长度四，不凭空补坐标。允许未知字段、稀疏节点、未写 generator 的历史 fixture，不禁止已有 slim 文件形状。metadata 仅检查消费者实际调用 get 的字典；focus/dumpsys_only 是对象森林。

- [ ] RED 使用真实 loader，写入 TD 脱敏 JSON；坏输入断言 ValueError 和实际三个 CLI 2，无异常外漏。代码中的 bad 列表必须全部运行：

```python
t.group("质量 T5：嵌套 JSON 形状与兼容边界")
quality_path = Path(TD) / "quality_full.json"
bad_json = [{"tree": [None]}, {"tree": [{}], "screen": ["bad"]},
            {"tree": [{"children": {}}]}, {"tree": [{"text": 3}]},
            {"tree": [{"bounds_screen": [0, 0, True, 10]}]},
            {"tree": [{"bounds_screen": [0, 0, float("nan"), 10]}]},
            {"tree": [], "screen": {"width": "100"}}, {"tree": [], "focus": "bad"}]
for obj in bad_json:
    quality_path.write_text(json.dumps(obj), encoding="utf-8")
    quality_value_error(lambda: observe_interface.load_full_json(str(quality_path)),
                        "损坏结构在文件入口拒绝")
    for args in [["observe"], ["visible"], ["tree", "--mode", "slim"]]:
        rc, out, err = quality_cli([*args, "--from-json", str(quality_path), "--quiet", "--no-color"])
        t.eq(rc, 2, "损坏业务结构返回文件错误 2")
        t.ok("ESCAPED" not in err and "Traceback" not in err, "无异常外漏")
        t.eq(out, "", "失败不输出成功投影")
for obj in [{"tree": [], "note": "保留未知字段"},
            {"tree": [{"children": None, "bounds_screen": None}], "screen": {}},
            {"tree": [], "screen": {"width": 0, "height": 0}}]:
    quality_path.write_text(json.dumps(obj), encoding="utf-8")
    t.eq(observe_interface.load_full_json(str(quality_path)), obj, "稀疏合法结构不被补写或删字段")
```

- [ ] Run RED；原 loader 仅验证 tree 列表，多数错误被接受或外漏。
- [ ] 在 output.py 加 `import math`，新增如下纯函数。模块 docstring 改为一行 English 的 full JSON serialization/validation 职责；不增加文件操作：

```python
def validate_full_json(obj: object) -> dict:
    """校验消费者实际依赖的形状；保留缺失读数和未知字段。"""
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError("full JSON 缺少 tree 列表")
    def fail(path: str) -> None:
        raise ValueError(f"full JSON 字段结构无效：{path}")
    def optional_object(value: object, path: str) -> None:
        if value is not None and not isinstance(value, dict):
            fail(path)
    def bounds(value: object, path: str) -> None:
        if value is None:
            return
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            fail(path)
        if any(isinstance(x, bool) or not isinstance(x, (int, float))
               or (isinstance(x, float) and not math.isfinite(x)) for x in value):
            fail(path)
    def forest(nodes: object, path: str) -> None:
        if nodes is None:
            return
        if not isinstance(nodes, list):
            fail(path)
        for index, node in enumerate(nodes):
            here = f"{path}[{index}]"
            if not isinstance(node, dict):
                fail(here)
            for key in ("class", "resource_id", "text", "content_desc", "hint", "package", "source"):
                value = node.get(key)
                if value is not None and not isinstance(value, str):
                    fail(f"{here}.{key}")
            for key in ("enabled", "focused", "selected", "checked", "visible", "visible_to_user",
                        "gone", "clickable", "focusable", "checkable", "long_clickable", "scrollable"):
                value = node.get(key)
                if value is not None and not isinstance(value, bool):
                    fail(f"{here}.{key}")
            for key in ("bounds_screen", "bounds_local", "bounds_abs_unclipped", "pred_visible_rect"):
                bounds(node.get(key), f"{here}.{key}")
            nested = node.get("dumpsys")
            optional_object(nested, f"{here}.dumpsys")
            if nested:
                for key in ("bounds_local", "bounds_abs_unclipped", "pred_visible_rect"):
                    bounds(nested.get(key), f"{here}.dumpsys.{key}")
            forest(node.get("children"), f"{here}.children")
    forest(obj["tree"], "tree")
    forest(obj.get("dumpsys_only"), "dumpsys_only")
    forest(obj.get("focus"), "focus")
    for key in ("screen", "align_stats", "source_consistency", "device", "window"):
        optional_object(obj.get(key), key)
    screen = obj.get("screen") or {}
    for key in ("width", "height"):
        value = screen.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            fail(f"screen.{key}")
    stamp = obj.get("captured_at")
    if stamp is not None and not isinstance(stamp, str):
        fail("captured_at")
    return obj
```

json_io.py 导入 `from tvuitree.domain.tree.output import validate_full_json`，load_full_json 的 json.load 之后改为 `return validate_full_json(obj)`，移除重复顶层判断。未知字段不丢弃；无需给每个元数据子字段建立模型。

- [ ] Run GREEN，既有真实 full fixture、golden/raw、minimal serialization fixture 和 shot 读取继续通过。在已有 `tree_output` 模块别名下追加 `t.ok(tree_output.validate_full_json(obj) is obj, "合法对象未被转换或清洗")`，证明不是转换或清洗。
- [ ] 若遇见新增校验与仓内真实字段不符，核对 output.build_full_json 与消费者再调整，仅记录已证明的合法形状；不要为了取得绿色把所有校验删除。
- [ ] 若获授权：`fix(json): 在文件入口校验实际消费的嵌套结构`。

## T6：连接查询共享可用状态判据（Q7）

**Files:** infrastructure/adb.py:_serial_is_device/connect；tests。
**Interfaces:** 新增纯 `_device_targets(out: str) -> list[str]`，仅列出状态为 device 的 serial；connect/恢复接口不变，不增加一次额外 devices 查询。

- [ ] RED；设备替身位于 subprocess.run，真实 _popen 负责 bytes 解码：

```python
t.group("质量 T6：连接仅接受 device 状态")
for state in ["device", "offline", "unauthorized"]:
    def quality_devices(command, **kwargs):
        return subprocess.CompletedProcess(command, 0,
            f"List of devices attached\nfixture:5555\t{state}\n".encode(), b"")
    for serial in ["fixture:5555", None]:
        device = adb.Adb("adb", serial, auto_connect=False)
        device._connected = True
        with patch.object(adb.subprocess, "run", side_effect=quality_devices) as process:
            t.eq(device.connect(quiet=True), state == "device", "初始连接核对可用状态")
        t.eq(process.call_count, 1, "no_connect 仅一次状态查询")
        t.eq(device._connected, state == "device", "不保留陈旧状态")
        if state != "device":
            t.eq(device.serial, serial, "失败不抢占目标")
```

- [ ] Run RED，offline/unauthorized 返回 True 的断言失败。
- [ ] 定义 helper，支持 adb devices 列之间的普通空白；先确认 rc=0 的职责仍在调用方：

```python
def _device_targets(out: str) -> list[str]:
    """返回列表中状态确认为 device 的 serial。"""
    targets = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            targets.append(parts[0])
    return targets
```

connect 的 targets 列表改为 `_device_targets(out)`；指定 serial 检查该列表；自动选择只从该列表选择，多于一台可用设备仍拒绝，serial 不变。_serial_is_device 在已有 rc 检查之后 `return self.serial in _device_targets(out)`，删除旧重复循环。保留 quiet 文案与恢复日志；不根据 connect 文案猜成功。

- [ ] 同组追加混合列表及两台可用设备的 RED，helper 按实际列解析，不用子串匹配：

```python
for listing, serial, expected, resulting in [
    ("fixture:5555\toffline\nother:5555\tdevice\n", "fixture:5555", False, "fixture:5555"),
    ("fixture:5555\toffline\nother:5555\tdevice\n", None, True, "other:5555"),
    ("fixture:5555\tdevice\nother:5555\tdevice\n", None, False, None),
]:
    device = adb.Adb("adb", serial, auto_connect=False)
    completed = subprocess.CompletedProcess([], 0,
        ("List of devices attached\n" + listing).encode(), b"")
    with patch.object(adb.subprocess, "run", return_value=completed) as process:
        t.eq(device.connect(quiet=True), expected, "混合状态只选可用目标，多设备拒绝猜测")
    t.eq(device.serial, resulting, "目标选择或保留符合契约")
    t.eq(process.call_count, 1, "不增加状态查询")
```

同时更新 connect 原有关于“仅检查 serial 存在”的注释，反映新的可用状态判据。
- [ ] Run GREEN；T2/T3 前轮连接异常、查询 rc、单次恢复链都继续绿。README 的 no_connect 行为在 T10 写明仍查询可用状态。
- [ ] 若获授权：`fix(adb): 统一初始连接与恢复的设备状态判据`。

## T7：实际运行错误进入既有 CLI 出口（Q5）

**Files:** interfaces/input.py、interfaces/shot.py；tests。
**Interfaces:** run_input/run_shot 返回 int；不吞所有编程异常，只处理实际外部边界异常。

- [ ] tests 导入 interfaces input/shot 两模块（英文别名 `input_interface` / `shot_interface`），与首次使用同一任务加入，不能留下未用导入。RED：

```python
t.group("质量 T7：运行失败有受控 CLI 出口")
from tvuitree.interfaces import input as input_interface, shot as shot_interface
device = adb.Adb("adb", "fixture", auto_connect=False)
with patch.object(input_interface, "connect_for_cli", return_value=device), \
     patch.object(device, "shell_raw", side_effect=adb.AdbError("injected timeout")):
    rc, out, err = quality_cli(["input", "DOWN", "--quiet", "--no-color"])
t.eq(rc, 1, "按键执行失败返回 1")
t.ok("发送失败" in err and "ESCAPED" not in err, "按键失败中文诊断")
path = Path(TD) / "quality_shot.json"
path.write_text(json.dumps({"tree": []}), encoding="utf-8")
png_path = Path(TD) / "quality_bad.png"
png_path.write_bytes(b"not a png")
rc, out, err = quality_cli(["shot", "--json", str(path), "--image", str(png_path),
                            "--out", str(Path(TD) / "quality-shot.png"), "--quiet", "--no-color"])
t.eq(rc, 1, "无效图片返回 shot 自身失败 1")
t.ok("画框失败" in err and "ESCAPED" not in err, "无图片异常外漏")
with patch("tvuitree.application.screenshot.render", side_effect=OSError("injected output failure")):
    rc, out, err = quality_cli(["shot", "--json", str(path), "--image", str(png_path), "--quiet", "--no-color"])
t.eq(rc, 1, "输出失败进入同一 shot 出口")
t.ok("[out]" not in out and "ESCAPED" not in err, "失败不打印成功摘要")
with patch.object(shot_interface, "connect_for_cli", return_value=None):
    rc, out, err = quality_cli(["shot", "--json", str(path), "--quiet", "--no-color"])
t.eq(rc, 2, "shot 连接失败仍返回 2")
with patch.object(input_interface, "connect_for_cli", return_value=None):
    rc, out, err = quality_cli(["input", "DOWN", "--quiet", "--no-color"])
t.eq(rc, 2, "input 连接失败仍返回 2")
```

- [ ] Run RED，旧 input/shot 异常为 -999。
- [ ] input.py 导入 AdbError，在现有 send_sequence 的 for 循环外加 try/except；保留每条返回错误时累积 failures 的现有行为：

```python
try:
    for keycode, error in send_sequence(device, keys, delay=args.delay, repeat=args.repeat):
        if error:
            failures += 1
            print(c(f"  {keycode:<20} 发送失败：{error}", C.RED), file=sys.stderr)
        elif not args.quiet:
            print(f"  {keycode}")
except (AdbError, OSError) as error:
    print(c(f"发送失败：{type(error).__name__}: {error}", C.RED), file=sys.stderr)
    return 1
```

shot.py 将 render 行包为：

```python
try:
    result = render(obj, png, args.out, draw=args.draw, source=args.source, width=args.width)
except (OSError, ValueError) as error:
    print(c(f"画框失败：{type(error).__name__}: {error}", C.RED), file=sys.stderr)
    return 1
```

Pillow 的无效图片异常属 OSError，不把 PIL 导入 domain，也不捕获所有 Exception。load/read/capture 既有出口保留；截图成功后的 notes、PNG 和输出形式保持现状。

- [ ] 同任务修正合法 ISO 时区的年龄比较，保留 ValueError 时跳过年龄提示的既有规则；T5 已拒绝非字符串 captured_at。将 age 计算一行替换为：

```python
when = dt.datetime.fromisoformat(captured_at)
age = (dt.datetime.now(when.tzinfo) - when).total_seconds()
```

该边界同组加入以下 RED，正常 2×2 PNG 离线画框不应外漏 TypeError：

```python
import datetime as quality_datetime
from PIL import Image as QualityImage
path.write_text(json.dumps({"tree": [],
    "captured_at": quality_datetime.datetime.now(quality_datetime.timezone.utc).isoformat()}),
    encoding="utf-8")
QualityImage.new("RGB", (2, 2)).save(png_path)
output_path = Path(TD) / "quality-timezone-shot.png"
rc, out, err = quality_cli(["shot", "--json", str(path), "--image", str(png_path),
                            "--out", str(output_path), "--quiet", "--no-color"])
t.eq(rc, 0, "合法带时区时间可正常离线画框")
t.ok(output_path.exists(), "成功确实产生 PNG")
t.ok("ESCAPED" not in err, "合法时间无 TypeError 外漏")
```
- [ ] Run GREEN，input list/正常按键返回值/shot 正常像素回归保持绿；若获授权：`fix(cli): 将按键与图片运行失败转换为受控诊断`。

## T8：发送前完整验证键码序列（Q8）

**Files:** application/input.py:normalize_keycode/send_sequence；interfaces/input.py:run_input；tests。依赖 T7 的实际执行失败出口。
**Interfaces:** normalize_keycode(name: str) -> str，非法语法抛 ValueError。允许别名、标识符、完整 KEYCODE_*、ASCII 数字；不列举所有 Android 枚举常量，语法合法但系统不支持的键仍由设备报告失败。

- [ ] RED：

```python
t.group("质量 T8：非法键码不触发任何设备操作")
for name in ["DOWN; :", "3 4", "HOME|:", "KEYCODE_", "$(X)", "", "２０"]:
    quality_value_error(lambda: remote_input.normalize_keycode(name), "拒绝非单个键码语法")
device = adb.Adb("adb", "fixture", auto_connect=False)
with patch.object(input_interface, "connect_for_cli", return_value=device) as connect, \
     patch.object(device, "shell_raw", return_value=(0, "", "")) as shell:
    rc, out, err = quality_cli(["input", "DOWN,HOME; :", "--quiet", "--no-color"])
t.eq(rc, 2, "非法序列返回用法错误 2")
t.eq(connect.call_count, 0, "整段预检在连接之前")
t.eq(shell.call_count, 0, "后段非法不能先发前段")
with patch.object(device, "shell_raw", return_value=(0, "", "")) as shell:
    quality_value_error(lambda: list(remote_input.send_sequence(
        device, ["DOWN", "HOME; :"], delay=0)), "Python API 整段预检")
t.eq(shell.call_count, 0, "API 也不产生部分副作用")
for value, expected in [(" down ", "KEYCODE_DPAD_DOWN"), ("dpad_down", "KEYCODE_DPAD_DOWN"),
                        ("KEYCODE_HOME", "KEYCODE_HOME"), ("20", "20"), ("KEYCODE_3", "KEYCODE_3")]:
    t.eq(remote_input.normalize_keycode(value), expected, "正常语法与别名保留")
```

- [ ] Run RED，旧 normalize 与 CLI 将元字符传入 shell。
- [ ] application/input.py 导入 re；函数改为：

```python
def normalize_keycode(name: str) -> str:
    """归一化单个键码；非法语法在任何设备操作前拒绝。"""
    k = name.strip()
    if re.fullmatch(r"[0-9]+", k):
        return k
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", k):
        raise ValueError(f"非法键码：{name!r}")
    k = KEY_ALIASES.get(k.upper(), k.upper())
    code = k if k.startswith("KEYCODE_") else "KEYCODE_" + k
    if not re.fullmatch(r"KEYCODE_[A-Z0-9][A-Z0-9_]*", code):
        raise ValueError(f"非法键码：{name!r}")
    return code
```

send_sequence 开头新增 `keys = [normalize_keycode(key) for key in keys]`，在第一条 send_key 前验证全段，保留 delay/repeat/sleep 时序。

run_input 在解析 keys/非空检查之后、connect 之前调用完整预检：

```python
try:
    keys = [normalize_keycode(key) for key in keys]
except ValueError as error:
    print(c(str(error), C.RED), file=sys.stderr)
    return 2
```

将 normalize_keycode 加入原 application.input 导入列表。T7 的执行异常出口仍处理实际 ADB 失败；不要把所有错误都归类为用法错误。send_key 内也保留 normalize，防直接 API 绕过。

- [ ] Run GREEN，按键不做真实设备测试；若获授权：`fix(input): 发送前验证单个键码及完整序列`。

## T9：保留有证据的无标签操作控件（Q9）

**Files:** domain/visible.py:targets/summary/page_nodes；tests。依赖 T2 的明确禁用状态。
**Interfaces:** select_visible(full_json) -> dict，schema_version/字段名/path/屏幕筛选不变。新增保留条件仅为当前可见 entries 中 clickable/long_clickable/checkable 的明确 True；空 layout、focusable-only 或仅 scrollable 容器不因本次条件新增。

- [ ] RED：

```python
t.group("质量 T9：无标签控件保留真实操作与状态")
for checked in [False, True]:
    node = {"source": "a11y", "class": "android.widget.Switch", "resource_id": "fixture:id/toggle",
            "bounds_screen": [0, 0, 20, 20], "checkable": True, "checked": checked,
            "enabled": False, "visible_to_user": True}
    result = domain_visible.select_visible({"tree": [node], "screen": {"width": 100, "height": 100}})
    items = result["page"]["nodes"]
    t.eq(len(items), 1, "有操作和坐标证据的 Switch 不遗漏")
    if items:
        t.eq(items[0].get("checked"), checked, "保留开关 False/True 读数")
        t.eq(items[0].get("enabled"), False, "不丢失 T2 的禁用状态")
        t.eq(items[0].get("resource_id"), "fixture:id/toggle", "保留已有标识")
        t.not_has(items[0], "labels", "不编造显示文字")
for flags in [{}, {"focusable": True}, {"scrollable": True}]:
    node = {"source": "a11y", "class": "android.widget.FrameLayout",
            "bounds_screen": [0, 0, 20, 20], **flags}
    t.eq(domain_visible.select_visible({"tree": [node], "screen": {"width": 100, "height": 100}})
         ["page"]["nodes"], [], "空容器不因弱证据膨胀输出")
```

- [ ] Run RED，Switch 当前消失。
- [ ] 在 targets 前新增并并入集合：

```python
actionable_paths = {path for path, node in entries
                    if any(node.get(key) is True for key in ("clickable", "long_clickable", "checkable"))}
targets = set(labels_by_path) | set(descriptions_by_path) | set(focused_paths) | actionable_paths
```

替换原 summary 字典筛选条件，保留现有键集合：focused/selected 只保留 True；checked 为 True 或原节点 checkable=True 时保留（于是 False 是有效开关读数）；enabled 仅保留 False。其它键条件原样保留：

```python
summary = {key: raw[key] for key in
           ("path", "source", "class", "resource_id", "bounds", "bounds_kind",
            "actions", "focused", "selected", "checked", "enabled")
           if key in raw
           and (key not in ("focused", "selected") or raw[key] is True)
           and (key != "checked" or raw[key] is True or by_path[path].get("checkable") is True)
           and (key != "enabled" or raw[key] is False)}
```

page_nodes 的追加条件新增 `or path in actionable_paths`。标签分组/截断去重、source=a11y、屏幕交集、path/focus 判定不改；不借机新增点击坐标推断。

- [ ] 同组追加以下接口及隐藏/屏外 RED，使用 T0 公共工具，随后 Run GREEN：

```python
toggle = {"source": "a11y", "class": "android.widget.Switch",
          "resource_id": "fixture:id/toggle", "bounds_screen": [0, 0, 20, 20],
          "checkable": True, "checked": False, "enabled": False, "visible_to_user": True}
full = {"tree": [toggle], "screen": {"width": 100, "height": 100}}
cli_o, mcp_o, cli_v, mcp_v = quality_projection_interfaces(full)
for projected in [cli_v, mcp_v]:
    items = projected.get("page", {}).get("nodes", [])
    t.eq(len(items), 1, "各 visible 接口保留无标签开关")
    if items:
        t.eq(items[0].get("checked"), False, "各接口保留未选读数")
        t.eq(items[0].get("enabled"), False, "各接口保留禁用读数")
for overrides in [{"visible_to_user": False}, {"bounds_screen": [200, 200, 220, 220]}]:
    hidden = {**toggle, **overrides}
    projected = domain_visible.select_visible({"tree": [hidden], "screen": full["screen"]})
    t.eq(projected["page"]["nodes"], [], "操作性不覆盖隐藏或屏外证据")
```
- [ ] 若获授权：`fix(visible): 保留无标签操作控件及明确开关状态`。

## T10：文档、金样及集中终验

**Files:** README.md、docs/README.md、本计划执行状态、docs/reports/2026-10-03-code-quality-remediation-delivery.md。

- [ ] README 补充实际规则：R1 双向唯一；enabled=False 是禁用读数；无标签 Switch 可通过资源 ID/坐标/状态保留；no_connect 仍只接受 device；按键非法语法在连接前返回 2；input/shot 运行失败受控返回 1。保留现有剪枝、层目录和截图约定检查用语。
- [ ] 将 README Inspector“所需的四个工具”改为“所需的工具”，由既有六工具列表作为权威，不创建第二套列表。
- [ ] 生成自包含交付报告，逐 Q1–Q9 列出修复、测试位置、RED/GREEN、实际断言数、最终 HEAD/工作树、配置保护、金样差异及未完成检查；不能预填 APPROVE。
- [ ] 最终运行以下检查，预期全部 rc=0。中文断言相关测试子进程必须 `env=dict(os.environ, PYTHONIOENCODING="utf-8")` 且父进程按 UTF-8 解码；沿用前轮修复。

```powershell
Invoke-QualityChecks
& $py main.py --help
if ($LASTEXITCODE -ne 0) { throw 'help failed' }
& $py main.py tree --prune-list
if ($LASTEXITCODE -ne 0) { throw 'prune-list failed' }
```
- [ ] 在 `PYTHONUTF8=0`、移除 PYTHONIOENCODING 后重跑整个 selftest；再以显式 GBK 父进程重跑。两次都应 rc=0，不仅验证外部设置 UTF-8 的场景。用 subprocess.run(env=...) 隔离环境，不改系统环境或生产 terminal。

```python
import os
import subprocess
import sys
for encoding in [None, "gbk"]:
    env = dict(os.environ, PYTHONUTF8="0")
    env.pop("PYTHONIOENCODING", None)
    if encoding:
        env["PYTHONIOENCODING"] = encoding
    result = subprocess.run([sys.executable, "tests/selftest_tree.py"], env=env, capture_output=True)
    assert result.returncode == 0, result.returncode
```

## 金样与真实环境

T0 阅读现有 golden.py 后，将以下脚本保存为本轮证据目录中的 `golden_quality.py`。T0 用 `baseline`，T10 用 `final`；每个输出目录必须从未存在，续跑时保留原证据并人工选择新的本轮目录，不覆盖历史输出。缺素材时停止该检查，交付报告明确记录未验证。

```python
"""Generate isolated quality-review golden evidence."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[2]
phase = sys.argv[1] if len(sys.argv) == 2 else ""
if phase not in ("baseline", "final"):
    raise SystemExit("参数只能是 baseline 或 final")
out = (here / phase).resolve()
if out.parent != here or out.exists():
    raise SystemExit("目标必须位于本轮证据目录且尚不存在")
script = root / "_temp/golden/golden.py"
required = [script, root / "_temp/e2e/full.json", root / "_temp/e2e/shot_a11y.png",
            root / "_temp/raw/activity_top_before.txt", root / "_temp/raw/activity_top_after.txt",
            root / "_temp/raw/u2_hierarchy.xml"]
missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
if missing:
    raise SystemExit("缺少金样素材：" + ", ".join(missing))
spec = importlib.util.spec_from_file_location("quality_golden", script)
assert spec is not None and spec.loader is not None
golden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(golden)
# 已核对现有 generate 会清理 out；上面确保它是本轮范围内的新目录。
golden.generate(out)
for path in out.glob("*.txt"):
    assert path.read_bytes().rstrip().endswith(b"--- rc=0 ---"), f"命令失败：{path.name}"
if phase == "baseline":
    print("已建立独立执行基线")
    raise SystemExit(0)
base = here / "baseline"
assert base.is_dir(), "缺少本轮 baseline"
names = {path.name for path in base.iterdir() if path.is_file()}
assert names == {path.name for path in out.iterdir() if path.is_file()}, "文件集合变化"

def differences(old: object, new: object, path: str = "$") -> list[dict]:
    """记录具体 JSON 路径，不归一 False、坐标、标签或顺序。"""
    if type(old) is not type(new):
        return [{"path": path, "before": old, "after": new}]
    if isinstance(old, dict):
        result = []
        for key in sorted(set(old) | set(new)):
            child = f"{path}.{key}"
            if key not in old or key not in new:
                result.append({"path": child, "before_exists": key in old,
                               "after_exists": key in new, "before": old.get(key), "after": new.get(key)})
            else:
                result.extend(differences(old[key], new[key], child))
        return result
    if isinstance(old, list):
        if len(old) != len(new):
            return [{"path": path, "before": old, "after": new}]
        return [item for index, (a, b) in enumerate(zip(old, new))
                for item in differences(a, b, f"{path}[{index}]")]
    return [] if old == new else [{"path": path, "before": old, "after": new}]

changes = []
for name in sorted(names):
    before, after = (base / name).read_bytes(), (out / name).read_bytes()
    if before == after:
        continue
    item = {"file": name, "before_sha256": hashlib.sha256(before).hexdigest(),
            "after_sha256": hashlib.sha256(after).hexdigest()}
    if name.endswith(".json"):
        item["json_changes"] = differences(json.loads(before), json.loads(after))
    changes.append(item)
(here / "golden-differences.json").write_text(
    json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8")
assert not any(item["file"].endswith(".png") for item in changes), "正常 PNG 发生变化，需先调查"
print(f"{len(names)} 个文件，{len(changes)} 个不同；每项须人工溯源后才能验收")
```

```powershell
# T0：先生成基线，再开始 T1。
& $py "$evidence/golden_quality.py" baseline
if ($LASTEXITCODE -ne 0) { throw 'fresh golden baseline failed' }
# T10：生成最终结果并记录差异；脚本成功不代表所有差异已获接受。
& $py "$evidence/golden_quality.py" final
if ($LASTEXITCODE -ne 0) { throw 'fresh golden final failed' }
```

当前 golden.py 已将输出目录和随时间变化的截图年龄替换为占位符；除此之外仍按生成文件字节比较，不额外放宽规则。逐项阅读 golden-differences.json；对不同的 .txt 再直接查看具体文本 diff（含 stdout、stderr、rc）。把每项关联到下列许可和实际输入；解释不清的差异必须调查，不能只列“有意变更”。

1. T0 动代码前建立新的执行基线，核对本地 `_temp/golden/golden.py` 和素材存在。生成函数可能清理目标目录，必须先读脚本，用从未存在的新目录，不触碰旧 base/now 或上一轮 evidence。缺素材时列出缺项，不伪造通过。
2. 后续 fresh 输出与本轮基线比较文件集合及原始字节，生成每个差异的记录。默认没有许可去覆盖旧金样或运行 make。
3. **允许变化名单必须按实际输入核对：** T1 有逆向歧义的匹配/关联字段及统计、align_rules.R1 的准确说明；T2 enabled=False；T3 告警文字与有无；T4 原先损坏 XML 的错误输出；T5–T8 本就无效输入/连接的受控失败；T9 无标签操作节点/checked=False；对应 stderr 的输出字节数允许随这些具体 JSON 内容变化。
4. 没有命中上述输入的输出应逐字节不变。正常 PNG 应不变；正常 observe/visible JSON 因有效字段新增可能改变，必须逐条解释，不能全局忽略 False、数字、标签、告警或顺序。
5. TV 可用时沿用用户既有只读实验授权，核对当前设备状态，采集 full + 单源 visible/observe，再离线投影及 screenshot 比较。shot 输入只能是 full JSON；所有产物放本轮 _temp，报告脱敏。不通过主动 disconnect 或真机按键制造验证场景。
6. TV 不可达时记未完成真机 QA，不阻塞离线结果；实际 MCP stdio 成功/错误路径、接口函数离线测试、真机行为三者分别记录。若没有真实 stdio 宿主，仅宣称离线接口覆盖。

## 自检与提交护栏

- [ ] 每个新片段导入齐全，t.eq 参数顺序是 got/want/what；异常用宽捕获后类型断言，RED 必须正常汇总。
- [ ] 只改本任务涉及的既有断言；如谓词收紧导致旧“geom”成为“seq/unpaired”，写出该 fixture 的真实证据依据后同步 EXP，不机械追求旧配对数。
- [ ] tests 中截图源文本限制、按键命令唯一归属、README 检查继续通过；业务校验不能通过 monkeypatch 生产实现实现。
- [ ] 最终比对 config SHA256；若用户并行改配置，不执行 restore/checkout，而是记录归属。保留 `.omo/`、`.zcodeignore` 和本轮计划/评审资料。
- [ ] docs 相对链接存在，计划代码块语法可解析，正式报告内容能脱离 _temp 理解。
- [ ] 有可用独立审查者时只安排一次集中只读终审，绑定最终 HEAD 与未提交 diff，覆盖五项 Review Focus；无审查者则明确自审，不能伪造代理 APPROVE。重要发现经有效回归修复再跑全套检查。

用户若在 DeepSeek 执行阶段授权本地提交，每个任务先验证，再精确暂存该任务的生产文件和自检差异块。共享 selftest/input/visible 不可把后续未验证差异混入提交，不执行 git add .。示例 T1：

```powershell
git add -- tvuitree/domain/tree/matching.py
git add -- tvuitree/domain/tree/output.py
# selftest 按本任务差异块暂存，核对 staged 内容后才提交。
git diff --cached --check
git diff --cached --stat
git commit -m 'fix(matching): 仅绑定双向唯一的几何候选'
```

其余采用各任务给出的 Conventional Commits，T10 使用 `docs(quality): 记录观测补修行为与实际验收`。未经新授权不推送，不把前一轮推送授权扩大到本计划。

## 原交接给 DeepSeek 的执行提示（历史保留）

> 读取本计划、对应 Q1–Q9 评审和 AGENTS.md；保留当前 docs、配置及工具状态。从 T0 建立基线，按 T1–T10 串行执行，逐项 RED→GREEN 和必要检查。遇到片段/既有断言与真实契约不符时先核实最小修正并写执行裁定，不能通过删断言、宽松金样归一、无依据回退或扩大重构范围取绿。最终把自包含交付写入指定 docs/reports，真实设备未验证则明确列出。默认不提交或推送，提交授权到来后严格按任务边界处理。

## 计划自审记录

- Q1–Q9 分别映射 T1、T2、T3、T4、T7、T5、T6、T8、T9；五项 Review Focus 有对应回归。
- T5 不强制合法空树含屏幕正数、不删除未知字段；T4 合法空 XML 保持支持；T2 不将 None 转成 False。
- T6 与前轮“初始连接暂不改”的范围不同，当前整体评审及用户方案已包含它；不以旧限定阻止本轮有意行为变化。
- T3 未修改绘图几何，T8 不执行真实按键，T9 不猜标签/焦点。依赖与框架维护项已明确排除。
- 执行方式已由用户改为 Codex，已在 codex/code-quality-remediation 的托管 worktree 实施；不要求用户再次选择执行代理。
- 交接自检：31 个 Python 代码块通过 AST 解析；拟议纯校验函数在内存中接受仓内保存的真机 full JSON 和稀疏合法输入；计划及索引的链接存在。主要 RED 片段已在未修改代码上用隔离替身试跑，失败对应当前缺陷，未访问设备。此记录证明交接片段可执行，不是修复后的 GREEN 或完整终验结果。
