---
entity_names:
  constants:
    - name: "DB_RELATIVE_PATH"
      value: "Path(\".codegraph\") / \"codegraph.db\""
      source: "src/codesense_v1/data/db.py"
  classes:
    - name: "CodeGraphDB"
      source: "src/codesense_v1/data/db.py"
    - name: "FileRow"
      source: "src/codesense_v1/data/db.py"
    - name: "NodeRow"
      source: "src/codesense_v1/data/db.py"
    - name: "EdgeRow"
      source: "src/codesense_v1/data/db.py"
retrieval_hints:
  - "CodeGraphDB 如何打开数据库？必须用 context manager 吗？"
  - "FileRow / NodeRow / EdgeRow 各有哪些字段？"
  - "iter_nodes 和 iter_edges 支持按 kind 过滤吗？"
  - "stats() 返回什么统计信息？"
  - "DB 路径是硬编码的吗？如何定位 codegraph.db？"
architectural_role: "CodeGraph SQLite 数据库只读封装层，是 data 模块的唯一数据库访问边界"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部函数调用。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：无（仅标准库 `sqlite3`、`pathlib`、`dataclasses`）

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `data/modules` | 构建 Module 列表和 ModuleEdge 列表 | `CodeGraphDB.iter_files`, `CodeGraphDB.iter_nodes`, `CodeGraphDB.iter_edges` |
| `data/architecture` | 跨目录公开 API 查询 | `CodeGraphDB.iter_nodes`, `CodeGraphDB.iter_edges` |
| `data/aggregate` | 目录级符号聚合 | `CodeGraphDB.iter_nodes` |
| `data/files` | 文件列表和目录树 | `CodeGraphDB.iter_files` |
| `data/docstrings` | 获取节点信息（仅引用 `NodeRow` 类型） | `NodeRow` |
| `tools/explore_module` | 直接查询数据库以探索模块 | `CodeGraphDB` |
| `summarizer` | 全量架构分析入口 | `CodeGraphDB` |

## 典型调用链

### 打开数据库并遍历文件
```
summarizer / tools
  → CodeGraphDB(project_root)         ← 自动定位 .codegraph/codegraph.db
    → __init__ 通过 sqlite3.connect(uri, uri=True) 以 mode=ro 打开
  → db.iter_files() → Iterator[FileRow]
  → db.iter_nodes(kinds=("function","class")) → Iterator[NodeRow]
  → db.iter_edges(kinds=("imports","calls")) → Iterator[EdgeRow]
```

### 获取统计信息
```
summarizer
  → CodeGraphDB(project_root) as db
  → db.stats() → {"files": N, "nodes": N, "edges": N, "nodes_by_kind": {...}, "edges_by_kind": {...}}
```

## 数据行定义

### FileRow
| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 文件路径（相对于项目根目录） |
| `language` | `str` | 编程语言 |
| `size` | `int` | 文件大小（字节） |
| `node_count` | `int` | 文件包含的节点数量 |

### NodeRow
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 节点唯一标识符 |
| `kind` | `str` | 节点类型：`file`、`import`、`function`、`class`、`method`、`variable` 等 |
| `name` | `str` | 节点简单名称 |
| `qualified_name` | `str` | 节点完全限定名 |
| `file_path` | `str` | 节点所属文件路径 |
| `language` | `str` | 编程语言 |
| `start_line` | `int` | 起始行号（1-based） |
| `end_line` | `int` | 结束行号（1-based） |
| `signature` | `str \| None` | 函数/方法签名，无签名则为 `None` |

### EdgeRow
| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `str` | 源节点 ID |
| `target` | `str` | 目标节点 ID |
| `kind` | `str` | 边类型：`contains`、`imports`、`calls` 等 |
| `line` | `int \| None` | 边在源码中的行号，无则为 `None` |

## CodeGraphDB 方法一览

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `__init__(project_root)` | — | 根据项目根定位 `.codegraph/codegraph.db`，以只读模式打开 |
| `close()` | — | 关闭数据库连接 |
| `__enter__()` / `__exit__()` | — | Context manager 支持，确保连接关闭 |
| `iter_files()` | `Iterator[FileRow]` | 遍历全部文件，按 `path` 排序 |
| `iter_nodes(kinds?)` | `Iterator[NodeRow]` | 遍历节点，可选按 `kind` 过滤（如 `("function","class")`） |
| `iter_edges(kinds?)` | `Iterator[EdgeRow]` | 遍历边，可选按 `kind` 过滤（如 `("imports","calls")`） |
| `get_node(node_id)` | `NodeRow \| None` | 按 ID 查询单个节点，不存在返回 `None` |
| `stats()` | `dict[str, object]` | 返回数据库统计信息（文件数/节点数/边数/按 kind 分布） |

## 实现约束清单

### 必须定义的常量/枚举

| 标识符 | 值 | 所在文件 | 说明 |
|-------|----|---------|------|
| `DB_RELATIVE_PATH` | `Path(".codegraph") / "codegraph.db"` | `db.py` | 数据库相对路径，不可硬编码为绝对路径——通过 `project_root` 拼接 |

### 数据库访问契约

| 约束 | 说明 |
|------|------|
| 只读模式 | 通过 `sqlite3.connect("file:...?mode=ro", uri=True)` 打开，防止意外写入 |
| Context Manager | 必须使用 `with CodeGraphDB(root) as db:` 确保连接关闭，不可手动管理连接 |
| Row Factory | `row_factory = sqlite3.Row`，所有查询以列名访问，不可按索引访问 |
| DB 路径解析 | `self.db_path = self.project_root.resolve() / DB_RELATIVE_PATH`，不可硬编码 |
| 文件不存在 | DB 不存在时抛出 `FileNotFoundError` 并提示运行 `codegraph init -i` |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| 数据行类型 | `@dataclass(frozen=True)` | 普通类 / TypedDict | 不可变、可哈希、IDE 友好 |
| 过滤参数 | `Iterable[str] | None`（可选） | 字符串拼接 | 支持单次查询多种 kind，同时保持简单调用 |
| 只读模式 | `mode=ro` URI 参数 | 文件权限 | 应用层强制，跨平台可靠 |
