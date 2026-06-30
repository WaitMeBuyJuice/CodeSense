---
module_id: data
architectural_role: "CodeGraph 数据查询层"
world_model_hints:
  - "基础设施层，数据源头，被 tools/summarizer 查询"
upstream_modules:
  - module: errors
    confidence: extracted
downstream_modules:
  - module: tools
    confidence: extracted
  - module: summarizer
    confidence: extracted
---

# data 模块概览

## Files

源代码（`src/codesense_v1/data/`，10 个源文件 + `__init__.py`）：

| 文件 | 职责 |
|---|---|
| `__init__.py` | 聚合导出全部公开 API（`__all__` 列表） |
| `db.py` | SQLite 只读封装 `CodeGraphDB` + `FileRow`/`NodeRow`/`EdgeRow` |
| `files.py` | 文件平铺列表与层级目录树 |
| `modules.py` | 文件级依赖边提取 + 文件/包级两种视图 |
| `aggregate.py` | 按目录路径聚合依赖与符号 |
| `architecture.py` | 架构分析（拓扑分层/环检测/中心度/公开 API） |
| `structure.py` | 顶层目录分类与自适应目录树深度 |
| `hashes.py` | 4 个内容指纹（segment 缓存失效判断） |
| `project_info.py` | 项目身份信息收集（README/配置/文档字符串） |
| `docstrings.py` | 多语言文档字符串提取（data 层唯一做文件 I/O 的模块） |
| `ref_docs.py` | 参考文档发现与 prompt 段落生成 |

知识库文档：`_overview.md`、`data_query.md`、`data_analysis.md`、`data_context.md`（本目录）。符号索引由 Codemap 提供。

## 子文档速览

| 子文档 | 覆盖文件 | 关键实体 |
|---|---|---|
| `data_query.md` | db.py / files.py / modules.py / aggregate.py | `CodeGraphDB`、`FileRow`、`NodeRow`、`EdgeRow`、`list_files`、`directory_tree`、`DirectoryNode`、`Module`、`ModuleEdge`、`list_modules`、`module_dependencies`、`to_file_dependency_dict`、`to_package_dependency_dict`、`directory_dependencies`、`directory_symbols` |
| `data_analysis.md` | architecture.py / structure.py / hashes.py | `DirCentrality`、`ArchitectureFeatures`、`topological_layers`、`find_cycles`、`compute_centrality`、`cross_dir_public_api`、`external_dependencies_by_dir`、`architecture_features`、`TopLevelDir`、`classify_top_dirs`、`auxiliary_category`、`compute_tree_max_depth`、`compute_identity_hash`、`compute_structure_hash`、`compute_architecture_hash`、`compute_dependencies_hash` |
| `data_context.md` | project_info.py / docstrings.py / ref_docs.py | `IdentitySource`、`collect_identity_sources`、`extract_tech_stack_hint`、`read_readme`、`extract_file_docstring`、`extract_symbol_docstrings`、`is_enabled`、`ref_docs_prompt_section`、`discover_ref_docs` |

## 模块概述

- **业务定位**：data 是 CodeGraph SQLite 知识图谱（`<project>/.codegraph/codegraph.db`）的只读查询层，把图结构（files/nodes/edges 表）加工成文件清单、模块依赖边、目录聚合、架构指标、内容指纹、项目身份信息等结构化数据，供上层 tools/summarizer 消费。除 `docstrings.py`/`project_info.py`/`ref_docs.py` 读源文件与配置外，其余子文件严格只读 SQLite。
- **上游**：仅依赖 `errors`（实际 data 内部源码未直接 import errors，errors 为同层基础设施；data 主要依赖标准库 `sqlite3`/`dataclasses`/`pathlib`/`hashlib`/`json`/`re`/`os` 及第三方 `pathspec`）。数据源是外部 CodeGraph 生成的 DB 文件。
- **下游**：`tools`（`project_map`/`save_project_map_segment`/`get_identity_segment_prompt`/`explore_module` 直接 import data 多个函数与 `CodeGraphDB`）、`summarizer`（大量 import data.* 用于 project_map/module segment 渲染）。

## 架构简析

分层结构：`CodeGraphDB 只读封装 → files/modules 聚合 → architecture/structure 分析 → hashes 指纹`；核心文件 `db.py`（唯一 SQLite 边界）、`modules.py`（依赖边提取核心算法）、`architecture.py`（图算法 Tarjan SCC/拓扑分层）、`hashes.py`（缓存失效判断）。

数据流：`CodeGraphDB(project_root)` 打开只读连接 → `iter_files/iter_nodes/iter_edges` 流式产出行 → `files/modules/aggregate/architecture` 在内存中加工 → `hashes` 对结构数据算 sha256 → tools/summarizer 消费。`docstrings`/`project_info`/`ref_docs` 旁路读源文件与配置，补充身份/文档上下文给 prompt。

## 上下游关系

- **被谁调用**（反向依赖，extracted）：
  - `tools/project_map.py`：import `classify_top_dirs`/`collect_identity_sources`/`compute_*_hash`/`find_cycles`/`list_modules`/`module_dependencies`/`topological_layers`/`compute_tree_max_depth`/`CodeGraphDB`/`directory_tree`。
  - `tools/save_project_map_segment.py`：import `classify_top_dirs`/`collect_identity_sources`/`compute_*_hash`/`find_cycles`/`list_modules`/`module_dependencies`/`CodeGraphDB`/`directory_tree`。
  - `tools/get_identity_segment_prompt.py`：import `collect_identity_sources`/`extract_tech_stack_hint`/`CodeGraphDB`。
  - `tools/explore_module.py`：import `CodeGraphDB`。
  - `summarizer/summarizer.py`：import `directory_dependencies`/`directory_symbols`/`architecture.*`/`CodeGraphDB`/`docstrings.*`/`DirectoryNode`/`list_modules`/`module_dependencies`/`IdentitySource`/`ref_docs_prompt_section`/`structure.*`/`hashes.compute_architecture_hash`/`hashes.compute_dependencies_hash`。
- **调用谁**（正向依赖）：data 内部子文件互相依赖（`files`/`modules`/`aggregate`/`architecture`/`docstrings`/`project_info`/`hashes` 均依赖 `db`；`aggregate`/`architecture` 依赖 `modules`；`hashes` 依赖 `modules`/`project_info`/`structure`；`project_info` 依赖 `docstrings`）。对外仅依赖标准库与 `pathspec`，不依赖 `registry`/`tools`/`server`/`summarizer`（避免反向依赖）。
