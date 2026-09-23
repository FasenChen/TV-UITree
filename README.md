# tv-uitree

**一句话**：`tv_tree.py` 从 Android TV 抓控件树，输出**全量 JSON** 和一份由它剪枝得到的**精简 JSON**（剪什么由参数控制）；按键、截图画框各自是独立脚本，**与取树无关**。

```
tv_tree.py        取控件树 → JSON       ← 本项目的核心，唯一的取数入口
tv_input.py       发遥控器按键          ← 手工测试辅助，不参与取树
tv_shot.py        截图 + 在图上画框     ← 验证辅助，不参与取树
selftest_tree.py  离线自检              ← 不连设备，锁住配对与剪枝行为
```

三者互不调用，只用 JSON 文件交接。取树**不需要**按任何键，也**不需要**截图。

---

## 1. 快速开始

准备（只需一次）：

```bash
python -m pip install uiautomator2          # tv_tree.py 的唯一硬依赖
python -m pip install pillow                # 可选，只有 tv_shot.py 画框要用
adb connect 192.168.31.102:5555             # 电视需已打开 ADB 调试
```

取树：

```bash
python tv_tree.py --out full.json                    # 全量 JSON（默认模式）
python tv_tree.py --mode slim --out slim.json        # 精简 JSON
python tv_tree.py --mode slim --keep empty --out s.json    # 精简 + 把空节点加回来
python tv_tree.py --prune-list                       # 看剪枝开关表（不连设备）
python tv_tree.py --from-json full.json --mode slim --out s.json   # 离线重剪，不连设备
```

辅助脚本：

```bash
python tv_input.py DOWN,RIGHT,OK --delay 0.6         # 发按键
python tv_input.py --list                            # 看可用按键短名
python tv_shot.py --json full.json --out shot.png    # 截图并画焦点框
python tv_shot.py --json full.json --source both --out shot_both.png   # 两种坐标都画（红实线 / 蓝虚线）
python tv_shot.py --json full.json --draw all --width 2 --out shot_all.png  # 画所有矩形，线加粗
python tv_shot.py --json full.json --image old.png --out o.png         # 用已有截图，不连设备
```

验收：

```bash
python selftest_tree.py                              # 离线自检，通过 → 退出码 0
```

本工作区已有一个装好依赖的虚拟环境，不想动系统环境可以直接用它的解释器：

```
C:\Users\LazyAngel\.workbuddy\binaries\python\envs\tvuitree\Scripts\python.exe
```

本机实测环境（`ADB` 默认为 `192.168.31.102:5555`）：MOKA R6G / Android 14 / SDK 34 / 1920×1080 @320dpi / userdebug；设备属性可用 `adb shell getprop` 复查。

---

## 2. 三个脚本的分工

| 脚本 | 负责 | **不**负责 |
|---|---|---|
| `tv_tree.py` | 抓 a11y 层次 + `dumpsys activity top`，按 R0–R3 合并成一棵树，输出 JSON | 按键、截图、看画面 |
| `tv_input.py` | 往设备发 `input keyevent` | 取树、判断焦点在哪 |
| `tv_shot.py` | `screencap` 截图，读**已有**的树 JSON 画框 | 取树（它只读 JSON） |

设备接入参数（`--host/--port/--serial/--address/--adb/--no-connect/--no-color/--quiet`）三个脚本共用一份定义（`tv_adb.py`），不存在两套。

**退出码**：`0` 成功 / `2` 用法错误（参数不合法、文件读不了）/ `3` 设备或取数失败。

### 2.1 `tv_shot.py` 画框约定：框 = 读数，偏差**原样暴露**

`tv_shot.py` 是**验证工具**，它的全部价值在于把「控件树算出来的位置」与「画面上的实际位置」的差异摆在眼前。任何让框「看起来更贴合焦点」的修饰，都是在擦掉要验证的东西。所以：

| 规矩 | 具体做法 |
|---|---|
| **框的几何 = 读数，逐像素对齐** | 不加偏移、不做容差。默认 `--width 1`，线所占像素**就是**读数所指的那一行/列；框线外再一格必须是干净底色 |
| **唯一允许的变换是分辨率换算** | 控件树坐标基于 `wm size`，截图是物理像素。`x` / `y` **各算一个**系数并打印出来；两轴不等（宽高比不一致）时点明「这已不是相似变换，画出的框与读数的对应关系**不成立**」，不许按单轴凑 |
| **两个来源只靠样式区分** | 读数 = 红实线，派生 = 蓝虚线。**绝不**靠几何偏移区分 —— 那会把真实差值伪装成样式差异 |
| **画不出来的照实说，且分得清性质** | 三种情况分开报：**零面积**（读数自身没有面积）／**真越界**（读数超出画面，逐条报原读数与裁后坐标）／**压屏幕外沿**（只给总数）。**「画不出来」本身是信息，不是要抹平的噪声** |
| **说明文字不参与坐标** | 标签画在框上方，只为可读；判定「框落在哪」只看框线 |
| **判定成因只用读数的算术** | 中心是否严格重合 → 比 `l+r`、`t+b` 的整数；是否等比 → 交叉相乘 `dd_w*da_h == dd_h*da_w` 的整数等式。**不设**「0.9~1.2 就算缩放」这类经验区间：真机两面板页那 1008 像素的滚动偏移**同样同心**，区间一宽就会被误报成「缩放动效」，恰好掩盖要查的问题 |

一句话：**读数不修正、偏差不补偿、画不出来的不假装。** 框画得「不完美」是结果，不是缺陷 —— 差异本身就是这个工具要交付的东西。

> **a11y 的 `bounds` 是半开区间**（Android 约定）：`[0,0][1920,1080]` 表示覆盖整屏，右/下边界**不含**在矩形内，末像素是 `1919`/`1079`。所以全屏框画出来时右边和下边比读数少 1 像素 —— 这是约定，不是偏差。`tv_shot.py` 会把它汇总成一条提示，不与「读数真的越出画面」混在一起。

加粗用 `--width N`：线带以读数为**中线对称**展开，中线永不离开读数。**不要**用加宽去「贴近」焦点。

这条约定在 `selftest_tree.py` 里有像素级断言（框上四边必须是画的颜色、再往外一格必须干净），并在源码里静态挡住三种复发写法：`abs(sx-1.0)>0.01` 的换算阈值、`0.9<=kx<=1.2` 的经验区间、把框向外膨胀的 `cl-w`。

---

## 3. 输出怎么读

### 3.1 顶层字段

| 字段 | 含义 |
|---|---|
| `mode` | `full` / `slim` |
| `captured_at` | 采集时刻。`tv_shot.py` 用它判断「截图」与「树」是不是同一时刻 |
| `primary_source` / `supplement_source` | 主源固定是 `uiautomator2 (a11y)`；补充源是 `dumpsys activity top`，`--no-dumpsys` 时为 `null` |
| `device` / `screen` / `window` / `segment` | 机型属性、屏幕尺寸与密度、前台窗口、选中的 Activity 段包名 |
| `source_consistency` | 抓了两次 dumpsys，两者**我们消费的那部分**是否一致。`drift: true` = 画面在动，配对可信度下降 |
| `coordinate_note` | 四种坐标各自是什么口径（必读） |
| `align_rules` / `align_stats` | 配对规则原文 + 这次各规则命中多少、几何校验各档多少 |
| `tree` | 一体式树（见 §3.2） |
| `dumpsys_only` | 「位次无法唯一确定」的 dumpsys 节点，单独列出，不塞进树里 |
| `focus` | a11y 报告的焦点节点：类名、res-id、屏幕坐标、文字、祖先路径 |

### 3.2 节点字段：两种来源，坐标口径不同

| | `source: "a11y"` | `source: "dumpsys"` |
|---|---|---|
| 怎么来的 | 主源直接读到的节点 | a11y 没收录、位次由 R3 唯一确定后补入的节点 |
| 坐标 | `bounds_screen`——**屏幕上真实可见的矩形**，读数 | `bounds_local`——**相对父容器**的布局矩形，读数 |
| 派生坐标 | `dumpsys.bounds_abs_unclipped`、`dumpsys.pred_visible_rect` | `bounds_abs_unclipped`、`pred_visible_rect` |
| 文字 | `text` / `content_desc` / `hint` | **没有**（ViewDebug 不调 `getText()`，本工具也不跨源回填） |
| 配对信息 | `geom_check`、`dumpsys.match_reason` | `position_by`、`why_not_in_a11y` |

两条硬规矩：

1. **读数与派生值分开**。带 `_abs_` / `_unclipped` / `pred_` 的都是**算出来的**，不是读出来的；工具不会把派生值冒充读数。
2. **dumpsys 侧的 res-id 原样输出**（`app:id/x`），归一化后的值另放 `resource_id_normalized`，不覆盖原值。

---

## 4. 精简版：剪枝开关与 `--keep`

精简 JSON 是**在全量 JSON 上剪枝**得到的同一棵树 —— 不是第二条采集路径。所以两种模式表达的是同一批读数，差别只在「留多少」。

8 个开关，默认**全部执行剪枝**：

| 开关 | 作用域 | 默认剪掉什么 |
|---|---|---|
| `gone` | 树 | `visibility=GONE` 的节点（只可能在 dumpsys 侧，a11y 根本不收录） |
| `zeroarea` | 树 | 自身布局矩形为零面积的节点 |
| `offscreen` | 树 | 可见区域与屏幕无交集的节点 |
| `empty` | 树 | 自身与整棵子树都没有任何信息的节点（无文字/描述/提示、无 res-id、不可点击/聚焦/长按/滚动/勾选） |
| `derived` | 字段 | 派生量：`bounds_abs_unclipped`、`pred_visible_rect` |
| `defaults` | 字段 | 取默认值的布尔字段（`false` 一律省略，`enabled`/`visible`/`visible_to_user` 的 `true` 省略） |
| `meta` | 字段 | 对齐元数据：`geom_check`/`match_reason`/`why_not_in_a11y`/`position_by`/`note`，以及顶层的 `coordinate_note`/`align_rules`/`align_stats`/`tree_note` |
| `instance` | 字段 | 实例标识：`view_hash`/`id_hex`/`outer`/`aid`/`drawing_order` |

被剪的是**整棵子树**：一个节点被剪，它的后代一并剪掉。理由是坐标口径 —— 子节点的 `bounds_local` 是**相对该节点**的，节点没了，子节点的坐标就无法解释。

### 4.1 `--keep` 的语义是确定的

`--keep <开关>` = **把那个开关关掉**，把那类信息整类加回来。

```bash
python tv_tree.py --mode slim --keep empty            # 保留空节点
python tv_tree.py --mode slim --keep gone,offscreen   # 保留 GONE + 屏外
python tv_tree.py --mode slim --keep all              # 一个都不剪 → 等于全量
```

能这么用，是因为**每个节点只由一个开关认领**，按固定优先序先命中先认领：

```
gone → zeroarea → offscreen → empty
```

这个顺序不是随手定的。真机上 GONE 的 View 几乎都是零面积（`G.E...... 0,0-0,0`）；如果没有「一个节点只归一个开关」这条规矩，`--keep gone` 把 GONE 节点放过之后会立刻被 `zeroarea` 认领剪掉 —— 节点数一个不变，开关表里写着「可保留」的选项**实际不起作用**，而输出上完全看不出来。`selftest_tree.py` 用「`--keep gone` 必须得到 7 个节点而不是 6」把这条钉死。

`--keep` 只在 `--mode slim` 下有意义；配合 `--mode full` 用会直接报错（退出码 2），不会静默忽略；开关名写错同样报错。

### 4.2 输出里的自述

精简 JSON 的 `slim` 字段把这次剪枝讲清楚：`switches`（哪些开关执行了剪枝）、`pruned_nodes`（各开关剪掉多少节点，含后代）、`nodes`（剪前/剪后节点数）、`switch_meaning`、`ownership`（认领规则）、`field_defaults`（省略即默认值，默认值表在这里）。

---

## 5. 两个数据源与 R0–R3 配对

### 5.1 各自能拿到什么

| | a11y（主源，必需） | `dumpsys activity top`（补充源） |
|---|---|---|
| 文字 | 有（`text`/`content-desc`/`hint`） | **没有** |
| 坐标 | 屏幕绝对坐标，**屏幕上真实可见的矩形** | 相对父容器的布局矩形；**没有**绝对坐标 |
| 可见性 | 只收录可见、有面积的节点 | 有 `V`/`G` 标志，能看到 GONE 与屏外节点 |
| 其他 | 21 个属性 | flags1/flags2、实例 hash、无障碍 view id |
| 短板 | 无 GONE、无屏外、无实例标识；**自定义类名会被替换成框架类名** | 可寻址性差（应用资源 id 会被 R8 混淆）；**只覆盖承载 Activity 的窗口** |

最后一条要特别注意：`dumpsys activity top` 只输出承载 Activity 的窗口的视图树。本机 display 0 有 5 个窗口，只有 2 个有 View Hierarchy。当前台焦点落在对话框/输入法/壁纸等独立窗口上时，dump 里根本没有它的树 —— 这时工具会在 `segment_match_note` 里明说用的是回退段、不保证对应当前画面。

**a11y 拿不到就报错退出**（退出码 3），不会静默退回单一数据源。否则同一条命令会时对时错，比直接失败更坏。

### 5.2 合并规则（不是坐标猜测）

| 规则 | 成立条件 |
|---|---|
| `R0` root | 两侧各唯一根 → 同一窗口根 |
| `R1` geom | `pred_visible_rect(view) == a11y bounds` 且 res-id/class 谓词成立且**候选唯一** |
| `R2` focus | 两侧各自唯一持焦点节点，且 class 谓词成立 |
| `R3` seq | 父节点已配对时，a11y 子序列到 view 子序列的**保序全注入解唯一**才采用；多解（歧义）或零解一律拒绝并记进 `align_stats.seq_refused` |

两个谓词：

- **res-id**：view 侧 `app:id/X` 归一化成 `<段包名>:id/X` 后字符串相等（同为 `None` 也算相等）
- **class**：view 类名属框架类（`android.widget.*` 等）时要求与 a11y 类名**完全相等**；自定义类不要求（它会被 a11y 替换成框架类名，计入 `class_substituted`）

容错是「宁缺毋滥」：配对不上就配对不上，不做启发式匹配、不按统计择优。

### 5.3 几何校验四档

对每个配对成功的节点，用**未裁剪的累加布局矩形**跟 a11y 屏幕读数比一次：

| 档位 | 含义 |
|---|---|
| `exact` | 两者完全相等 → 该坐标被两个数据源独立证实 |
| `clip` | 只按祖先裁剪、或再按屏幕裁剪后相等 → 有屏外内容被裁 |
| `drift` | 都不等（实测为焦点项的 1.05 倍缩放动效） |
| `na` | 缺读数或缺布局矩形，无法比对 |

四档之和恒等于配对总数，不会有节点没被归过档。

---

## 6. 诚实边界

工具**不提供**这些，也不假装提供：

| 不提供 | 说明 |
|---|---|
| 系统焦点顺序 | 树里的子节点顺序是布局顺序，不等于按遥控器时的前进/后退顺序。要真实顺序，得用 `tv_input.py` 按一下、再取一次树来比对 |
| 屏外 / 滚动容器之外的内容 | a11y 只给可见部分。想看清就先用 `tv_input.py` 滚动，再重跑 |
| dumpsys 侧的滚动偏移 | dump 不含 `scrollX`/`scrollY`，所以累加出来的绝对坐标**有前提**：祖先链上没有滚动偏移。这个前提无法从数据里验证，只能由逐节点的 `geom_check` 间接反映 |
| 对话框 / 输入法窗口的树 | `dumpsys activity top` 不输出这类窗口；a11y 能拿到，但配对会缺席，工具会明说 |
| 操作设备的能力 | 本工具只读。按键是 `tv_input.py` 的事 |

拿不到就报错（退出码 3）或告警，不静默回退、不猜。解析期发现「有字段却没读出来」「缩进不是 2 的倍数」都会打成告警，不静默丢数据。

**截图不是数据源**：`tv_tree.py` 全程 0 次 `screencap`，只有 `tv_shot.py` 才会调它。

---

## 7. 自检与验收

```bash
python selftest_tree.py          # 离线，不连设备；通过 → 0，有失败 → 1
```

它用按**真机格式**手写的夹具（不是简化版）锁住：

- **dumpsys 解析**：缩进（每层 2 空格、起点 6）、flags 宽度（flags1 恒 9 位 / flags2 恒 8 位）、`app:id/x` 写法、解析告警
- **R0–R3**：每条规则的命中数、几何四档、类名替换计数、**view 节点守恒**（配上 + 补入 + 未定位 == view 节点总数）、多解/零解被拒
- **剪枝**：8 个开关各剪掉什么、`--keep` 的每一档、`--keep all` 时精简树与全量树**逐字节一致**、剪枝幂等、全量 JSON 不被剪枝污染
- **命令行**：离线重剪各分支、错误退出码、dumpsys 漂移判定（单调时钟字段必须被排除，否则恒定误报）
- **辅助脚本**：键码归一化、画框取坐标、祖先链溢出告警
- **画框几何（像素级）**：框上四边必须是画的颜色、再往外一格必须干净（钉死「框 = 读数」）；加宽对称；零面积 / 真越界 / 压屏幕外沿三类分开报。另有静态锁挡住三种「靠经验修偏差」的写法复发（见 §2.1）
- **职责边界与文档同步**：主脚本不含 `screencap`/`input keyevent`；README 必须写到每个开关名、每个脚本名，以及画框约定里的关键措辞

改代码后先跑它。它是唯一能在不接设备的情况下发现「行为悄悄变了」的手段。

---

## 8. 排查

| 现象 | 先看 |
|---|---|
| 提示 a11y 拿不到 / uiautomator2 未安装 | 装依赖；确认 `adb connect` 成功、`adb devices` 里是 `device` 而不是 `offline` |
| `source_consistency.drift: true` | 画面在动（动画、视频、时间在刷新）。配对结果可信度下降，建议画面静止时重跑 |
| `segment_match_note` 有内容 | 前台窗口的树不在 dump 里，用的是回退段，不保证对应当前画面 |
| `align_stats.view_unpaired` 有值 | 这些 dumpsys 节点位次无法唯一确定，它们会在 `dumpsys_only` 里单独列出 |
| `unexplained_visible_not_in_a11y` 有值 | a11y 没收录一个「可见且有面积」的节点，不是正常剪枝，值得单独查 |
| 焦点框画的位置不对 | 加 `--source both`，对照红（a11y 读数）与蓝虚线（派生）。不一致时看派生框的溢出告警 |
| 焦点框看起来比焦点「大一点/偏一点」 | **这是结果，不是缺陷**：框就是读数，差多少是读数本身差多少。先看焦点坐标对照的「差值」与「几何比例」，再决定信哪个源 —— **不要**去调框（§2.1） |
| 提示两轴换算系数不相等 | 截图宽高比与 `wm size` 对不上，换算已不是相似变换，框的位置无意义；先把两者对齐 |
| 提示框被裁到边界 | 那条读数的矩形本身就有一部分在屏幕外（如焦点缩放把上边顶出屏幕上沿），提示里给了原读数 |
| 想人工复核原始输入 | `--save-raw DIR`，会落盘 `u2_hierarchy.xml` + 两次 dumpsys 原文 |

---

## 9. 文件

| 文件 | 说明 |
|---|---|
| `tv_tree.py` | 核心：取控件树 → JSON（全量 / 精简） |
| `tv_adb.py` | 设备接入层：adb 调用、掉线自动重连、公共命令行参数、component 归一化 |
| `tv_input.py` | 发遥控器按键 |
| `tv_shot.py` | 截图 + 按树 JSON 画框 |
| `selftest_tree.py` | 离线自检 |
| `README.md` | 本文件 |

运行期产物（`--out`、`--save-raw` 指定的路径）不在此列，放哪由使用者决定。

---

## 10. 给开发者

改代码前先明确自己要动哪一层：

```
tv_adb.py     设备接入        （只管「怎么跟 adb 说话」）
  ↓
tv_tree.py    解析 → 配对 → 序列化 → 剪枝
  ├─ 解析     parse_dumpsys_top / parse_u2_xml
  ├─ 坐标     absolute_bounds（派生）/ clip_to_chain / pred_visible_rect
  ├─ 谓词     norm_res_id / class_ok / resid_ok
  ├─ 配对     align（R0–R3）/ merge_children（位次是否唯一，唯一判据只在这一处）
  ├─ 成树     build_unified（a11y 骨架 + 位次已定的 dumpsys 节点）
  ├─ 序列化   build_full_json
  └─ 剪枝     apply_prune / _owner_switch（认领唯一，见 §4.1）
```

三条容易踩的线：

1. **判据只能有一处**。比如「某个 dumpsys 独有节点的位次是否已确定」，判断只写在 `merge_children()` 里，统计与输出都调它。写两处就会漂移 —— 同一个节点既出现在主树里、又被列进「位置无法确定」。
2. **派生的前提要标出来**。`absolute_bounds()` 沿祖先链累加，隐含「祖先链上没有滚动偏移」；这个前提不能假设成立，只能由 `geom_check` 逐节点给结论。
3. **诚实优先于完整**。宁可输出「这里判不了」，也不要输出一个看着完整、实际是猜出来的结果。

改完之后按这个顺序验：

```bash
python -m py_compile tv_tree.py tv_adb.py tv_input.py tv_shot.py selftest_tree.py
python -m pyflakes  tv_tree.py tv_adb.py tv_input.py tv_shot.py selftest_tree.py   # 须无输出
python selftest_tree.py                                                            # 须退出码 0
```

接上设备还可以跑一遍真机流程：

```bash
python tv_tree.py --out full.json
python tv_tree.py --mode slim --out slim.json
python tv_input.py DPAD_DOWN
python tv_shot.py --json full.json --source both --out shot.png
```
