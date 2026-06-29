## 文件概述
该文件是 CodeGraph SQLite 数据库的只读封装层，提供对 `.codegraph/codegraph.db` 的统一访问入口。它定义了文件行、节点行、边行三个数据类，以及 `CodeGraphDB` 上下文管理器类——所有数据库查询都集中在此，若 schema 变更只需修改这一个文件。

## 对外接口
- `FileRow(path, language, size, node_count)` — 文件行数据类，包含文件路径、语言、大小和节点数。
- `NodeRow(id, kind, name, qualified_name, file_path, language, start_line, end_line, signature)` — 节点行数据类，表示一个代码符号（函数、类、变量等），含位置和签名信息。
- `EdgeRow(source, target, kind, line)` — 边行数据类，表示节点间的关系（包含、导入、调用等），含源/目标节点 ID 和行号。
- `CodeGraphDB(project_root: str | Path) -> None` — 以只读模式打开项目下的 CodeGraph 数据库，数据库不存在时抛出 `FileNotFoundError`。
- `CodeGraphDB.close() -> None` — 关闭数据库连接。
- `CodeGraphDB.__enter__() -> CodeGraphDB` — 上下文管理器入口，返回自身。
- `CodeGraphDB.__exit__(exc_type, exc, tb) -> None` — 上下文管理器出口，自动关闭连接。
- `CodeGraphDB.iter_files() -> Iterator[FileRow]` — 按路径排序迭代所有文件行。
- `CodeGraphDB.iter_nodes(kinds=None) -> Iterator[NodeRow]` — 迭代节点，可按类型过滤；按文件路径和起始行排序。
- `CodeGraphDB.iter_edges(kinds=None) -> Iterator[EdgeRow]` — 迭代边，可按类型过滤。
- `CodeGraphDB.get_node(node_id: str) -> NodeRow | None` — 按 ID 查询单个节点，不存在返回 `None`。
- `CodeGraphDB.stats() -> dict[str, object]` — 返回数据库统计信息（文件数、节点数、边数、各类型计数）。
- `DB_RELATIVE_PATH` — 常量 `Path(".codegraph") / "codegraph.db"`，表示数据库文件相对路径。

## 跨模块依赖
**出向：**
- 标准库 `sqlite3`、`collections.abc`（`Iterable`/`Iterator`）、`dataclasses`、`pathlib`

**入向：**
- `src/codesense_v1/data/__init__.py`
- `src/codesense_v1/data/aggregate.py`
- `src/codesense_v1/data/architecture.py`
- `src/codesense_v1/data/docstrings.py`
- `src/codesense_v1/data/files.py`
- `src/codesense_v1/data/modules.py`
- `src/codesense_v1/data/project_info.py`
- `src/codesense_v1/summarizer/summarizer.py`
- `src/codesense_v1/tools/explore_module.py`
- `src/codesense_v1/tools/project_map.py`
- `src/codesense_v1/tools/get_identity_segment_prompt.py`
- `src/codesense_v1/tools/save_project_map_segment.py`
- `tests/test_data_db.py`
- `tests/test_data_modules.py`

## 典型调用链
- `CodeGraphDB.__init__` → `sqlite3.connect` (以 `mode=ro` URI 打开只读连接)
- `CodeGraphDB.iter_nodes` / `iter_edges` → `sqlite3.Connection.execute` → 逐行构造 `NodeRow` / `EdgeRow`
- `data` 子模块各文件（如 `modules.py`、`architecture.py`）→ `CodeGraphDB.iter_nodes/iter_edges/stats` → 获取结构化数据后进行聚合分析