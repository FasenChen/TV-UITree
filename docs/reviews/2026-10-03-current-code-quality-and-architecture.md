# 当前代码质量与架构评审

日期：2026-10-03。审查版本：`c5eb108494b8a221eba0cf5074bd162c6676cf28`。

## 结论

四层架构适合目前的 Android TV 调试工具规模，主线清楚，抽象程度基本合适，建议继续沿用。共享 full JSON、纯 domain 规则及 CLI/MCP 复用应用服务，已经构成有用的维护基础。

当前质量短板在观测语义与外部边界：仍有可以复现的任意配对、状态丢失、坐标告警错误和失败被当作成功的情况。作为本地调试工具已经具备可运行、可回归的基础；作为自动化决策的数据来源，应先关闭这些问题。没有必要为了改善质量整体更换框架或新增更多层。

本轮审查范围是当前整体实现，包含上一轮补修未涉及的匹配、状态投影、截图告警及输入路径。前次补修的通过记录只证明其当时的范围，不代表全仓所有边界均已正确。

本轮确认 1 项 P1、8 项 P2，未确认 P0/Critical。P2 的影响和优先级不同，详见各项触发条件。维护建议单列，不把代码长度、缺少类型或依赖锁定本身视为运行缺陷。

## 范围与验证

- 独立新上下文审查者按 requesting-code-review 流程审查四层核心、接口、测试及工程文档；主代理复核关键案例。
- 当前 37 个生产 Python 文件约 3900 行；检查范围含 main.py、tvuitree、tests。domain 的 AST 导入检查未发现 application/infrastructure/interfaces/Pillow/uiautomator2/MCP/os/pathlib/subprocess 依赖。
- 项目 `.venv` 重新执行 py_compile、pyflakes、selftest、diff-check，均退出码 0；864 条断言通过。已有用例未覆盖下述部分失败方向，因此通过数量不能代替边界正确性证明。
- 复现使用纯函数、内存 JSON/XML 或 subprocess/设备替身，不连接 TV、不发按键、不改配置。本轮未进行真实 stdio、真机或真实 POSIX 文件系统验证。
- 本地实际安装版本：uiautomator2 3.7.0、Pillow 12.3.0、mcp 1.30.0、pyflakes 4.0.0。这是当前环境事实，不代表 requirements 已固定这些版本或新版兼容性已验证。
- 本轮只新增本报告并更新文档索引，没有修复生产代码、提交或推送。

## 架构优点

| 优点 | 实现证据与价值 |
|---|---|
| 数据流程有单一入口 | `application/observation.py:10–70` 将实时采集与离线投影集中管理，CLI/MCP 共用，减少两套逻辑漂移 |
| domain 保持纯计算 | 解析、配对、剪枝、可见摘要与截图坐标选择不需要设备或协议；有利于脱离 TV 的确定性验证 |
| 读数和派生信息有区分 | `domain/tree/output.py:38–113`、`matching.py` 保留 a11y 与 dumpsys 来源、几何等级和漂移说明，方向符合观测工具需求 |
| 部分关键规则有明确权威来源 | R3 唯一保序映射、merge_children 插入判据、剪枝 OWNER_PRIORITY 集中实现，减少调用方重复判断 |
| 测试覆盖有实际价值 | 第 8 段覆盖共享快照的 CLI/MCP 输出与图片；后续回归覆盖真实 _popen 恢复链及原子写失败，超出单纯检查源码形式 |
| 规模可控 | 生产文件最大约 397 行，没有必要因测试脚本较长而重构整个产品或引入重型应用框架 |

## 产品缺陷

### Q1 — P1：R1 几何配对缺少逆向唯一性

**位置：** `tvuitree/domain/tree/matching.py:207–213`。

代码声明“双向唯一”，实际只检查一个 a11y 节点的可用 View 候选数量，再立即占用 View。两个相同类、资源 ID、矩形的 a11y 节点竞争一个 View 时，先遍历者被标为 `geom`，另一节点失配。

主代理使用正常父子结构复核：一个已 R0 配对的根，其 a11y 子节点 A/B 都为 Button、资源 ID `pkg:id/key`、矩形 `(10,10,40,40)`，View 侧只有一个对应子节点。顺序 `[A,B]` 时 A 配对，顺序 `[B,A]` 时 B 配对，均无序列歧义说明。

**影响：** 同样的布局证据绑定给不同控件，后续派生字段、R3 补入及几何说明可能建立在任意关联上。该问题影响工具核心数据可信度。

**最小建议：** 在绑定前计算两个方向的候选唯一性，不因循环中的占用造成伪唯一。补充“两 a11y 争一 View”及顺序交换用例；明确允许后续更强证据处理歧义，而非几何路径抢占。

### Q2 — P2：摘要丢失禁用状态

**位置：** `tvuitree/domain/observation.py:71–73`；消费者 `tvuitree/domain/visible.py:103–109`。

共享 node_summary 仅保留 `enabled=True`，visible 又只打算保留 `enabled=False`，故该消费者的禁用分支实际无法收到值。

**复现：** a11y Button 含 `enabled=False`、`clickable=True`、文本及有效屏幕 bounds；observe/visible 摘要仍有 `actions=["click"]`，没有 enabled 字段。

**影响：** 下游知道控件的 clickable 读数，却无法知道其当前禁用状态。clickable 不应被解释为 enabled 的替代证据。

**最小建议：** 共享摘要保留显式布尔状态，具体投影再省略默认值；验证同一控件启用/禁用时 observe、visible、CLI/MCP 的一致性。

### Q3 — P2：截图溢出检查混用坐标系

**位置：** `tvuitree/domain/screenshot.py:64–65`。

子节点 bounds_local 在父坐标系，父节点 bounds_local 在祖父坐标系，直接比较四个边界无效。

**复现：** 父矩形 `[100,100,300,300]`，尺寸为 200×200。子 `[0,0,50,50]` 完全在父内却报溢出；子 `[100,100,250,250]` 超出父局部范围却无告警。

**影响：** 对派生截图坐标的可信度产生误报和漏报。本项不意味着绘制的像素偏移算法已错误；问题位于祖先链诊断。

**最小建议：** 在同一坐标系比较子矩形与父局部范围 `[0,0,width,height]`，覆盖父容器不在原点的内含及溢出案例。

### Q4 — P2：XML 解析失败被转换为成功空树

**位置：** `tvuitree/domain/tree/parsing.py:162–165`。

ET.ParseError 被吞掉并返回空列表。上游 fetch_u2 只检查 `<hierarchy` 子串，不保证 XML 可解析。

**复现：** snapshot 替身返回 `"<hierarchy><node"`，collect_full_json(use_dumpsys=False) 返回 `tree=[]`、`_parse_anomalies=[]`；后续 observe 返回 `full_tree_available=True`。

**影响：** 损坏的主数据源与合法空 hierarchy 无法区分，下游会看到正常“没有焦点/节点”。本轮证明失败传播路径，未声称已在真机见到该 XML。

**最小建议：** 保留解析失败，在现有应用/接口边界转换为采集错误；合法空 XML 行为另外明确，勿用一律拒绝空树取代区分。

### Q5 — P2：input/shot 的外部失败异常外漏

**位置：** `tvuitree/interfaces/input.py:33`、`tvuitree/interfaces/shot.py:53`。

**复现：** 真实 cli.main 的 input 分支在替身设备 shell_raw 抛 AdbError 时异常外漏；shot 读到无效图片后 render 外漏 UnidentifiedImageError。输出目录写失败也缺少该运行边界的受控处理。

**影响：** 用户收到 traceback，无法稳定获得中文失败说明。即便进程最终也以 1 退出，仍不能视为已完成接口错误处理。

**最小建议：** 在现有命令边界处理实际 ADB、图片和文件异常，保持 shot/input 自身失败返回 1、连接失败返回 2；不引入泛化恢复框架。

### Q6 — P2：full JSON 入口只检查 tree 是列表

**位置：** `tvuitree/interfaces/json_io.py:73–78`，以及各离线投影调用边界。

**复现：** 通过 builtins.open 的 StringIO 替身保留真实 load_full_json：`{"tree":[null],"screen":{"width":400,"height":300}}` 令 observe、visible、tree slim 全部外漏 AttributeError；`screen=["invalid"]` 令 visible/tree 外漏异常，observe 则原样接受。

**影响：** 有效 JSON 语法、无效业务结构没有进入文件错误退出码 2 通道，各消费者的结构要求也不一致。

**最小建议：** 在持久化入口校验实际消费的 node/children/screen/bounds 等形状，并以明确 ValueError 报告；字段允许缺失的情况按已有 full 格式定义，不强制补出并不存在的业务事实。不能只增加宽泛 except 掩盖模型契约问题。

### Q7 — P2：初始连接接受 offline/unauthorized 成员

**位置：** `tvuitree/infrastructure/adb.py:156–165`。

指定 serial 时仅判断其是否在列表中；唯一目标自动选择也未检查状态。devices 替身返回该目标为 offline，connect() 仍返回 True。

**影响：** 连接不可用进入采集链，错误被推迟到后续命令，与恢复路径的 device 状态判据不一致。

**最小建议：** 复用按目标查询状态的逻辑，只将 device 视为可用；no_connect 控制是否发 connect 命令，不应替代状态判断。上一轮补修明确暂不改变此既有语义，本轮整体审查重新提出，未把它当成最新提交的回归。

### Q8 — P2：按键名缺少字符边界校验

**位置：** `tvuitree/application/input.py:20–35`。

**复现：** send_key(fake,"DOWN; :") 传给 shell_raw 的实际字符串为 `input keyevent KEYCODE_DOWN; :`，替身 rc=0 时函数返回成功。upper() 保留 shell 标点。

**影响：** 输入被作为 shell 语法组成部分，而非单个键码。当前入口仅本地 CLI，调用者已有 ADB 权限，没有 MCP 按键工具；未证明远程攻击、提权或真实设备上的破坏行为，故作为输入校验问题处理。

**最小建议：** 仅接受数字或明确的键码标识符/别名，拒绝元字符和多余参数，再交给当前 ADB 执行边界。错误键名应在设备操作前报告。

### Q9 — P2：无文字的可操作控件被可见投影丢弃

**位置：** `tvuitree/domain/visible.py:97–98,117`。

**复现：** Switch 含 resource_id、有效屏幕 bounds、checkable=True、checked=False、enabled=True、visible_to_user=True，但无 text/content-desc；select_visible 的 page.nodes 为空。

**影响：** 有坐标、操作和状态读数的真实控件未进入“可见控件摘要”，下游不能定位或读取它。此案例与无信息布局容器不同。

**最小建议：** 保留有实际操作/状态证据的控件，资源 ID、类名可作为已有标识；不创造文本标签，也不因只有 focusable 就推断可见或焦点。

## 维护建议（非运行故障）

1. **依赖可重现性。** requirements.txt 的 uiautomator2、Pillow、pyflakes 无版本范围，MCP 也未固定本轮版本；仓内未见锁文件。可先记录验证版本及约束，不必更换依赖管理框架。
2. **集中数据契约。** full JSON、screen、snapshot 和节点在消费者间以宽泛 dict 传递，Q2/Q6 已显示契约漂移。按稳定边界增量补类型和校验，优先复用现有 dataclass/标准库类型；不把每个字典都包装成独立模型。
3. **测试按行为组织。** 2673 行自检包含许多真实格式与集成断言，价值应保留。后续可逐步将夹具、纯规则、接口错误的实现分组，保持现有顺序脚本入口；优先新增歧义、非原点坐标、布尔 false、损坏输入这些遗漏方向，无须为了行数迁移 pytest。
4. **持续验证入口。** 仓内未见跟踪的 .github 工作流。若需要多人维护，可把既有项目检查做成受控的持续验证，并让离线测试不依赖个人设备地址；不是本轮已实现功能。
5. **小范围一致性。** README:233 写六个工具、264 仍写四个；image.load_tree 与 json_io.load_full_json 有重复基础加载规则。优先级低于产品缺陷，后续局部整理即可。

## 建议处理顺序

先处理 Q1、Q2、Q3、Q4，确保观测证据不被任意关联、丢失或伪装为空；接着处理 Q5–Q9 的接口与可见投影边界；最后做依赖约束、类型契约和测试组织。修复每项前写可达行为回归，不用源码词语数量或测试断言数量作为正确性判据。

## 未判定范围

- 真机 uiautomator2 的服务生命周期、实际连接/dump 时限、Android 版本与多窗口覆盖：本轮未连接设备。
- 截图期间页面变化及真实坐标：本轮只验证纯几何，不能代替截图/真机验收。
- 当前 MCP 宿主的并发和长期运行：本轮未重新做协议压力检查。前一轮真实 stdio 错误路径结果见补修交付报告，其范围不覆盖这些行为。
- 新版依赖、Node/Inspector 的当前兼容性：本轮未联网，也未运行 Inspector。
- 本轮提出的是已读代码和可复现路径的结论，未声称数学证明、全平台验证或所有潜在问题已枚举。

本地静态检查日志及规模统计位于 `_temp/plan-evidence/remediation-follow-up-20261003/architecture-review-*`、`architecture-metrics.json`，不随仓库提供；本报告中的触发形状、结果与限制可独立阅读。
