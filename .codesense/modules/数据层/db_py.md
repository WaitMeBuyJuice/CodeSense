## 文件概述

`db.py` 是 CodeGraph SQLite 数据库（`<project>/.codegraph/codegraph.db`）的只读访问边界，定义 `CodeGraphDB` 类及 `FileRow`/`NodeRow`/`EdgeRow` 三个不可变数据行结构。它通过 `mode=ro` URI 强制只读连接，向上层提供文件、节点、边的迭代与查询接口，是数据层（第0层基础层）的核心文件，被摘要协调层与工具实现层广泛依赖。

## 对外接口

### 常量

- `DB_RELATIVE_PATH = Path(".codegraph") / "codegraph.db"`：数据库相对项目根的路径常量。

### 数据结构（`@dataclass(frozen=True)`）

- `FileRow`：文件行，字段 `path: str`、`language: str`、`size: int`、`node_count: int`。
- `NodeRow`：节点行，字段 `id: str`、`kind: str`（file/import/function/class/method/variable 等）、`name: str`、`qualified_name: str`、`file_path: str`、`language: str`、`start_line: int`、`end_line: int`、`signature: str | None`。
- `EdgeRow`：边行，字段 `source: str`（节点 id）、`target: str`（节点 id）、`kind: str`（contains/imports/calls 等）、`line: int | None`。

### `CodeGraphDB` 类

只读封装 `<project>/.codegraph/codegraph.db`，支持上下文管理器用法。

- `__init__(self, project_root: str | Path) -> None`：解析项目根，定位数据库文件；不存在则抛 `FileNotFoundError`（提示先运行 `codegraph init -i`）；以 `file:...?mode=ro` URI 建立只读连接，`row_factory` 设为 `sqlite3.Row`。
- `close(self) -> None`：关闭数据库连接。
- `__enter__(self) -> CodeGraphDB`：返回自身。
- `__exit__(self, exc_type: object, exc: object, tb: object) -> None`：调用 `close()`。
- `iter_files(self) -> Iterator[FileRow]`：按 `path` 排序迭代所有文件行。
- `iter_nodes(self, kinds: Iterable[str] | None = None) -> Iterator[NodeRow]`：迭代节点行；`kinds` 非空时按 `kind IN (...)` 过滤，结果按 `file_path, start_line` 排序。
- `iter_edges(self, kinds: Iterable[str] | None = None) -> Iterator[EdgeRow]`：迭代边行；`kinds` 非空时按 `kind IN (...)` 过滤。
- `get_node(self, node_id: str) -> NodeRow | None`：按 `id` 精确查询单个节点，未命中返回 `None`。
- `stats(self) -> dict[str, object]`：返回统计字典，含 `files`、`nodes`、`edges` 总数及 `nodes_by_kind`、`edges_by_kind` 两个按类型分组的计数字典。

## 跨模块依赖

### 出向依赖

仅依赖 Python 标准库：`sqlite3`、`collections.abc`（`Iterable`/`Iterator`）、`dataclasses`、`pathlib.Path`。无项目内出向依赖。

### 入向依赖（被以下文件 import）

- 数据层内部：`src/codesense_v1/data/__init__.py`、`aggregate.py`、`architecture.py`、`docstrings.py`、`files.py`、`modules.py`、`project_info.py`。
- 摘要协调层：`src/codesense_v1/summarizer/summarizer.py`。
- 工具实现层：`src/codesense_v1/tools/explore_module.py`、`get_identity_segment_prompt.py`、`project_map.py`、`save_project_map_segment.py`。
- 脚本与测试：`scripts/validate_dir_deps.py`、`tests/test_data_db.py`、`tests/test_data_modules.py`。

## 典型调用链

- `summarizer/summarizer.py` → `CodeGraphDB(project_root)` → `iter_nodes()` / `iter_edges()`：摘要协调层读取节点与边构建代码图上下文。
- `tools/project_map.py` → `CodeGraphDB` → `iter_files()` / `stats()`：生成项目地图时枚举文件并取统计信息。
- `tools/explore_module.py` → `CodeGraphDB` → `get_node()` / `iter_nodes(kinds=...)`：按节点 id 或类型查询模块内符号。
- `data/modules.py` / `data/files.py` → `CodeGraphDB` → `iter_nodes()` / `iter_files()`：数据层其他聚合模块基于此基础封装做进一步加工。