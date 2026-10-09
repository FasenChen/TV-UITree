# 网络与 USB 默认设备设置工具拆分

## 结果与使用

默认设备设置已拆成两个 MCP 工具，原 `set_default_device` 不再注册。五个读取工具的名称、参数、返回内容和连接逻辑保持当前行为。MCP 客户端需要刷新工具列表，并将原设置调用改为对应的新工具。

| 工具 | 参数 | 保存行为 |
|---|---|---|
| `set_default_network_device` | `TV_IP_Address` 必填；`port` 可省略或传 null | 修改 IP，省略端口时保留配置端口；显式端口一起保存；删除默认 USB serial |
| `set_default_usb_device` | `serial` 必填 | 保存默认 USB serial；保留已有网络字段和其他配置 |

网络调用示例：

```json
{"TV_IP_Address": "192.0.2.10"}
```

例如原配置端口为 5556，上述调用后仍是 5556。程序不会自动补 5555；配置缺少有效端口时，需要在网络调用中显式提供 port。

USB 调用示例：

```json
{"serial": "USB_SERIAL"}
```

两个工具只保存配置，不连接设备。继续使用共享 `update_default_device` 校验与原子保存，返回 previous、current、config_path；输入或保存失败仍返回 error、error_type。类型保持 strict，避免将 true、数字字符串或其他不合法输入转换后写入。

## 影响范围

- `interfaces/mcp.py`：拆分工具签名及各自的 save 计时；未新增配置保存层或依赖。
- `scripts/collect_tv_scene.py`：动态工具发现后跳过两个设置工具，保持现场报告只读。
- `tests/selftest_tree.py`：更新注册名称与 schema、现有配置测试的调用名；覆盖非 5555 端口保留、USB/网络切换、失败配置保留、独立 timing，以及现场采集实际调用名单。
- README、AGENTS、压测指南与文档索引：同步当前用法。历史计划及报告保留原时点内容。

## 实际验证

| 检查 | 结果 |
|---|---|
| 接入前新增回归 RED | 1260 条断言中 7 项失败，复现新工具未注册、schema 缺失及报告脚本未排除新设置工具 |
| 完整离线自检 GREEN | 1273 条断言全部通过，退出 0 |
| 压测离线自检 | `tests/selftest_bench_mcp.py` 通过 |
| 编译与静态检查 | .venv 的 py_compile、pyflakes 覆盖 main.py、tvuitree、tests 和两个相关脚本，均通过 |
| CLI 与差异 | main.py --help、tree --prune-list、git diff --check 均通过 |
| 真实 stdio MCP | 发现 7 个工具；网络/USB 参数分别公开、必填字段正确、旧设置工具缺席；临时配置中 3 次有效设置成功、6 次无效调用被拒绝，失败时配置字节不变 |
| 配置保护 | 本机 config.json 的现有用户修改被保留；stdio 验证前后 SHA-256 一致，所有保存验证使用临时配置 |

使用项目已安装的 MCP 1.30.0、Pydantic 2.13.5。原始日志和临时协议验证程序在忽略的 `_temp/split_device_set/`，不随仓库交付，不归档本机设备地址或序列号。

## Ponytail 自审与边界

本次由实施方按 Ponytail review 做自审，追踪两个工具到共享配置写入函数、真实 schema、timing 和动态报告消费者；没有发现阻塞问题。这不是独立 reviewer 的审核结论。只读报告的异步测试替身保留会话创建、初始化、工具发现、调用和退出的生命周期。

本次修改设置接口，未连接或操作真实 TV；有线/网络真机采集及当前客户端刷新后的页面显示未重新验收。未暂存、提交、推送或发布。旧工具移除属于有意接口变化，外部客户端如保存了旧调用名，需要更新。
