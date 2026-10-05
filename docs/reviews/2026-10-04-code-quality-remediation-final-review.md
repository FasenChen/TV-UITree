# 观测质量补修独立终审（2026-10-04）

本轮采用一位独立新上下文审查者，集中检查全部未提交实现。原始结论为 **With fixes**：无 Critical、无另需处理的 Minor，有 1 项 Important。执行者随后用有效 RED→GREEN 关闭该问题，不将补修后的版本冒称为审查者再次 APPROVE。

## 审查对象与依据

- 基线及审查时 HEAD：`c5eb108494b8a221eba0cf5074bd162c6676cf28`；分支 `codex/code-quality-remediation`。实现全部为 worktree 未提交差异。
- 审查差异 SHA-256：`b4a24bf467a786e2edcbfb6a2880bf4565932aec7eb05c380bccba104268ed53`。
- 审查者核对逐文件 manifest，实时 diff 与 review.diff 精确匹配。此绑定对应补修前版本；补修后文件哈希另保存在 final-manifest.json，不能混用。
- 依据：[Q1–Q9 评审](2026-10-03-current-code-quality-and-architecture.md)、[实施计划](../superpowers/plans/2026-10-03-code-quality-remediation-deepseek.md)、[交付报告](../reports/2026-10-03-code-quality-remediation-delivery.md)。

## 已确认的主体实现

R1 的候选图保持静态且双向唯一；明确 False 与未知状态区分；损坏 XML 不再伪装合法空树；键码序列整体预检；无标签开关保留真实读数。五项 Review Focus 和 Q1–Q9 的主案例均与实现吻合，原分层和有效旧断言保持。

审查者独立运行完整自检，1079 条通过；diff check 通过。19 个金样中的 16 个精确相同、3 个差异与交付声明一致，全部 PNG 字节相同。审查全过程只读，没有编辑代码、索引、HEAD 或分支。

## Important：合法稀疏焦点节点的截图比较外漏异常

审查位置：补修前 `tvuitree/domain/screenshot.py:199–201`，与新增 `domain/tree/output.py:validate_full_json` 的兼容边界有关。

输入示例：

```json
{"tree":[{"source":"a11y","class":"android.widget.Button","focused":true,"bounds_screen":null}]}
```

新校验正确允许坐标缺失，但 compare_focus 的末分支默认 dumpsys 坐标存在，两来源均未知时解引用 None。审查者用纯函数和真实 CLI 复现 TypeError；该缺陷已经存在，本轮明确保留稀疏输入，因此需要补齐消费者契约。

执行者增加第 33 组回归，覆盖字段缺失、字段为 null 两种输入。使用真实 JSON 文件、正常 2×2 PNG 和实际 Pillow 绘图，不替换消费者或设备操作。RED 正常汇总：1087 条断言中 6 条失败；修复为 `elif d` 区分仅派生坐标，并在两来源均无坐标时输出“坐标未知”。没有收紧合法输入，也没有加广泛 except。

GREEN：1087 条自检、compile、pyflakes、diff check 通过；默认/GBK 非 UTF-8 父进程完整自检通过。真实 MCP stdio 错误路径仍通过。新建 post-review 金样与补修前 final 的 19 文件全部精确相同，正常截图几何保持不变。该 Important 已由执行者关闭，没有再派发第二轮审查。

## 审查者考虑但未判定及执行裁定

1. **真机采集、截图时序漂移、Android 多窗口**：审查未访问设备，配置目标也未处于 device 状态。裁定保持真机待验证，不从离线结果推断。风险是设备端服务/多窗口差异仍可能暴露问题。
2. **MCP 长期并发、Inspector、新版依赖**：本轮没有这些改动或对应环境。裁定维持排除范围。风险是长期运行与其他版本兼容性未获验证。
3. **完整 metadata schema、重复加载器整理**：本轮采用实际消费结构的最小校验。裁定不扩展为全模型/加载器重构。风险是未来消费者增加字段时需要同步补校验。
4. **XML 属性缺失时的既有默认值策略**：T2 的需求是 full JSON 摘要保留缺失/None，未重新定义 uiautomator2 XML 属性契约。裁定保留解析器策略，不以本轮结果宣称部分 XML 属性未知语义已改。风险是非标准或字段缺失的 XML 状态可能仍不精确，须另行确认来源契约。

无独立审查发现的待处理 Minor。终审结论的范围不包括真实设备成功采集、协议压力或依赖升级。
