---
repo: CodeSense_V1
generated_at: 2026-06-29
codemap: available
scan_mode: depth-1
module_count: 7
---

# CodeSense_V1 知识库全局索引

> 本文件由 code-index-builder 生成。模块符号索引由 Codemap MCP 实时提供（find_symbol / search_code / get_symbol_detail），此处仅记录模块清单与依赖关系。

## 模块清单

| module_id | architectural_role | src_path | kb_path | 子文档数 |
|-----------|-------------------|----------|---------|---------|
| `server` | MCP 入口层 | `src/codesense_v1/server` | `.codemaker/codeindex/server` | 1 |
| `registry` | 工具注册与分发层 | `src/codesense_v1/registry` | `.codemaker/codeindex/registry` | 1 |
| `tools` | MCP 工具层 | `src/codesense_v1/tools` | `.codemaker/codeindex/tools` | 2 |
| `summarizer` | 摘要协调层 | `src/codesense_v1/summarizer` | `.codemaker/codeindex/summarizer` | 2 |
| `data` | CodeGraph 数据查询层 | `src/codesense_v1/data` | `.codemaker/codeindex/data` | 3 |
| `cache` | 缓存读写层 | `src/codesense_v1/cache` | `.codemaker/codeindex/cache` | 1 |
| `errors` | 错误类型体系 | `src/codesense_v1/errors.py` | `.codemaker/codeindex/errors` | 1 |

## 模块间依赖关系

> extracted = 静态分析可信（源码 import / cross_module_hints）；inferred = Agent 推断待复核

| 模块 | 上游（谁依赖我） | 下游（我依赖谁） |
|------|----------------|----------------|
| `server` | （外部 CodeMaker Agent spawn） | registry(extracted), tools(extracted), cache(inferred), errors(inferred) |
| `registry` | server(extracted), tools(extracted) | errors(extracted) |
| `tools` | server(extracted, import 触发注册), registry(extracted, dispatch 调 handler) | data(extracted), summarizer(extracted), cache(extracted), errors(extracted), registry(extracted) |
| `summarizer` | tools(extracted) | data(extracted), cache(extracted), errors(extracted) |
| `data` | tools(extracted), summarizer(extracted) | errors(extracted, 同层基础设施) |
| `cache` | tools(extracted), summarizer(extracted) | （无，叶子模块） |
| `errors` | registry, tools, summarizer, data 等(extracted) | （无，叶子模块） |

## 全局文档清单

| 文档 | 路径 | 用途 |
|------|------|------|
| 项目概览 | `.codemaker/codeindex/_project_overview.md` | 仓库定位/技术栈/目录结构/环境变量 |
| 系统架构 | `.codemaker/codeindex/_architecture.md` | 层次划分/边界规则/数据流/约束/接口规范 |
| 核心子系统 | `.codemaker/codeindex/_core_systems.md` | 子系统列表/关键流程/设计取舍 |
| 目录 | `.codemaker/codeindex/_catalog.md` | 模块名→职责→文档路径导航 |
| 概念索引 | `.codemaker/codeindex/_concept_index.md` | 业务关键词→子文档速查（RAG 入口） |
| 全局索引 | `.codemaker/codeindex/_index.md` | 本文件 |

## Codemap 状态

- ✅ 可用：44 文件，900 符号，2075 调用边
- 符号索引（classes/functions/methods）由 Codemap MCP 实时提供，知识库文档不重复列举
- 知识库沉淀：业务规则、架构约束、模块职责、实现约束清单、典型调用链
