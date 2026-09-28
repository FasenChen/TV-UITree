# MCP Inspector 安装与使用指南

## 1. 简介

MCP Inspector 是用于检查和调试 Model Context Protocol（MCP）服务器的官方工具。它提供网页、命令行和终端界面，可以连接 MCP 服务器，查看其能力、调用工具，并检查协议通信。本文介绍通用操作方法，可直接用于 Wiki；具体服务器的启动命令、参数和认证方式应以该服务器自身文档为准。

Inspector 是调试客户端。网页中看到的业务工具由所连接的 MCP 服务器提供，并非 Inspector 固定内置的工具。

## 2. 安装前准备

1. 安装 Node.js **22.19.0 或更高版本**。从 [Node.js 官网](https://nodejs.org/)获取安装包。
2. 打开新的终端，确认 Node.js 和 `npx` 可用：

   ```powershell
   node --version
   npx --version
   ```

3. 准备要调试的 MCP 服务器。若它以本地进程运行，先确认启动命令、参数、工作目录及所需环境变量；若它提供 HTTP 地址，先确认服务已运行，并取得准确的 MCP 端点 URL。

Inspector 可由 `npx` 直接运行，无须预先全局安装。首次运行时，`npx` 需要从 npm 获取软件包；之后通常使用本机缓存。官方当前要求 Node.js 22.19.0 或更高版本，见 [MCP Inspector 官方文档](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector)。

## 3. 启动网页界面

### 3.1 先打开 Inspector，再在网页中添加服务器

```powershell
npx -y @modelcontextprotocol/inspector
```

这种方式适合在网页的 **Servers** 页面添加、编辑和切换多个服务器。首次启动时可能出现官方示例服务器；按实际需要添加自己的服务器即可。

### 3.2 连接本地 stdio 服务器

将服务器的启动命令及其参数放在 Inspector 命令后面。以下是通用 Python 示例，实际路径和参数应按目标服务器说明替换：

```powershell
npx -y @modelcontextprotocol/inspector python C:\path\to\server.py
```

若服务器依赖项目工作目录，可显式指定 `--cwd`：

```powershell
npx -y @modelcontextprotocol/inspector --cwd C:\path\to\project python C:\path\to\project\server.py
```

也可传入虚拟环境中的 Python 绝对路径。此方式启动的是一个临时目标服务器，不会将它写入 Inspector 的服务器目录。

### 3.3 连接 HTTP 服务器

先按目标服务器的说明启动它，再用其 MCP 端点 URL 连接。下例中的地址仅作格式示范：

```powershell
npx -y @modelcontextprotocol/inspector --server-url http://127.0.0.1:8000/mcp --transport http
```

若服务器使用 SSE，按其文档将传输类型设为 `sse`，并填写对应端点。需要认证头或 OAuth 时，使用服务器提供的配置；不要把访问令牌写入公开文档。

### 3.4 打开与停止

启动后，终端会打印包含会话令牌的完整本机网址。**复制本次启动输出的完整网址**到浏览器；不要只凭记忆输入端口。会话令牌用于保护可在本机启动进程的 Inspector 后端，不应发布到 Wiki。默认情况下 Inspector 只绑定本机地址。

保持启动终端运行。调试结束后，在该终端按 `Ctrl+C` 停止 Inspector。下次启动时重新使用新的终端输出网址。

## 4. 网页界面与调试流程

1. 在 **Servers** 页面查看连接状态。未连接时，按目标服务器文档添加或选择服务器并连接。
2. 在 **Tools** 页面查看服务器提供的工具、描述和输入参数。选择工具，填写参数，执行调用，并检查文本、结构化数据、图片或错误信息。
3. 服务器提供其他能力时，可在 **Resources** 页面读取资源，在 **Prompts** 页面填写参数并预览提示模板。
4. 调试协议行为时查看 **Protocol** 中的请求、响应和通知。本地 stdio 服务器的诊断输出显示在 **Console**；HTTP 或 SSE 连接的网络请求显示在 **Network**。这些页面是否出现取决于服务器能力和传输方式。

推荐从查看工具定义开始，再以最简单的有效参数调用一次；出现错误时，对照协议记录、服务器诊断输出和目标服务器文档定位问题。网页工具表单依据服务器声明的输入 schema 生成，因此每个服务器的工具名称和参数都可能不同。

### 常见页面的作用

| 页面 | 主要用途 |
|---|---|
| Servers | 添加、选择、连接服务器，查看连接状态 |
| Tools | 查看工具 schema、填写参数并检查调用结果 |
| Resources | 查看和读取服务器公开的资源 |
| Prompts | 查看提示模板并预览生成的消息 |
| Protocol | 检查 MCP 的 JSON-RPC 请求、响应和通知 |
| Console | 查看 stdio 服务器写入标准错误的诊断信息 |
| Network | 查看 HTTP 或 SSE 连接的状态、请求头和响应 |

服务器的 `tools`、`resources` 或 `prompts` 能力未提供时，对应页面或内容可能不会出现。更多界面细节见 [官方网页界面说明](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/web)。

## 5. 命令行快速验证

无需启动网页时，可以使用 Inspector 的 CLI 模式检查服务器。以下仍以通用 Python stdio 服务器为例：

```powershell
npx -y @modelcontextprotocol/inspector --cli python C:\path\to\server.py --method tools/list
```

检查 HTTP 服务器的工具列表：

```powershell
npx -y @modelcontextprotocol/inspector --cli --server-url http://127.0.0.1:8000/mcp --transport http --method tools/list
```

`tools/list` 成功返回工具名称和输入 schema，只证明 MCP 连接与工具发现正常；工具执行是否成功，还取决于目标服务器自身的配置、权限和外部依赖。CLI 还支持 `tools/call` 等方法，参数格式见 [官方 Inspector CLI 文档](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/cli)。

## 6. 常见问题

| 现象 | 检查方向 |
|---|---|
| `npx` 无法识别 | 检查 Node.js 安装与终端 PATH，重新打开终端后运行 `node --version` 和 `npx --version` |
| 首次启动停留在下载阶段 | 检查 npm 网络连接；首次运行需要获取 Inspector 软件包 |
| 浏览器无法打开页面 | 使用当前终端输出的完整网址，确认 Inspector 进程仍在运行 |
| 网页打开但连接失败 | 核对目标服务器的启动命令或 HTTP 端点、传输类型、工作目录和认证配置 |
| 已连接但看不到预期工具 | 检查服务器是否声明了 `tools` 能力，以及 **Protocol** 中的 `tools/list` 结果；核对服务器版本 |
| stdio 服务器异常退出 | 查看 **Console** 中的标准错误输出；确认运行时、依赖和环境变量可用 |
| HTTP 调用失败 | 查看 **Network** 中的状态码、请求与响应，并核对服务端日志 |

对于 stdio 服务器，标准输出用于 MCP 协议通信；普通诊断日志应写入标准错误，否则可能干扰连接。

## 7. 参考资料

- [MCP Inspector 官方文档](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector)
- [Inspector 网页界面说明](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/web)
- [Inspector 配置与命令参数](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/configuration)
- [MCP Inspector 官方仓库](https://github.com/modelcontextprotocol/inspector)
