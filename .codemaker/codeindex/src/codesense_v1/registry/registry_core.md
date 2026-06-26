---
entity_names:
  constants: []
retrieval_hints:
  - "@tool 装饰器怎么用？"
  - "如何注册一个新的 MCP 工具？"
  - "dispatch 函数的参数校验流程是什么？"
  - "⚠️ 如果你要找的是 MCP Server 启动逻辑，不在这里，在 server 模块"
  - "新增工具函数必须用 @tool 装饰器注册，不可绕过 registry 直接暴露"
architectural_role: "工具注册与调度中间层"
---

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：

| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|---------|---------|------------|
| `errors` | 捕获 ToolError 转为 MCP 错误响应 | `ToolError` | extracted |

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `server` | MCP tools/list 和 tools/call 请求处理 | `list_tools`, `dispatch` |
| `tools` | 各工具函数自注册 | `@tool` |

## 典型调用链

### 工具调用完整路径
```
MCP Client → tools/call {"name":"explore_module", "arguments":{"module_name":"data"}}
  → server.handle_call_tool()
    → registry.dispatch("explore_module", {"module_name":"data"})
      → _tools["explore_module"] 查表
      → jsonschema.validate(args, inputSchema)  ← Schema 校验
      → handler(**args)  ← 调用 tools.explore_module("data")
      → 成功: CallToolResult(content=[TextContent(text=result)])
      → 失败: catch ToolError → _error(e.message) → CallToolResult(isError=true)
```

## 实现约束清单

### 必须定义的常量/枚举

| 标识符 | 值 | 所在文件 | 说明 |
|-------|----|---------|------|
| `_ToolRegistry` | 全局单例 | `registry.py` | 存储已注册工具的核心字典 |

### 必须实现的函数

| 函数名 | 所在文件 | 说明 |
|--------|---------|------|
| `dispatch` | `registry.py` | 统一调度入口，含 Schema 校验→调用→异常捕获，**不可跳过 Schema 校验步骤** |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| 注册方式 | `@tool` 装饰器声明式注册 | 手动调用 `register()` | 声明式更简洁，工具定义与注册不分离 |
| 错误处理 | dispatch 统一 catch ToolError | 各工具自行 try/except | 统一错误格式，避免工具遗漏异常处理 |
| Schema 校验 | jsonschema 库 | 手写校验逻辑 | 标准化，支持复杂嵌套 Schema |
