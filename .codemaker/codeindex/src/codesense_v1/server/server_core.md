---
entity_names:
  constants: []
retrieval_hints:
  - "CodeSense Server 怎么启动？"
  - "MCP 请求如何路由到工具函数？"
  - "如何添加新的 MCP 请求处理器？"
  - "⚠️ 如果你要找的是工具函数的实现，不在这里，在 tools 模块"
  - "新增 MCP 能力时应优先在 tools 模块添加工具函数，而非在 server 层扩展协议"
architectural_role: "MCP 服务入口，协议适配层"
---

## 对外接口

| 接口 | 方向 | 关键字段 | 业务说明 | 入口符号 |
|------|------|---------|---------|---------|
| `tools/list` | MCP 请求 | 无参数 | 枚举所有已注册工具 | `server.py:handle_list_tools` |
| `tools/call` | MCP 请求 | `name`(string), `arguments`(object) | 调用指定工具 | `server.py:handle_call_tool` |

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：

| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|---------|---------|------------|
| `registry` | 工具枚举与调度 | `list_tools`, `dispatch` | extracted |

> 反向依赖（谁调用了本子模块）：无（最外层，仅被 MCP Client 通过 stdio 调用）

## 典型调用链

### 服务启动 → 工具调用
```
codesense_v1 命令 → __main__.py:main()
  → server.py:CodeSenseServer.__init__  ← 创建 MCP Server 实例
  → @server.list_tools() → registry.list_tools()  ← 注册工具列表处理器
  → @server.call_tool() → registry.dispatch(name, args)  ← 注册工具调用处理器
  → stdio_server.run()  ← 启动 stdio 传输，等待 MCP Client 连接

MCP Client → tools/call → handle_call_tool
  → registry.dispatch(name, arguments)
    → 校验 → 调用 handler → 返回结果/错误
```

## 实现约束清单

### 必须实现的函数

| 函数名 | 所在文件 | 说明 |
|--------|---------|------|
| `main` | `__main__.py` | 服务入口，**必须在此初始化 CodeSenseServer 并启动 stdio 传输** |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| 传输协议 | stdio (StdioServerTransport) | HTTP/SSE | stdio 是 MCP 标准本地传输，零配置，无需端口管理 |
| 请求路由 | 装饰器注册 handler | 手动路由表 | mcp 库推荐模式，类型安全 |
| server 层职责 | 仅做协议适配和路由 | 混合业务逻辑 | 保持 server 薄层，业务逻辑在 tools/summarizer |
