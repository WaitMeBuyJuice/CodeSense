---
module_id: tools
architectural_role: "MCP 工具适配层"
world_model_hints:
  - "位于 MCP Client 与 summarizer/cache/data 之间，是 Agent 与 CodeSense 系统的唯一入口"
  - "每个 tool 文件 = 一个 MCP endpoint，负责参数校验、缓存查询、委派给 summarizer"
upstream_modules:
  - module: MCP Client
    confidence: inferred
downstream_modules:
  - module: summarizer
    confidence: extracted
  - module: cache
    confidence: extracted
  - module: data
    confidence: extracted
---

## Files

### 源代码路径
- `src/codesense_v1/tools/`（6 个工具文件 + `__init__.py`）

| 文件 | 对应 MCP Tool | 核心函数 |
|------|--------------|---------|
| `explore_module.py` | `explore_module` | `explore_module(module_name: str) -> str` |
| `project_map.py` | `project_map` | `project_map() -> str` |
| `get_project_map_prompt.py` | `get_project_map_prompt` | `get_project_map_prompt_tool() -> str` |
| `get_module_prompt.py` | `get_module_prompt` | `get_module_prompt_tool(module_name: str) -> str` |
| `save_module_summary.py` | `save_module_summary` | `save_module_summary_tool(module_name: str, summary: str) -> str` |
| `submit_project_map.py` | `submit_project_map` | `submit_project_map_tool(response: str) -> str` |

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/tools/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/tools/tools_endpoints.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `tools_endpoints.md` | 6 个 MCP Tool 端点签名、调用链、缓存命中/未命中流程 | `explore_module`, `project_map`, `get_project_map_prompt_tool`, `get_module_prompt_tool`, `save_module_summary_tool`, `submit_project_map_tool` |

## 模块概述

本模块是 CodeSense 系统对 MCP Agent 暴露的接口层。6 个 tool 函数通过 `@tool` 装饰器注册到 MCP registry，每个函数负责：

1. **参数校验**：检查 `module_name` 非空、`CODESENSE_PROJECT_ROOT` 已设置等
2. **缓存查询**：读 `.codesense/` 目录的缓存（project_map.md、module summaries）
3. **委派生成**：缓存未命中时调用 summarizer 生成 prompt 或解析/保存 Agent 响应

核心设计模式：**Lazy Cache with Agent-Driven Generation**。缓存命中直接返回；缓存未命中返回结构化工作流指令，指导 Agent 通过 `get_*_prompt → 生成 → submit/save` 闭环完成内容生产。

上游：MCP Client 通过 registry dispatch 调用对应 tool 函数。

下游：`summarizer`（4 个公开函数）、`cache`（读缓存判断命中、读模块哈希）、`data`（`_compute_module_hash` 内部使用 CodeGraphDB 的 `iter_nodes`）。

## 架构简析

6 个文件结构高度一致：

```
@tool(description=..., input_schema=...)
async def xxx_tool(...) -> str:
    # 1. 读 CODESENSE_PROJECT_ROOT 环境变量
    # 2. 参数校验（空值、DB 存在性）
    # 3. 缓存查询（cache.read_xxx）
    # 4. 命中 → 返回缓存内容；未命中 → 返回 Agent 指令 / 委派 summarizer
```

`explore_module` 最复杂：包含辅助目录检查、L1 模块查找、per-module 缓存 + hash 校验。`project_map` 次之：全局 DB hash 校验 + 缓存命中/未命中分支。其余 4 个 tool 函数为薄层适配器，直接委托给 summarizer。

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：MCP Client（通过 `@tool` registry dispatch）
- **下游**：summarizer（prompt 生成、解析保存）、cache（缓存读写）、data（`_compute_module_hash` 使用 CodeGraphDB）
