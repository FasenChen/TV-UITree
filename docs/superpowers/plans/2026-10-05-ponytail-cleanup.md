# Ponytail 清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落实已复核的 7 项复杂度建议，消除闲置代码、重复判断和截图中转文件，保持已有输出与失败语义。

**Architecture:** 保持四层和 full JSON 数据流。在现有模块删除无消费者实现；几何分级统一到 geom_of；截图文件和字节入口共用一个私有绘图核心。不开新模块，不新增依赖。

**Tech Stack:** Python 3.10+、现有 .venv、Pillow、uiautomator2、MCP、pyflakes、tests/selftest_tree.py；使用 PowerShell。

**Spec:** [审查复核](../../reviews/2026-10-05-ponytail-audit-review.md)为本计划的范围和边界依据；[原审查](../../reviews/2026-10-05-ponytail-audit.md)的编号用于追踪。代码基线 `a220fc2d8a2636669333e344d146fb33d25ce1a0`。本文保留计划正文，已执行步骤已勾选；实施与授权状态见末尾执行记录。

## Global Constraints

- 保留 R0–R3、唯一配对和插入规则、OWNER_PRIORITY、读数/派生值、未知焦点、所有 JSON 字段及退出码。不要改 generator 的 tv_tree.py。
- 保留 full/slim/observe/visible 的顺序、摘要上限与截断；无 dumpsys 时的分支语义保持不变。
- 绘图坐标、线宽、边沿、标签告警、drawn/skipped/notes 不变。MCP 仍落盘新截图，stderr 的 timing/save 阶段保持不变。
- 保留 config.json、.omo 和全部无关本地修改。仓外内部符号调用未检查，不引入推测性的兼容包装。
- 本次只交付计划。后续实施须先由用户审阅并选择执行方式；Git 提交须另有明确授权，推送/合并须确认目标及范围。下文提交步骤都是条件步骤。
- 不以净减少 60 行或性能改善作为验收指标。新私有绘图核心只有两个当前真实消费者。
- selftest 是单个脚本，没有 pytest 或单测试选择。删除闲置代码及等价重构不制造人为 RED；新增断言锁定真实契约，可以在重构前通过。仅“字节渲染无需临时目录”的新约束预期先失败。
- 原始验证脚本与日志留在 ignored _temp，不进入 docs。生产模块遵守现有注释、类型和依赖方向。

## Review Focus

| 输入或失败模式 | 必须锁定的结果 | 负责验证 |
|---|---|---|
| 无坐标、祖先裁剪、屏幕裁剪及偏移 | geom 四档统计和节点分类一致，配对总数不变 | 任务 2 的 6 类样例及现有 R0–R3/守恒组 |
| 两个根、多个孩子及空树 | 多根逆序、孩子原序、对象身份和空列表不变 | 任务 2 的遍历断言 |
| 重复标签/同一字典在不同位置、上限 1/2、缺失/歧义/唯一焦点 | 不按标签或身份去重，截断和焦点上下文不变 | 任务 1 的摘要断言及现有观测组 |
| 不存在文件、坏 JSON、数组/null、缺 tree、tree 类型错误 | 库层 OSError/ValueError；shot 返回 1、stderr 有解释、不生成 PNG | 任务 3 迁移第 7 组 6 类输入；保留现有嵌套校验组 |
| 文件 PNG/JPEG、字节 PNG、缺 Pillow、非法 PNG | 格式推断、字节/像素与提示一致；字节路径无需临时目录；错误仍抛出 | 任务 4 新回归组及现有像素/MCP 测试 |

## 文件与接口地图

路径均相对仓库根 `D:\Code\tv-uitree`。

| 文件 | 修改职责 |
|---|---|
| tvuitree/domain/tree/models.py | 删除 A11Y_ATTRS、Node.label、U2Node.bounds_str |
| tvuitree/domain/screenshot.py | 删除无调用的 walk；JsonNode 保留 |
| tvuitree/domain/observation.py | 删除闲置子摘要开关与路径集合 |
| tvuitree/interfaces/tree.py | 删除 _summary.out_path 及专属 Optional 导入 |
| tvuitree/domain/tree/matching.py | geom_of 统一统计、复用遍历、裁剪实现合并、缩减 build_unified 参数 |
| tvuitree/domain/tree/parsing.py | 删除 parse_node_line.indent；更新 iter_nodes 注解 |
| tvuitree/domain/tree/output.py | 更新 build_unified 调用；build_full_json 签名不变 |
| tvuitree/infrastructure/image.py | 删除 load_tree；字节渲染使用 BytesIO，共享绘图核心 |
| tests/selftest_tree.py | 按真实调用迁移读取测试、更新旧签名断言、补行为边界 |
| docs/reports/2026-10-05-ponytail-cleanup-delivery.md、docs/README.md | 后续实施完成后记录实际改动/验证并更新索引 |

## 执行准备与通用验证

- [x] 从根目录读取当前 AGENTS.md，运行下面只读检查。HEAD 已变化时对受影响定义及调用重新复核；不 reset 用户内容。

```powershell
git status --short
git rev-parse HEAD
Test-Path -LiteralPath '.venv\Scripts\python.exe'
rg -n 'A11Y_ATTRS|include_children|included_paths|pred_noscreen|_clip_ancestors|load_tree|build_unified|parse_node_line|draw_boxes_png' tvuitree tests scripts
```

- [x] 实施前跑一次当前完整基线；失败则记录并排查，不把原有失败记为本次回归。只用本地环境，不联网安装。

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe tests\selftest_tree.py
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe main.py tree --prune-list
git diff --check
```

各任务最后运行下列检查块一次；出现失败时修复本任务并重新跑受影响检查。新增代码没有改变边界时不要无限扩大检查。

```powershell
$pythonFiles = @('main.py') + (Get-ChildItem tvuitree, tests -Filter '*.py' -Recurse | ForEach-Object { $_.FullName })
.\.venv\Scripts\python.exe -m py_compile $pythonFiles
.\.venv\Scripts\python.exe -m pyflakes $pythonFiles
.\.venv\Scripts\python.exe tests\selftest_tree.py
git diff --check
```

预期四条命令退出码均为 0，自检无 FAIL。条数会因新增回归增长，不用固定 1087 作为通过条件。

## Task 1：删除无消费者代码与摘要闲置选项

**对应原建议：** 1、3、7 的 _summary。

**Files:** 修改 models.py、domain/screenshot.py、domain/observation.py、interfaces/tree.py、tests/selftest_tree.py。

**Contracts:**
- Consumes: `summarize_full_json(full_json: dict, *, max_nodes: int = DEFAULT_MAX_NODES, parse_anomalies: Optional[list] = None) -> dict` 的现有结果，`_focus_context` 的位置关系。
- Produces: `node_summary(node: dict, path: tuple[int, ...]) -> dict`；`_summary(obj: dict) -> None`；所有调用同步。上述生产文件不再提供原建议 1 的四个闲置符号。

- [x] **Step 1：在 selftest 收尾前添加第 34 组，先锁定摘要契约。** 这是重构保护测试，当前实现应通过；不要求人为失败。

```python
t.group("34. Ponytail 清理：摘要位置、上限与焦点上下文")
cleanup_same = {"text": "重复标签", "focused": True,
                "children": [{"text": "子控件"}]}
cleanup_full = {"tree": [cleanup_same, cleanup_same]}
for cleanup_cap, cleanup_paths in [(1, ["0"]), (2, ["0", "0/0"])]:
    cleanup_summary = domain_observation.summarize_full_json(
        cleanup_full, max_nodes=cleanup_cap)
    t.eq([n["path"] for n in cleanup_summary["page"]["nodes"]],
         cleanup_paths, "摘要按树位置保留顺序和上限")
    t.eq(cleanup_summary["page"]["summary_truncated"], True, "达到上限报告截断")
    t.eq(cleanup_summary["focus"]["status"], "ambiguous", "两处 focused 不猜测目标")
cleanup_summary = domain_observation.summarize_full_json(cleanup_full)
t.eq([n["path"] for n in cleanup_summary["page"]["nodes"]],
     ["0", "0/0", "1", "1/0"], "相同标签和相同对象不丢失不同路径")
cleanup_summary = domain_observation.summarize_full_json({"tree": [cleanup_same]})
t.eq(cleanup_summary["focus"]["status"], "found", "唯一焦点保留")
t.eq(cleanup_summary["focus"]["context"]["children"][0]["path"],
     "0/0", "删子摘要选项后仍保留焦点孩子上下文")
t.eq(cleanup_summary["focus"]["node"]["children_count"], 1, "保留直接孩子数量")
cleanup_summary = domain_observation.summarize_full_json({"tree": [{}]}, max_nodes=1)
t.eq(cleanup_summary["focus"]["status"], "missing", "无读数不猜测焦点")
t.eq(cleanup_summary["page"]["nodes"][0]["path"], "0", "无有意义节点保留首节点回退")
t.eq(cleanup_summary["page"]["summary_truncated"], False, "回退不误报截断")
```

运行 `.\.venv\Scripts\python.exe tests\selftest_tree.py`，预期所有组通过。

- [x] **Step 2：删除四个定义。** 删除 A11Y_ATTRS 的专属注释与整个元组；删除下面两个属性块和 walk 整个函数。U2Node.bounds_str 的同名实现删除，Node.bounds_str 不动。

```python
# 从 Node 删除此属性块。
@property
def label(self) -> str:
    s = self.short_cls
    if self.res_id:
        s += f"#{self.res_id}"
    return s

# 仅从 U2Node 删除此属性块。
@property
def bounds_str(self) -> Optional[str]:
    if not self.bounds:
        return None
    l, t, r, b = self.bounds
    return f"{l},{t}-{r},{b}"

# 从 domain/screenshot.py 删除此函数。
def walk(nodes: list, parent=None):
    """(node, parent) 深度优先。"""
    for n in nodes:
        yield n, parent
        yield from walk(n.get("children") or [], n)
```

- [x] **Step 3：收紧摘要和显示函数。** node_summary 改为下面签名，删除 include_children 的完整分支，其余字段复制与 children_count 不动。将 candidates 的显式 False 调用改为双参数。只删除页面循环的集合及成员判断，不修改 break/回退/truncated。

```python
def node_summary(node: dict, path: tuple[int, ...]) -> dict:
```

```python
candidates.append(node_summary(node, path))
```

```python
page_nodes = []
for node, path, _parent in items:
    if _meaningful(node):
        page_nodes.append(node_summary(node, path))
    if len(page_nodes) >= max_nodes:
        break
```

tree.py 删除仅被旧参数使用的 `from typing import Optional`，签名与调用分别为：

```python
def _summary(obj: dict) -> None:
```

```python
_summary(result)
```

- [x] **Step 4：执行通用验证块，检查只改变本任务文件。** 新第 34 组与原有摘要、visible、shot 像素测试均通过；不得通过减少有效断言获得通过。
- [x] **Step 5：若用户明确授权提交，检查 diff 后提交本任务；否则记录未提交。** 不暂存本轮审查文档或其他任务文件。

```powershell
git add -- tvuitree/domain/tree/models.py tvuitree/domain/screenshot.py tvuitree/domain/observation.py tvuitree/interfaces/tree.py tests/selftest_tree.py
git commit -m 'refactor(summary): 删除闲置属性与摘要选项'
```

## Task 2：统一几何、遍历与内部参数

**对应原建议：** 2、5、7 的 build_unified/parse_node_line。

**Files:** 修改 matching.py、parsing.py、output.py、tests/selftest_tree.py。

**Contracts:**
- Consumes: `geom_of(u: U2Node, screen: Optional[tuple]) -> str`，返回 exact/clip/drift/na；Node/U2Node.children 的现有列表。
- Produces: `build_unified(u2_roots: list, screen: Optional[tuple]) -> list`；`parse_node_line(text: str, lineno: int, anomalies: Optional[list] = None) -> Optional[Node]`；`clip_to_chain(node: Node) -> Optional[tuple]`；`u2_all(roots: list) -> list` 保留 list 返回。build_full_json 签名不变。

- [x] **Step 1：添加第 35 组。** 放在第 34 组后、收尾前。当前应通过；这里保护分级优先级、统计与遍历，不依赖已删除符号。

```python
t.group("35. Ponytail 清理：几何四档与多根顺序")
cleanup_screen = (0, 0, 100, 100)
cleanup_geom_cases = [
    ("exact", (5, 5, 20, 20), (5, 5, 20, 20), None),
    ("clip", (0, 0, 50, 50), (-5, -5, 60, 60), (0, 0, 50, 50)),
    ("clip", (0, 0, 100, 100), (-5, -5, 120, 120), None),
    ("drift", (6, 6, 20, 20), (5, 5, 20, 20), None),
    ("na", None, (5, 5, 20, 20), None),
    ("na", (5, 5, 20, 20), None, None),
]
for cleanup_grade, cleanup_reading, cleanup_layout, cleanup_parent in cleanup_geom_cases:
    cleanup_v = models.Node(cls="android.view.View", bounds=cleanup_layout)
    if cleanup_parent is not None:
        cleanup_v.parent = models.Node(cls="android.view.View", bounds=cleanup_parent)
    cleanup_u = models.U2Node(raw={}, cls=cleanup_v.cls, bounds=cleanup_reading)
    cleanup_stats = matching.align([cleanup_u], [cleanup_v], None, cleanup_screen)
    t.eq(matching.geom_of(cleanup_u, cleanup_screen), cleanup_grade, "几何分级保持既有优先级")
    t.eq(getattr(cleanup_stats, "geom_" + cleanup_grade), 1, "统计与节点分级一致")
    t.eq(sum(getattr(cleanup_stats, "geom_" + g)
             for g in ("exact", "clip", "drift", "na")), 1, "一个配对只归属一个几何档")
    t.eq(cleanup_stats.paired, 1, "统计重构不改变根配对")
cleanup_first = models.U2Node(raw={}, children=[models.U2Node(raw={}), models.U2Node(raw={})])
cleanup_last = models.U2Node(raw={}, children=[models.U2Node(raw={})])
cleanup_order = [cleanup_last, cleanup_last.children[0], cleanup_first, *cleanup_first.children]
for cleanup_walk in (matching.u2_all, lambda roots: list(parsing.iter_nodes(roots))):
    cleanup_got = cleanup_walk([cleanup_first, cleanup_last])
    t.eq([id(n) for n in cleanup_got], [id(n) for n in cleanup_order], "根逆序、孩子原序且身份不变")
    t.eq(cleanup_walk([]), [], "空树仍是空序列")
```

运行完整 selftest，预期全部通过。

- [x] **Step 2：只替换 align 的几何统计块并删除 pred_noscreen。** R1 的 pred 字典及 R0–R3 均不动。geom_of 现有条件不动，使用它决定计数字段。

```python
grade = geom_of(u, screen)
field = f"geom_{grade}"
setattr(st, field, getattr(st, field) + 1)
```

- [x] **Step 3：复用遍历并合并裁剪。** iter_nodes 只改注解，保留函数体；u2_all 替换为下面全部实现。将 _clip_ancestors 的现有实现直接命名为 clip_to_chain，删除旧转发函数；pred_visible_rect 内改调用名。保留其节点签名和绝对坐标/祖先计算。

```python
def iter_nodes(roots: Iterable[Node | U2Node]) -> Iterable[Node | U2Node]:
```

```python
def u2_all(roots: list) -> list:
    return list(iter_nodes(roots))
```

```python
def clip_to_chain(node: Node) -> Optional[tuple]:
    own = absolute_bounds(node)
    if own is None:
        return None
    r = own
    cur = node.parent
    while cur is not None:
        ab = absolute_bounds(cur)
        if ab is not None:
            r = intersect(r, ab)
        cur = cur.parent
    return r
```

```python
# pred_visible_rect 的首条计算语句。
r = clip_to_chain(node)
```

- [x] **Step 4：删除内部闲置参数并更新所有调用。** parse_dumpsys_top 的 ind 仍用于告警和树层级，不删。以下为最终签名/调用的精确形式：

```python
def parse_node_line(text: str, lineno: int,
                    anomalies: Optional[list] = None) -> Optional[Node]:
```

```python
node = parse_node_line(cur.lstrip(" ").rstrip(), i + 1, target)
```

```python
def build_unified(u2_roots: list, screen: Optional[tuple]) -> list:
```

```python
# output.build_full_json 内的调用；该函数自己的 view_roots 参数保留。
uni = build_unified(u2_roots, _scr if show_dumpsys else None)
```

```python
# selftest 原第 3 组附近的统一树调用。
uni = matching.build_unified(FX["u2_roots"], SCR)

# selftest 原第 12 组签名契约断言。
t.eq(list(inspect.signature(matching.build_unified).parameters),
     ["u2_roots", "screen"], "build_unified 只接收实际使用的树和屏幕")
```

selftest 的 post_name 调用保留原行号 1，删除第三个位置实参 6，完整调用为：

```python
post_name = parsing.parse_node_line(
    "com.android.internal.policy.DecorView{e99bd3f I.ED..... R.....ID "
    "0,0-1920,1080 aid=0}[MainSettings]", 1)
```

执行 `rg -n 'build_unified\(|parse_node_line\(|_clip_ancestors|pred_noscreen' tvuitree tests scripts`，逐个确认没有旧调用。保留现有奇数缩进/解析告警、无 dumpsys、R1 冲突、R3 非唯一、插入守恒的行为测试。

- [x] **Step 5：执行通用验证块。** 比对固定夹具 EXP_* 不改；任何计数变化先检查算法与调用，不修改期望值掩盖变化。
- [x] **Step 6：仅在用户授权提交后，检查并提交本任务文件。**

```powershell
git add -- tvuitree/domain/tree/matching.py tvuitree/domain/tree/parsing.py tvuitree/domain/tree/output.py tests/selftest_tree.py
git commit -m 'refactor(tree): 统一几何分级与节点遍历'
```

## Task 3：移除截图旧 JSON 加载器并迁移测试

**对应原建议：** 4。

**Files:** 修改 infrastructure/image.py、tests/selftest_tree.py；interfaces/json_io.py 的生产实现不改。

**Contracts:**
- Consumes: `json_io.load_full_json(path: str) -> dict`，其内部调用 validate_full_json；失败抛 OSError/ValueError。
- Produces: 删除 image.load_tree；第 7 组直接测试实际 JSON 加载入口，shot CLI 继续返回既有错误结果。

- [x] **Step 1：将 json_io 加到测试顶部 interfaces 导入。** 必须在第 7 组之前；删除第 11/12 组原有两个重复 json_io 导入，保留其余断言。

```python
from tvuitree.interfaces import (cli, connection, terminal, timing, json_io,
                                observe as observe_interface,
                                tree as tree_interface, visible as visible_interface)
```

- [x] **Step 2：迁移第 7 组读取测试，只改入口及描述。** bad_json_cases 的 6 类数据、异常断言和全部 subprocess/退出码/文件不存在断言不删除。原形状错误的 `"tree" in str(raised)` 检查保留。

```python
t.eq(json_io.load_full_json(FULL_PATH)["mode"], "full", "load_full_json 能读回全量 JSON")
```

```python
# 原 try 中只替换此调用。
json_io.load_full_json(source_path)
```

```python
t.ok(isinstance(raised, expected_error),
     f"load_full_json 的 {label} 输入抛 {expected_error.__name__}",
     f"实际 {type(raised).__name__}: {raised}")
```

运行完整 selftest，预期通过。现有稀疏 JSON、非法嵌套数据和 CLI 读取边界也必须通过；不为通过迁移而放宽 validate_full_json。

- [x] **Step 3：删除 image.py 的旧函数及专用 import json。** 不添加 infrastructure 到 interfaces 的导入，生产 shot 已经使用正确入口。

```python
# 删除此函数以及文件顶部 import json。
def load_tree(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as source:
        obj = json.load(source)
    if not isinstance(obj, dict) or not isinstance(obj.get("tree"), list):
        raise ValueError(f"{path} 里没有 tree，不像是本工具输出的控件树 JSON。")
    return obj
```

- [x] **Step 4：执行通用验证块。** `rg -n 'image\.load_tree|def load_tree' tvuitree tests scripts` 应无调用/定义；查无匹配时 rg 退出码 1 正常，不当成应用失败。不添加只检查函数不存在的测试。
- [x] **Step 5：仅在用户授权提交后提交。**

```powershell
git add -- tvuitree/infrastructure/image.py tests/selftest_tree.py
git commit -m 'refactor(image): 移除重复 JSON 加载入口'
```

## Task 4：字节截图改用 BytesIO，保留路径格式与回退

**对应原建议：** 6；依赖任务 3 清理 image.py 的旧加载器。

**Files:** 修改 infrastructure/image.py、tests/selftest_tree.py。application/screenshot.py、interfaces/mcp.py 的保存与计时逻辑不改。

**Contracts:**
- Consumes: 原画框算法、boxes 六元组、screen、width、show_details。
- Produces: 保留 `draw_boxes(png_bytes: bytes, boxes: list, out_path: str, screen: dict, width: int = 1, show_details: bool = True) -> tuple` 和 `draw_boxes_png(png_bytes: bytes, boxes: list, screen: dict, width: int = 1, show_details: bool = True) -> tuple`；新增唯一私有 `_draw_boxes(... output: str | io.BytesIO ...) -> tuple`，返回 drawn/skipped/notes。字节入口仍返回 png_bytes/drawn/skipped/notes。

- [x] **Step 1：补第 36 组实际 I/O 和回退测试。** 测试顶层增加 `import builtins`。下列组放在第 35 组后、收尾前。Pillow 使用项目已有环境，不安装依赖。

```python
t.group("36. Ponytail 清理：内存画框与文件格式")
from PIL import Image
cleanup_source = io.BytesIO()
Image.new("RGB", (20, 20), (255, 255, 255)).save(cleanup_source, format="PNG")
cleanup_png = cleanup_source.getvalue()
cleanup_boxes = [(2, 3, 15, 16, "", "reading")]
cleanup_screen_dict = {"width": 20, "height": 20}
cleanup_png_path = Path(TD) / "cleanup-render.png"
cleanup_file_stats = image.draw_boxes(cleanup_png, cleanup_boxes, str(cleanup_png_path),
                                      cleanup_screen_dict, width=1, show_details=False)
cleanup_bytes_result = image.draw_boxes_png(cleanup_png, cleanup_boxes,
                                           cleanup_screen_dict, width=1, show_details=False)
t.eq(cleanup_bytes_result[0], cleanup_png_path.read_bytes(), "字节与文件 PNG 完全一致")
t.eq(cleanup_bytes_result[1:], cleanup_file_stats, "两个入口计数和提示一致")
with Image.open(io.BytesIO(cleanup_bytes_result[0])) as cleanup_rendered:
    t.eq(cleanup_rendered.getpixel((2, 3)), image.COLOR_READING, "读数位置有红框")
    t.eq(cleanup_rendered.getpixel((1, 3)), (255, 255, 255), "外侧一像素保持干净")
cleanup_jpeg_path = Path(TD) / "cleanup-render.jpg"
image.draw_boxes(cleanup_png, [], str(cleanup_jpeg_path), cleanup_screen_dict)
with Image.open(cleanup_jpeg_path) as cleanup_jpeg:
    t.eq(cleanup_jpeg.format, "JPEG", "文件入口继续按扩展名推断格式")

cleanup_original_import = builtins.__import__
def cleanup_no_pillow(name, *args, **kwargs):
    if name == "PIL" or name.startswith("PIL."):
        raise ImportError("offline no-Pillow check")
    return cleanup_original_import(name, *args, **kwargs)

with patch("builtins.__import__", side_effect=cleanup_no_pillow):
    cleanup_fallback_file = image.draw_boxes(cleanup_png, cleanup_boxes,
                                            str(cleanup_png_path), {})
    cleanup_fallback_bytes = image.draw_boxes_png(cleanup_png, cleanup_boxes, {})
t.eq(cleanup_png_path.read_bytes(), cleanup_png, "缺 Pillow 时文件仍保存原图")
t.eq(cleanup_fallback_bytes[0], cleanup_png, "缺 Pillow 时字节入口仍返回原图")
t.eq(cleanup_fallback_bytes[1:], cleanup_fallback_file, "缺 Pillow 两个入口的计数和提示相同")
t.eq(cleanup_fallback_file,
     (0, 1, ["未安装 Pillow，只保存了原始截图（画框需 pip install pillow）"]),
     "缺 Pillow 保留既有提示与跳过计数")

cleanup_bad_png_error = None
try:
    image.draw_boxes_png(b"invalid PNG", [], cleanup_screen_dict)
except Exception as cleanup_error:
    cleanup_bad_png_error = cleanup_error
t.ok(isinstance(cleanup_bad_png_error, OSError), "非法 PNG 仍抛图像读取错误")

cleanup_io_error = None
try:
    with patch("tempfile.TemporaryDirectory", side_effect=AssertionError("disk staging forbidden")):
        cleanup_memory_result = image.draw_boxes_png(cleanup_png, cleanup_boxes,
                                                     cleanup_screen_dict, show_details=False)
except Exception as cleanup_error:
    cleanup_io_error = cleanup_error
t.eq(cleanup_io_error, None, "字节画框不需要创建临时目录")
if cleanup_io_error is None:
    t.eq(cleanup_memory_result, cleanup_bytes_result, "移除临时目录后结果保持一致")
```

运行完整 selftest，预期当前代码仅本组“字节画框不需要创建临时目录”失败。若出现其他失败，先排查夹具/真实契约。这个 RED 检查中转步骤，不要求旧行为等价断言先失败。

- [x] **Step 2：将现有 draw_boxes 主体改名为 _draw_boxes。** 只改函数签名、缺 Pillow 输出载体分支、最后保存语句；中间所有像素计算及提示原样保留。不要复制第二套绘图算法。

```python
def _draw_boxes(png_bytes: bytes, boxes: list, output: str | io.BytesIO,
                screen: dict, width: int = 1, show_details: bool = True) -> tuple:
```

导入 Pillow 的 try 保留；替换 except ImportError 的主体为：

```python
except ImportError:
    if isinstance(output, io.BytesIO):
        output.write(png_bytes)
    else:
        with open(output, "wb") as f:
            f.write(png_bytes)
    return 0, len(boxes), ["未安装 Pillow，只保存了原始截图（画框需 pip install pillow）"]
```

替换原 `img.save(out_path)`，保持紧随其后的 `return drawn, skipped, notes`：

```python
if isinstance(output, io.BytesIO):
    img.save(output, format="PNG")
else:
    img.save(output)
```

- [x] **Step 3：增加保留原签名的文件包装，替换字节包装。** 两个包装均调用真实共用核心；不扩大 draw_boxes 公开参数类型。删除已无消费者的 os/tempfile 导入，保留 io。BytesIO 上下文负责释放，不增加更通用的输出协议。

```python
def draw_boxes(png_bytes: bytes, boxes: list, out_path: str,
               screen: dict, width: int = 1, show_details: bool = True) -> tuple:
    """按文件扩展名保存画框结果，返回画出数、未画出数和提示。"""
    return _draw_boxes(png_bytes, boxes, out_path, screen, width, show_details)


def draw_boxes_png(png_bytes: bytes, boxes: list, screen: dict,
                   width: int = 1, show_details: bool = True) -> tuple:
    """用同一套画框逻辑渲染，返回 PNG 字节，不留下成品文件。"""
    with io.BytesIO() as output:
        drawn, skipped, notes = _draw_boxes(
            png_bytes, boxes, output, screen, width, show_details)
        return output.getvalue(), drawn, skipped, notes
```

- [x] **Step 4：执行通用验证块，预期新第 36 组 GREEN。** 原第 7 组及其他像素回归继续验证宽度、边沿、虚线与告警；原第 8 组 MCP 验证图像字节、落盘、timing stages。不得删除 MCP 保存逻辑以追求“无文件”。
- [x] **Step 5：仅在用户授权提交后提交。**

```powershell
git add -- tvuitree/infrastructure/image.py tests/selftest_tree.py
git commit -m 'refactor(image): 使用内存缓冲渲染 PNG'
```

## 最终验收与交付

- [x] 审阅整个 diff：7 条原建议分别落入任务 1/2/3/4，原图像算法、配对与剪枝判据没有额外变更。依赖和配置无改动；plan 的静态检查与全自检已在任务 4 执行，不无故再跑一次。
- [x] 最后运行 help/prune-list 及 diff 检查，确认 CLI 文案和剪枝表仍可读取。

```powershell
.\.venv\Scripts\python.exe main.py --help
.\.venv\Scripts\python.exe main.py tree --prune-list
git diff --check
git status --short
```

- [x] 按实际结果写 `docs/reports/2026-10-05-ponytail-cleanup-delivery.md`，包含 7 项去向、实际检查和退出码、新增自检条数、是否提交、真实设备验证状态。docs/README.md 更新本计划状态并链接交付报告。未做 TV/ADB 验证须明示，离线通过不能写成真机通过；无需为了纯内部重构触发设备输入。
- [x] 检查报告不包含设备地址或敏感输出，文档变更执行 git diff --check。只有用户授权提交时才单独提交交付文档：`docs(cleanup): 记录 Ponytail 清理验证结果`。交付时提供实际 diff 和检查结论，等待另行推送/合并授权。

## 计划自审与执行建议

7 项建议完整映射到 4 项任务，5 类 Review Focus 都有负责测试；没有新增依赖、旧内部参数兼容层或未使用抽象。Python 类型名来自当前模块已有导入，BytesIO 来自已存在的 io；第 7 组 json_io 的导入次序已明确。新增保护断言在当前实现可通过，唯一预期 RED 是临时目录依赖。

计划编写时已用临时执行器直接读取三个完整测试块：52 条断言中 51 条通过，仅“字节画框不需要创建临时目录”按预期失败；执行器验证唯一失败后退出 0。这个结果只证明计划测试能运行且 RED 原因正确，不是未来实现的 GREEN。执行时仍须把代码放入 selftest，运行完整脚本以验证共享状态、组顺序及所有旧断言。

建议选择 **Native：在本会话顺序执行**，使用 superpowers:executing-plans。任务规模小且共享 matching/image/selftest，顺序执行便于保留同一套行为基线。也可由用户选择 Subagent-driven，采用逐任务实现与评审。须先审阅本计划并选定方式；本文不表示已获实施、提交或推送授权。

## 执行记录（2026-10-05）

用户选择 executing-plans 本会话顺序执行，并授权创建隔离 worktree。四项实施已完成；已执行步骤勾选，条件提交步骤因未获提交授权保留未勾选。任务 1/2/3/4 完成自检分别为 1100/1128/1128/1140 条，编译、pyflakes 和差异检查均通过；任务 4 的临时目录要求经过唯一失败的 RED 到完整通过的 GREEN。

执行位置为 Codex 管理的 ponytail-cleanup worktree；原主目录生产代码没有改动。本次实施没有提交、推送或合并。执行裁定、终审和实质限制见[交付报告](../../reports/2026-10-05-ponytail-cleanup-delivery.md)。开头和 Global Constraints 中的“本次只交付计划”记载计划编写时的范围，后续实施授权及状态以本节为准。

后续授权与提交：用户于 2026-10-05 要求推送并合并到 main，条件提交步骤已获得授权并完成四个阶段代码提交：d0801db、bce9f05、1799615、04e1e2c。文档随本次归档提交，来源分支 codex/ponytail-cleanup；实际发布与 main 合并结果以远端记录为准。上述未提交状态属于实施/终审时的历史记录。
