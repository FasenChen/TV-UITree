# Ponytail 全项目复杂度审查

日期：2026-10-05。审查版本：`a220fc2d8a2636669333e344d146fb33d25ce1a0`。

采用用户指定的 `ponytail:ponytail-audit`，范围为过度设计、重复实现、闲置功能和可替换的中间步骤。开始审查时工作区干净。本轮仅新增审查报告和索引，不修改生产代码、测试、配置或依赖，不提交或推送。

## 结论

整体实现没有需要推倒重建的复杂度问题。四层职责、full JSON 作为统一数据来源、CLI/MCP 共享应用服务、R0–R3 唯一性判据和剪枝归属规则均服务于已有需求。可简化部分集中在闲置代码、重复几何判断和少量不必要的处理步骤。

下列编号可用于后续指定整改范围。前五项按预计代码减量排列；第六项主要减少中间文件与清理步骤，第七项主要减少接口误导。减量是生产代码的粗估，约 60 行，未实施，也不包含测试迁移和本报告增加的行数。

1. `delete:` 删除仓内无消费者的 `A11Y_ATTRS`、`Node.label`、`U2Node.bounds_str` 和 `screenshot.walk`。无需替代；保留仍被输出层使用的 `Node.bounds_str`、两种节点的 `short_cls` 及截图包装类的 `label()`。位置：`tvuitree/domain/tree/models.py:12,155,210`，`tvuitree/domain/screenshot.py:6`。
2. `reuse:` 删除 `align()` 内另一份 exact/clip/drift/na 判断及仅为该判断建立的 `pred_noscreen`。改为调用现有 `geom_of(u, screen)`，再增加对应统计字段，保持统计和节点输出使用同一规则。位置：`tvuitree/domain/tree/matching.py:187,248,349`。
3. `yagni:` 删除 `node_summary(include_children=True)` 的闲置分支和页面遍历的 `included_paths` 集合。现有调用均不启用子树嵌套摘要；焦点子节点已由 `_focus_context()` 处理，`_walk()` 的索引路径天然唯一。位置：`tvuitree/domain/observation.py:37,79,188`。
4. `reuse:` 删除只有测试调用的 `image.load_tree()` 及其专用 `json` 导入。将相关读取断言迁到实际使用的 `json_io.load_full_json()`，保留非法文件/结构及 CLI 退出码覆盖；不增加从 infrastructure 到 interfaces 的反向导入。位置：`tvuitree/infrastructure/image.py:8,29`，`tests/selftest_tree.py:988,1005`。
5. `reuse:` 将 `u2_all()` 的重复栈遍历改成 `list(iter_nodes(roots))`；将 `_clip_ancestors()` 的实现直接命名为 `clip_to_chain()`，并让 `pred_visible_rect()` 调用它，去掉仅转发的包装函数。位置：`tvuitree/domain/tree/matching.py:42,56,109`，`tvuitree/domain/tree/parsing.py:149`。
6. `stdlib:` 删除 `draw_boxes_png()` 的临时目录、写文件、重新读文件步骤。让现有画框函数支持 `io.BytesIO` 输出并显式指定 PNG 格式，继续共用同一绘图逻辑，保留缺少 Pillow 时原图返回的既有行为；最终截图保存仍由 MCP 的保存步骤承担。位置：`tvuitree/infrastructure/image.py:88,181`。
7. `shrink:` 删除三个函数体未读取的参数：`build_unified.view_roots`、`parse_node_line.indent`、`_summary.out_path`。同步更新调用点及现有签名断言，分别保留实际使用的 `screen`、行号和解析告警。位置：`tvuitree/domain/tree/matching.py:371`，`tvuitree/domain/tree/parsing.py:16`，`tvuitree/interfaces/tree.py:33`。

## 证据和整改边界

| 编号 | 当前证据 | 后续整改必须保留的行为 |
|---|---|---|
| 1 | 搜索生产代码、脚本、测试和仓内文档，确认常量只有定义；`Node.label` 和 `U2Node.bounds_str` 无消费者；截图 `walk` 只有自身递归。检查 `getattr`、动态导入和字符串引用，未发现这些符号的动态消费者 | 不误删 `JsonNode.label()` 或 `Node.bounds_str`；未核查仓外对内部模块的直接导入 |
| 2 | `align()` 的 248–259 行与 `geom_of()` 的 358–368 行表达相同分级条件。后者已被 `build_unified()` 用于节点 `geom_check` | exact/clip/drift/na、配对总数、JSON 字段保持相同；不改变 R1 候选图或 R3 插入判断 |
| 3 | 所有 `node_summary()` 调用使用默认值或显式 False；没有 True 调用。`_walk()` 通过父路径和子节点索引生成路径，即使同一字典在两处出现，路径仍唯一 | 页面摘要顺序、上限、截断标记和焦点上下文保持相同 |
| 4 | `run_shot()` 已使用 `load_full_json()`；旧加载器的仅存执行调用是第 7 组自检。新入口还调用共享 `validate_full_json()` | 不以删除旧函数为由删掉错误路径断言；保留库层 OSError/ValueError 和 shot 退出码 1 |
| 5 | 两种遍历均从 `list(roots)` 栈开始、pop 节点并扩展 reversed(children)。本轮用含两个根的 U2Node 树对照，结果对象与顺序相同 | 更新遍历函数注解以接受两类节点；保留现有多根遍历顺序，不顺带调整算法 |
| 6 | 现有绘图已使用 Pillow 和 io，字节输出包装却需要文件系统中转。本轮验证已安装 Pillow 能向 BytesIO 保存 PNG | 只替换输出载体；线宽、逐像素几何、标签告警、drawn/skipped/notes 和无 Pillow 路径保持相同；本轮未实现或验证完整替代函数 |
| 7 | AST 检查三个参数均不在函数体的读取节点中；全部调用点已搜索。自检第 12 组对 build_unified 的旧签名有显式断言 | 跟随实际契约修改签名断言；不删除有效的调用验证，也不为旧内部签名新增兼容包装 |

## 未建议删除的部分

- `uiautomator2`、Pillow、MCP 均有实际运行职责；pyflakes 是项目已有静态检查工具。没有确认可删依赖。
- 输入边界校验、原子替换与失败清理、单次 ADB 恢复、MCP 耗时记录均有真实契约或回归覆盖，不能作为通用“样板代码”删除。
- `JsonNode` 的父链用于派生坐标溢出检查，领域模型用于解析和匹配，不因只有一种实现就改成无约束字典。
- 观察、可见控件和焦点标签的遍历过滤规则不同，不为了合并函数而抹平语义差异。
- 现有长自检保留真实设备格式、像素断言和接口错误路径，不因长度换框架、删除断言或重写夹具。
- 历史计划及交付记录是证据归档，不作为可删“重复文档”。

## 验证

| 检查 | 本轮结果 |
|---|---|
| 项目 `.venv` 执行 `tests/selftest_tree.py` | 退出码 0，1087 条断言全部成立 |
| `.venv` 执行 pyflakes，包含 main.py、tvuitree、tests、scripts | 退出码 0，无诊断 |
| 39 个 Python 文件的 AST 解析与内存 compile | 全部通过；没有将此步骤冒称为 py_compile 命令 |
| 重复遍历的多根 U2Node 对照 | 对象身份及遍历顺序一致 |
| 观察路径唯一性对照 | 同一字典在两处出现时，索引路径仍唯一 |
| 当前 Pillow 的 BytesIO PNG 输出 | 支持，输出含 PNG 签名 |
| `git diff --check` | 归档前通过；归档后再次检查 |

本轮使用的环境版本：uiautomator2 3.7.0、Pillow 12.3.0、MCP 1.30.0、pyflakes 4.0.0。只核对本地环境，不评价新版依赖兼容性。

自检原始输出位于本地忽略目录 `_temp/ponytail-audit-20261005/selftest.log`，不随仓库交付。未连接 TV、发送按键、修改设备配置或执行真实 stdio/Inspector 验证。以上通过结果属于当前代码基线，不证明尚未实施的建议已经通过验证。正确性、安全和性能缺陷不属于此插件本轮审查范围。

net: -60 lines, -0 deps possible.
