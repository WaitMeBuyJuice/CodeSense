---
module_id: data
architectural_role: "数据访问与架构分析层"
world_model_hints:
  - "位于 summarizer 和 tools 之下，封装 CodeGraph SQLite 数据库的只读查询"
  - "所有子模块均通过 CodeGraphDB 访问 .codegraph/codegraph.db，不直接操作数据库文件"
  - "architecture 子模块基于 modules 的 ModuleEdge 做图算法分析，纯语言无关"
upstream_modules:
  - module: summarizer
    confidence: extracted
  - module: tools
    confidence: extracted
downstream_modules:
  - module: SQLite DB (codegraph.db)
    confidence: extracted
---

## Files

### 源代码路径
- `src/codesense_v1/data/`（7 个文件）

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/data/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/data/data_db.md`
- `.codemaker/codeindex/src/codesense_v1/data/data_modules.md`
- `.codemaker/codeindex/src/codesense_v1/data/data_architecture.md`
- `.codemaker/codeindex/src/codesense_v1/data/data_aggregate.md`
- `.codemaker/codeindex/src/codesense_v1/data/data_docstrings.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `data_db.md` | DB 访问封装 | CodeGraphDB, FileRow, NodeRow, EdgeRow |
| `data_modules.md` | 文件级依赖模型 | Module, ModuleEdge, list_modules, module_dependencies |
| `data_architecture.md` | 架构分析算法 | compute_centrality, find_cycles, topological_layers, cross_dir_public_api, ArchitectureFeatures |
| `data_aggregate.md` | 目录级聚合 + 文件树 | directory_dependencies, directory_symbols, list_files, directory_tree |
| `data_docstrings.md` | 文档提取 + 参考文档 | extract_file_docstring, extract_symbol_docstrings, discover_ref_docs, ref_docs_prompt_section |

## 模块概述

本模块是 CodeSense 的数据访问与架构分析层，封装对 CodeGraph SQLite 数据库（`.codegraph/codegraph.db`）的只读查询，并在文件级依赖图之上提供语言无关的架构分析算法（中心性、循环检测、拓扑分层、公开 API 提取）。

上游：summarizer（消费全部分析结果生成模块摘要）、tools（explore_module 直接使用 CodeGraphDB）。

下游：CodeGraph 的 SQLite 数据库（只读访问）。

核心数据流：`SQLite → CodeGraphDB → Module/ModuleEdge → 聚合/图算法 → 供 summarizer 消费`

## 架构简析

7 个文件构成分层结构：

1. **db.py** — 最底层，封装 SQLite 只读连接，定义 `FileRow`/`NodeRow`/`EdgeRow` 三个数据行类
2. **modules.py** — 依赖 db，将节点/边映射为文件级 `Module`/`ModuleEdge`，提供 `module_dependencies` 核心函数
3. **architecture.py** — 依赖 modules，在 `ModuleEdge` 列表上执行图算法（Tarjan SCC、拓扑排序、fan-in/fan-out）
4. **aggregate.py** — 依赖 modules/db，将文件级边聚合到目录级，提供目录级依赖和符号列表
5. **files.py** — 依赖 db，提供文件列表和目录树视图
6. **docstrings.py** — 唯一做文件 I/O 的子模块（直接读取源码），从源文件提取 docstring
7. **ref_docs.py** — 独立模块，扫描项目参考文档目录

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：summarizer（消费全部分析结果）、tools/explore_module（直接使用 CodeGraphDB）
- **下游**：CodeGraph SQLite 数据库（`.codegraph/codegraph.db`，只读）
