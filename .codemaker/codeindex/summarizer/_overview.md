---
module_id: summarizer
architectural_role: "摘要协调层"
world_model_hints:
  - "协调层，组合 data+cache，产出 prompt 与渲染 Markdown，不直接调 LLM"
upstream_modules:
  - module: tools
    confidence: extracted
downstream_modules:
  - module: data
    confidence: extracted
  - module: cache
    confidence: extracted
  - module: errors
    confidence: extracted
---

## Files

- `src/codesense_v1/summarizer/summarizer.py`（单文件约 1567 行，全部逻辑集中于此）
- `src/codesense_v1/summarizer/__init__.py`（仅 re-export 公开符号，无逻辑）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|----------|----------|
| `summarizer_project_map.md` | project_map 协调：模块划分提示词、竖线文本解析、文件展开、重命名迁移、02/04 段纯程序渲染、01/03 段提示词 | `get_project_map_prompt` / `submit_project_map` / `_parse_modules_text` / `_expand_module_files` / `_migrate_renamed_module_caches` / `render_structure_segment` / `render_dependencies_segment` / `get_identity_segment_prompt` / `get_architecture_segment_prompt` |
| `summarizer_module.md` | 模块摘要协调：单模块提示词、摘要落盘、模块 hash、prompt 构建、docstring 注入 | `get_module_prompt` / `save_module_summary` / `_compute_module_hash` / `_build_module_prompt` |

## 模块概述

summarizer 是 CodeSense 的摘要协调层，把 data 层（CodeGraph DB 查询）的结构数据组合成 LLM prompt 文本，并解析外部 Agent 返回、渲染 Markdown 段落，本身**不直接调 LLM**（LLM 调用由外部 tools 层 Agent 完成）。上游被 tools 层多个工具调用（`submit_project_map_tool` / `get_module_prompt_tool` / `save_module_summary_tool` / `get_modules_segment_prompt_tool` / `get_identity_segment_prompt_tool` / `project_map` 等）。下游依赖 data（大量 import：`aggregate` / `architecture` / `db` / `docstrings` / `files` / `modules` / `project_info` / `ref_docs` / `structure` / `hashes`）、cache（读写 `.codesense/`）、errors（`InvalidArgumentError`）。

## 架构简析

分层结构：`data 查询（DB/aggregate/architecture/docstrings）→ prompt 构建/响应解析（_build_*_prompt / _parse_modules_text）→ cache 读写（modules_index / segment / module hash）→ Markdown 渲染（render_*_segment / _render_*_markdown）`。

核心文件 `summarizer.py` 单文件承载全部协调逻辑。数据流：DB 查询产出目录符号/依赖/中心度/拓扑层 → `_build_project_map_prompt` 拼提示词文本返回给 tools 层 → 外部 Agent 回竖线文本 → `submit_project_map` 经 `_parse_modules_text`（fuzzy 校正/去重/冲突丢弃）+ `_expand_module_files`（父子目录排除）解析为结构化模块 → 写 `modules_index.json` + 03/04 段 + `render_project_map`。

**关键架构事实：summarizer 不直接调 LLM。** 它只产出 prompt 文本（`get_*_prompt` 系列返回 str）+ 解析 Agent 返回的文本（`submit_project_map` / `save_module_summary` 接收已生成内容）+ 渲染 Markdown（`render_*_segment` 纯程序）。LLM 调用由外部 tools 层 Agent 完成，summarizer 与 LLM 解耦。

## 上下游关系

### 上游（调用 summarizer 的模块）

| 调用方模块 | 调用场景 | 关键符号 | confidence |
|-----------|----------|----------|-----------|
| tools | `submit_project_map_tool` 调 `submit_project_map` 解析模块划分 | `submit_project_map` | extracted |
| tools | `get_module_prompt_tool` 调 `get_module_prompt` 取单模块提示词 | `get_module_prompt` | extracted |
| tools | `save_module_summary_tool` 调 `save_module_summary` 落盘摘要 | `save_module_summary` | extracted |
| tools | `get_modules_segment_prompt_tool` 调 `get_project_map_prompt` 取划分提示词 | `get_project_map_prompt` | extracted |
| tools | `get_identity_segment_prompt_tool` 调 `get_identity_segment_prompt` 取 01 段提示词 | `get_identity_segment_prompt` | extracted |
| tools | `project_map` 工具调 `render_structure_segment` 渲染 02 段 | `render_structure_segment` | extracted |

### 下游（summarizer 依赖的模块）

| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|----------|----------|-----------|
| data | DB 查询、目录符号/依赖聚合、拓扑层/中心度/环检测、docstring 提取、ref_docs 段、hash 计算 | `CodeGraphDB` / `list_modules` / `module_dependencies` / `directory_dependencies` / `directory_symbols` / `compute_centrality` / `topological_layers` / `find_cycles` / `cross_dir_public_api` / `external_dependencies_by_dir` / `extract_file_docstring` / `extract_symbol_docstrings` / `ref_docs_prompt_section` / `compute_architecture_hash` / `compute_dependencies_hash` | extracted |
| cache | 读写 `.codesense/`：modules_index、segment、module hash、safe_key、db_hash、render_project_map | `read_modules_index` / `write_modules_index` / `write_segment` / `is_segment_valid` / `write_module` / `read_module_hashes` / `write_module_hash` / `safe_key` / `db_hash` / `render_project_map` | extracted |
| errors | 参数校验失败抛 `InvalidArgumentError` | `InvalidArgumentError` | extracted |
