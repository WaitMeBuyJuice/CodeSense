---
module_id: registry
architectural_role: "工具注册与调度层"
world_model_hints:
  - "介于 MCP Server 与 Tool 实现之间的中间层，负责注册、校验、调度"
upstream_modules:
  - module: server
    confidence: extracted
  - module: tools
    confidence: extracted
downstream_modules:
  - module: errors
    confidence: extracted
---

## Files

### 源代码路径
- `src/codesense_v1/registry/`

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/registry/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/registry/registry_core.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `registry_core.md` | @tool 装饰器、dispatch 调度、list_tools 枚举 | tool, dispatch, list_tools |

## 模块概述

本模块提供 MCP 工具注册与调度机制。通过 `@tool` 装饰器声明式注册工具函数（含 JSON Schema 校验），`dispatch` 统一执行参数校验→调用→异常捕获流程，`list_tools` 枚举所有已注册工具的 MCP Tool 描述。

上游：server 模块调用 `list_tools()` 响应 MCP `tools/list` 请求，调用 `dispatch()` 响应 `tools/call` 请求；tools 模块各函数通过 `@tool` 装饰器自注册。

下游：dispatch 捕获 ToolError 异常转为 MCP 错误响应，依赖 errors 模块的异常层次。

## 架构简析

单文件模块 `registry.py`，核心是 `_ToolRegistry` 全局单例。结构：`@tool` 装饰器接收 JSON Schema → 存入 `_tools: dict` → `list_tools()` 遍历生成 MCP Tool 描述列表 → `dispatch(name, args)` 查表→jsonschema 校验→调用 handler→catch ToolError 转 isError。

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：server（list_tools / dispatch 的直接调用者）、tools（@tool 装饰器的使用者）
- **下游**：errors（捕获 ToolError 并转为 MCP 错误响应）
