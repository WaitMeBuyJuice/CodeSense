---
entity_names:
  constants: []
retrieval_hints:
  - "如何定义新的错误类型？"
  - "ToolError 的子类有哪些？"
  - "LLM 调用失败时抛出什么异常？"
  - "⚠️ 如果你要找的是 MCP 协议错误码，不在这里，在 server 模块"
  - "新增的错误类型必须继承 ToolError，不可直接继承 Exception"
architectural_role: "横切错误域，定义统一异常层次"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部 raise/catch。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：无

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `summarizer` | 参数校验失败时 raise | `InvalidArgumentError` |
| `tools` | 工具函数参数校验失败 | `InvalidArgumentError` |
| `registry` | dispatch 捕获 ToolError 转 isError 响应 | `ToolError` |

## 典型调用链

### 工具调用 → 错误处理
```
MCP Client → server.dispatch → registry.dispatch(tool_name, args)
  → tools.explore_module(module_name)  ← 参数校验失败
    → raise InvalidArgumentError("模块名不能为空")
      → registry.dispatch catch ToolError → _error(e.message)
        → CallToolResult(isError=true, content=[TextContent(text=e.message)])
```

## 实现约束清单

> 实现本模块相关需求时，Agent 必须在动笔前逐条核对以下项。

### 必须定义的常量/枚举

| 标识符 | 值 | 所在文件 | 说明 |
|-------|----|---------|------|
| `ToolError` | 基类 | `errors.py` | 所有可预期业务错误的基类，不可直接用于内部异常 |
| `ValidationError` | 继承 ToolError | `errors.py` | Schema 校验失败专用 |
| `InvalidArgumentError` | 继承 ToolError | `errors.py` | 语义层非法参数专用 |
| `LLMError` | 继承 ToolError | `errors.py` | LLM API 调用失败专用 |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| 基类选择 | 自定义 `ToolError(Exception)` | 直接使用 `ValueError`/`RuntimeError` | 统一 `message` property 契约，使 registry 能区分业务错误与内部异常 |
| 异常粒度 | 三层子类（Validation/InvalidArgument/LLM） | 单一 ToolError + error_code | 子类即分类，无需额外错误码表，MCP client 可直接展示 message |
