---
module_id: tools
architectural_role: "MCP 工具层"
world_model_hints:
  - "L3 工具层，@tool 装饰器注册，server import 触发注册，registry dispatch 调用"
upstream_modules:
  - module: server
    confidence: extracted
  - module: registry
    confidence: extracted
downstream_modules:
  - module: data
    confidence: extracted
  - module: summarizer
    confidence: extracted
  - module: cache
    confidence: extracted
  - module: errors
    confidence: extracted
---

## Files

| 源码路径 | 职责 |
|---------|------|
| `src/codesense_v1/tools/__init__.py` | import 全部 8 个工具子模块触发 `@tool` 注册；无导出符号，副作用即注册 |
| `src/codesense_v1/tools/_project_root.py` | 共享辅助：`resolve_project_root()` 三级 fallback 定位项目根；`project_root_not_found_error()` 返回错误 Markdown |
| `src/codesense_v1/tools/project_map.py` | `project_map` 工具：返回项目架构概览（4 段拼接），缺失段引导 Agent 生成 |
| `src/codesense_v1/tools/explore_module.py` | `explore_module` 工具：返回模块深度理解，缓存未命中引导生成 |
| `src/codesense_v1/tools/get_module_prompt.py` | `get_module_prompt` 工具：委派 `summarizer.get_module_prompt` |
| `src/codesense_v1/tools/get_identity_segment_prompt.py` | `get_identity_segment_prompt` 工具：收集 identity sources + 委派 summarizer |
| `src/codesense_v1/tools/get_modules_segment_prompt.py` | `get_modules_segment_prompt` 工具：委派 `summarizer.get_project_map_prompt` |
| `src/codesense_v1/tools/submit_project_map.py` | `submit_project_map` 工具：委派 `summarizer.submit_project_map` |
| `src/codesense_v1/tools/save_project_map_segment.py` | `save_project_map_segment` 工具：校验 segment_id + 写 `cache.write_segment` |
| `src/codesense_v1/tools/save_module_summary.py` | `save_module_summary` 工具：委派 `summarizer.save_module_summary` |

## 子文档速览

| 子文档 | 关键实体（工具名） |
|--------|------------------|
| `tools/tools_project_map.md` | project_map / get_identity_segment_prompt / get_modules_segment_prompt / submit_project_map / save_project_map_segment |
| `tools/tools_module.md` | explore_module / get_module_prompt / save_module_summary |

## 模块概述

`tools` 是 CodeSense 的 MCP 工具层，每个 `.py` 文件实现 1 个工具，通过 `@tool(name, description, input_schema)` 装饰器自注册到 `registry`，`__init__.py` 集中 import 触发注册。上游被 `server`（import 触发注册）和 `registry`（dispatch 调 handler）驱动。下游依赖 `data`（DB 查询）、`summarizer`（业务逻辑委派）、`cache`（段/模块缓存读写）、`errors`（`InvalidArgumentError`/`LLMError`）。

## 架构简析

分层结构：`server → registry → tools(handler) → {data, summarizer, cache, errors}`。

核心文件：`project_map.py`（最复杂，含 4 段 hash 计算 + 程序渲染 02/04 + 引导 01/03）、`explore_module.py`（模块缓存命中/未命中分支）、`_project_root.py`（全工具共享的项目根定位）。

数据流：客户端 `tools/call` → `registry.dispatch`（schema 校验）→ tools handler（参数校验 + 委派 summarizer/cache/data）→ 返回 `str`（registry 包装为 `TextContent`）。

`@tool` 注册机制：装饰器在模块 import 时执行，将 `(name, handler, schema, description)` 写入 registry 的 `ToolSpec` 表；`__init__.py` 用 `# noqa: F401` 标注纯副作用 import，`__all__` 为空列表。

`_project_root` 三级 fallback：① `CODESENSE_PROJECT_ROOT` 环境变量（最高优先级，显式指定）→ ② MCP `roots/list`（客户端 IDE 工作区根，通过 `request_ctx.get()` 取 session 调 `list_roots()`）→ ③ CWD 向上最多 10 级查找 `.codegraph/codegraph.db`。三级全失败返回 `None`，调用方用 `project_root_not_found_error()` 生成错误 Markdown。

## 上下游关系

**上游（调用方）**：
- `server`：`import codesense_v1.tools` 触发全部工具注册（`# noqa: F401`），不直接调用 handler。
- `registry`：`dispatch(name, arguments)` 按 name 查 ToolSpec 表调对应 handler，做 schema 校验与异常→MCP 错误响应转换。

**下游（被依赖）**：
- `data`：`project_map`/`save_project_map_segment` 调 `list_modules`/`module_dependencies`/`collect_identity_sources`/`compute_*_hash`/`classify_top_dirs`/`directory_tree` 等；`get_identity_segment_prompt` 调 `collect_identity_sources`/`extract_tech_stack_hint`。
- `summarizer`：`get_module_prompt`/`get_modules_segment_prompt`/`submit_project_map`/`save_module_summary` 委派对应函数；`project_map` 调 `render_structure_segment`/`render_dependencies_segment`/`is_auto_expire_enabled`；`explore_module` 调 `is_auto_expire_enabled` + `_compute_module_hash`。
- `cache`：`project_map`/`explore_module`/`save_project_map_segment` 读写段/模块缓存（`read_segment`/`write_segment`/`is_segment_valid`/`render_project_map`/`read_modules_index`/`read_module`/`read_module_hashes`/`safe_key`）。
- `errors`：`explore_module`/`get_module_prompt`/`save_module_summary`/`save_project_map_segment` 抛 `InvalidArgumentError`；`submit_project_map` 抛 `LLMError`（经 summarizer 传播）。
