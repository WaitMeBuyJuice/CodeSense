---
module_id: server
architectural_role: "MCP 服务入口层"
world_model_hints:
  - "MCP stdio 服务启动与请求路由，最外层"
upstream_modules: []
downstream_modules:
  - module: registry
    confidence: extracted
  - module: tools
    confidence: inferred
---

## Files

### 源代码路径
- `src/codesense_v1/server/`

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/server/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/server/server_core.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `server_core.md` | MCP stdio 服务启动、请求路由 | main, CodeSenseServer |

## 模块概述

本模块是 CodeSense MCP Server 的入口层，负责启动 stdio 传输、注册 MCP 请求处理器（tools/list、tools/call），将 MCP 协议请求路由到 registry 层进行工具调度。

上游：MCP Client（Claude Desktop / VS Code / 其他 MCP 宿主）通过 stdio 发起请求。

下游：调用 registry.list_tools() 和 registry.dispatch() 完成工具发现与执行。

## 架构简析

双层结构：`__main__.py`（`main()` 函数，启动入口）→ `server.py`（`CodeSenseServer` 类，MCP Server 实例化与 handler 注册）。使用 `mcp` 库的 `StdioServerTransport` 实现 stdio 通信，handler 注册为 `@server.list_tools()` 和 `@server.call_tool()` 装饰器。

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：MCP Client（外部，通过 stdio）
- **下游**：registry（list_tools / dispatch）
