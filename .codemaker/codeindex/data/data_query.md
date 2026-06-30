---
entity_names:
  constants:
    - name: DB_RELATIVE_PATH
      value: "Path(\".codegraph\") / \"codegraph.db\""
      source: src/codesense_v1/data/db.py
    - name: EXTERNAL_PREFIX
      value: "\"external::\""
      source: src/codesense_v1/data/modules.py
    - name: _STRIP_EXT_LANGS
      value: "{\"typescript\": (\".d.ts\", \".ts\", \".tsx\"), \"javascript\": (\".js\", \".jsx\", \".mjs\", \".cjs\")}"
      source: src/codesense_v1/data/modules.py
    - name: _CODESENSE_IGNORE_FILE
      value: "\".codesense/.codesenseignore\""
      source: src/codesense_v1/data/files.py
retrieval_hints:
  - "正向疑问句：怎么从 CodeGraph DB 查所有文件/节点/边？"
  - "正向疑问句：文件级依赖边怎么提取？内部依赖与外部依赖如何区分？"
  - "正向疑问句：怎么把文件依赖按目录或包聚合？"
  - "⚠️ 反向排除：若找模块摘要渲染或 LLM 调用，不在这里，在 summarizer；data 只产结构化数据不调 LLM"
  - "⚠️ 反向排除：若找架构拓扑分层/环检测/中心度，不在本子文档，在 data_analysis.md（architecture.py）"
  - "架构归属句：新增 DB 查询函数必须放 data/ 对应子文件，不可在 tools 层直连 sqlite；所有 SQL 只允许出现在 db.py"
  - "本模块也叫 Data Layer / 数据查询层"
architectural_role: "CodeGraph 数据查询层"
---

# data_query — DB 只读封装 + 文件/模块/目录聚合查询

覆盖：`db.py` / `files.py` / `modules.py` / `aggregate.py`。

## 对外接口

data 对外接口由 `__init__.py` 聚合导出。本子文档相关函数与类：

| 函数/类 | 用途 | 所在文件 |
|---|---|---|
| `CodeGraphDB` | 只读 SQLite 连接（上下文管理器），`iter_files`/`iter_nodes(kinds=)`/`iter_edges(kinds=)`/`get_node(id)`/`stats()` | db.py |
| `FileRow` / `NodeRow` / `EdgeRow` | frozen dataclass 行模型 | db.py |
| `list_files(db)` | 平铺文件列表（过滤 gitignore + .codesenseignore） | files.py |
| `directory_tree(db)` | 层级目录树 → `DirectoryNode` | files.py |
| `DirectoryNode` | 目录树节点（`name`/`path`/`files`/`subdirs`，含 `to_dict()`） | files.py |
| `list_modules(db)` | 每个文件 → `Module`（id=POSIX 路径，package_id=包/目录） | modules.py |
| `module_dependencies(db, *, include_external, include_calls, include_imports)` | 文件级依赖边 → `list[ModuleEdge]` | modules.py |
| `Module` / `ModuleEdge` | frozen dataclass（ModuleEdge 含 `is_external`） | modules.py |
| `to_file_dependency_dict(edges)` | 文件级视图 `{file: {imports:[], calls:[]}}`（外部加 `external::` 前缀） | modules.py |
| `to_package_dependency_dict(edges, modules, *, include_self_loops)` | 包/目录级聚合视图 | modules.py |
| `directory_dependencies(edges, modules, *, max_depth, include_external, include_self_loops)` | 按文件系统目录路径聚合依赖 dict | aggregate.py |
| `directory_edges(...)` | `directory_dependencies` 的扁平 `(src, tgt, kind)` 列表变体 | aggregate.py |
| `directory_symbols(db, *, max_depth, kinds, max_per_dir)` | 按目录聚合符号列表 `{dir: [{name, kind, file}]}` | aggregate.py |

## 跨模块依赖

外部依赖（data → 其他模块）：

| 依赖 | 用途 |
|---|---|
| 标准库 `sqlite3`/`dataclasses`/`pathlib`/`collections.abc` | db.py 基础 |
| 第三方 `pathspec` | files.py 合并 `.gitignore` + `.codesense/.codesenseignore` 为 PathSpec |
| `codesense_v1.data.db` | files/modules/aggregate/docstrings 均依赖（唯一 SQLite 边界） |
| `codesense_v1.data.modules` | aggregate 依赖 `EXTERNAL_PREFIX`/`Module`/`ModuleEdge` |

反向调用方（谁调用了本子文档的函数）：

| 调用方 | 调用的 data 函数 |
|---|---|
| `tools/project_map.py` | `list_modules`/`module_dependencies`/`CodeGraphDB`/`directory_tree` |
| `tools/save_project_map_segment.py` | `list_modules`/`module_dependencies`/`CodeGraphDB`/`directory_tree` |
| `summarizer/summarizer.py` | `list_modules`/`module_dependencies`/`directory_dependencies`/`directory_symbols`/`CodeGraphDB`/`DirectoryNode` |

## 典型调用链

1. `project_map tool → list_modules(db) → module_dependencies(db) → directory_dependencies(edges, modules)`（生成目录级依赖视图供 segment 渲染）。
2. `summarizer → directory_symbols(db, max_per_dir=50) → db.iter_nodes(kinds=("function","class","method"))`（按目录聚合符号喂给 LLM prompt，防 token 超限）。
3. `project_map tool → directory_tree(db) → db.iter_files()`（构建层级目录树，过滤 ignore 规则）。

## 实现约束清单

| 类型 | 约束 |
|---|---|
| 设计决策 | **所有 SQL 只允许出现在 `db.py`**；schema 变更时只需改一处。其余子文件通过 `CodeGraphDB` 方法访问数据。 |
| 设计决策 | `CodeGraphDB` 用 `file:...?mode=ro` URI 强制只读，防止意外写入 CodeGraph DB。 |
| 设计决策 | 文件级 ID = POSIX 路径字符串（`/` 分隔，跨平台可比较）；私有 `resolve_id` 用于 import 匹配（Python 点号名，TS/JS 去扩展名路径）。 |
| 设计决策 | 外部依赖在 dict 视图中加 `external::` 前缀，视觉上与内部路径无歧义区分。 |
| 设计决策 | `module_dependencies` 内外依赖判断：优先看 `tgt_node.kind != "import"`（新版 CodeGraph 已解析内部 import 到真实文件）；旧版回退 name 匹配（`_resolve_internal_import`）。 |
| 设计决策 | calls 边只信任 target 为 callable（function/method/class）且 source 为 callable 或同文件 file 节点；跨文件 calls 边需已有对应 imports 边才采信（防 CodeGraph 误解析同名方法产生假边）。 |
| 设计决策 | `to_package_dependency_dict` 默认 `include_self_loops=False`（同包内循环不算包间依赖）。 |
| 必须实现的函数 | `CodeGraphDB.iter_files`/`iter_nodes`/`iter_edges`/`get_node`/`stats`（流式 Iterator，按 path/file_path 排序）。 |
| 阈值/默认值 | `directory_symbols` 的 `max_per_dir` 默认 `None`（不限），summarizer 调用时传 `50` 防 token 超限；`kinds` 默认 `("function","class","method")`。 |
| 错误处理 | DB 文件不存在 → `CodeGraphDB.__init__` 抛 `FileNotFoundError`；SQLite 查询出错向上传播 `sqlite3.OperationalError`；其余不兜底。 |
| 数据类 | `FileRow`/`NodeRow`/`EdgeRow`/`Module`/`ModuleEdge` 均 `frozen=True`；`DirectoryNode` 非 frozen（可变 subdirs）。 |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/data.md`、`doc/Week2/tasks/data.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

- `doc/Week2/design/data.md`：data 层定位为 L4 基础设施（与 schemas/errors 平级），只读 SQLite 不写入、不注册 MCP 工具、不依赖 registry/tools/server。子模块职责表与本文一致（db/files/modules/aggregate）。关键设计决策：文件级 ID 用 POSIX 路径、resolve_id 私有匹配 import、`external::` 前缀区分内外依赖、SQLite 只读 `mode=ro`、单一 SQLite 边界（所有 SQL 只在 db.py）。
- `doc/Week2/tasks/data.md`：T-D-1~T-D-4 迁移 db/files/modules/aggregate 已完成（✅），验收要求 `FileRow`/`NodeRow`/`EdgeRow` 为 `frozen=True`、无旧式类型注解、mypy strict + ruff 零警告。`_resolve_id`/`_resolve_internal_import` 算法 1:1 复刻。
- `doc/Week5/week5_handoff.md`：Week5 前置改动新增 `data/aggregate.py` 的 `directory_symbols` 函数（按目录聚合符号 `name/kind/file`，给 `project_map_summary` 的 LLM prompt 用，`max_per_dir=50` 防 token 超限）。
