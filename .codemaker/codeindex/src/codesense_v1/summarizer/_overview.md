---
module_id: summarizer
architectural_role: "LLM Prompt 生成与摘要管理"
world_model_hints:
  - "位于 tools 之下、data 和 cache 之上，组装 LLM prompt 并解析/保存 Agent 生成的内容"
upstream_modules:
  - module: tools
    confidence: extracted
downstream_modules:
  - module: data
    confidence: extracted
  - module: cache
    confidence: extracted
---

## Files

### 源代码路径
- `src/codesense_v1/summarizer/summarizer.py`

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/summarizer/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/summarizer/summarizer_core.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `summarizer_core.md` | 核心 API、prompt 构建器、数据流、调用链 | `get_project_map_prompt`, `submit_project_map`, `get_module_prompt`, `save_module_summary`, `_compute_module_hash`, `_build_project_map_prompt`, `_build_module_prompt` |

## 模块概述

本模块负责两件事：(1) 从 data 层获取 CodeGraph DB 的结构化数据，组装成 LLM 可理解的分析 prompt；(2) 解析 Agent 返回的文本内容，写入 cache 层持久化。是 tools（MCP 入口）和 data/cache（数据与存储）之间的桥梁。

上游：tools 模块的 6 个 tool 函数全部调用 summarizer（`get_project_map_prompt_tool → get_project_map_prompt`、`project_map → (cache miss → Agent → get_project_map_prompt → submit_project_map)` 等）。

下游：`data` 层提供 `list_modules`、`module_dependencies`、`compute_centrality`、`extract_file_docstring`、`cross_dir_public_api`、`extract_symbol_docstrings` 等查询函数；`cache` 层提供 `read_modules_index`、`write_modules_index`、`write_project_map`、`write_module`、`write_module_hash`、`db_hash` 等读写接口。

## 架构简析

单文件模块 `summarizer.py`，核心分为三部分：

1. **目录解析**（`_resolve_roots_and_aux`、`_filter_dir_deps`、`_is_under_roots`）：确定 L1 核心目录与 L2 辅助目录，过滤出根目录下的依赖关系。
2. **Prompt 构建**（`get_project_map_prompt` → `_build_project_map_prompt`、`get_module_prompt` → `_build_module_prompt`）：从 DB 提取目录符号、依赖关系、拓扑层级、循环依赖、docstring 等，组合为结构化 Markdown prompt。
3. **提交与保存**（`submit_project_map`、`save_module_summary`、`_compute_module_hash`）：解析 Agent 响应文本（pipe-delimited 格式），写入 modules_index 和 project_map/module_summary 缓存。

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：tools（全部 6 个 MCP tool 函数调用 summarizer 的 4 个公开函数）
- **下游**：data（CodeGraphDB 查询、架构分析函数）、cache（缓存文件读写）
