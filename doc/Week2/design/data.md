# 详细设计 - data 模块

> 路径：`src/codesense_v1/data/`
> 层级：L4 基础设施（与 schemas/errors 平级，纯数据加工层，不暴露 MCP 工具）
> 上游数据源：CodeGraph 索引数据库 `<project>/.codegraph/codegraph.db`（SQLite）

---

## 1. 模块功能说明

`data` 层负责从 CodeGraph 的 SQLite 知识图谱中提取、转换结构化的依赖信息，供验证脚本或上层工具消费。具体能力：

1. **文件清单**：读取索引数据库，以平铺列表或层级目录树形式返回所有已索引文件。
2. **依赖边提取**：将 CodeGraph 图中的 `imports` / `calls` 边归约到文件级别，区分内部依赖与外部依赖（第三方库）。
3. **两种视图**：
   - **文件级视图**（`to_file_dependency_dict`）：`{文件路径: {imports:[...], calls:[...]}}`
   - **包/目录级视图**（`to_package_dependency_dict`）：同语言包或目录名聚合后的视图
4. **目录聚合**（`aggregate.py`）：按文件系统目录路径聚合（与包 ID 不同，适合非 Python 项目或自定义分层）。

本层只读 SQLite，不写入，不注册 MCP 工具，不依赖 `registry` / `tools` / `server`。

---

## 2. 子模块职责

| 子模块 | 文件 | 职责 |
|---|---|---|
| db | `data/db.py` | SQLite 唯一边界，提供 `CodeGraphDB` + `FileRow`/`NodeRow`/`EdgeRow` |
| files | `data/files.py` | 文件平铺列表与层级目录树 |
| modules | `data/modules.py` | 文件级依赖边提取 + 文件/包级两种视图 |
| aggregate | `data/aggregate.py` | 按目录路径聚合（备用视图） |

---

## 3. 对外暴露接口

通过 `src/codesense_v1/data/__init__.py` 统一导出：

```python
CodeGraphDB          # 只读 SQLite 连接，上下文管理器
list_files(db)       # list[FileRow] — 所有已索引文件平铺
directory_tree(db)   # DirectoryNode — 层级目录树
list_modules(db)     # list[Module]  — 所有文件的模块对象
module_dependencies(db, *, include_external, include_calls, include_imports)
                     # list[ModuleEdge] — 文件级依赖边
to_file_dependency_dict(edges)
                     # dict[str, dict[str, list[str]]] — 文件级视图
to_package_dependency_dict(edges, modules, *, include_self_loops)
                     # dict[str, dict[str, list[str]]] — 包/目录级视图
directory_dependencies(edges, modules, *, max_depth, include_external, include_self_loops)
                     # dict[str, dict[str, list[str]]] — 目录路径聚合视图
Module               # frozen dataclass：id, file_path, language, package_id
ModuleEdge           # frozen dataclass：source, target, kind, is_external
```

---

## 4. 核心数据结构

### FileRow（frozen dataclass）
| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 相对 POSIX 路径 |
| `language` | `str` | 编程语言（python / typescript / ...） |
| `size` | `int` | 文件字节数 |
| `node_count` | `int` | 该文件的节点数 |

### NodeRow（frozen dataclass）
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 节点唯一 ID |
| `kind` | `str` | file / import / function / class / ... |
| `name` | `str` | 短名 |
| `qualified_name` | `str` | 全限定名 |
| `file_path` | `str` | 所在文件路径 |
| `language` | `str` | 编程语言 |
| `start_line` | `int` | 起始行 |
| `end_line` | `int` | 结束行 |
| `signature` | `str \| None` | 函数签名（可为空） |

### EdgeRow（frozen dataclass）
| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `str` | 源节点 ID |
| `target` | `str` | 目标节点 ID |
| `kind` | `str` | contains / imports / calls / ... |
| `line` | `int \| None` | 发生行号 |

### Module（frozen dataclass）
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 文件级 ID = POSIX 路径 |
| `file_path` | `str` | 同 id，保留冗余字段增强可读性 |
| `language` | `str` | 编程语言 |
| `package_id` | `str` | Python 用点号包名，其他语言用目录路径 |

### ModuleEdge（frozen dataclass）
| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `str` | 源文件 ID（POSIX 路径） |
| `target` | `str` | 目标文件 ID（内部）或模块名（外部） |
| `kind` | `str` | "imports" / "calls" |
| `is_external` | `bool` | True = 外部依赖 |

### DirectoryNode（dataclass）
层级目录树节点，含 `name`、`path`、`files: list[FileRow]`、`subdirs: dict[str, DirectoryNode]`，提供 `to_dict()` 序列化。

---

## 5. 与其他模块的交互契约

```
scripts/validate_dir_deps.py  ──► data  : from codesense_v1.data import ...
data  ──► (无)                : 不被 registry / tools / server 引用
```

- **严禁**被 `registry` / `tools` / `server` 引用（当前阶段是纯数据层）。
- 仅依赖标准库：`sqlite3`、`dataclasses`、`pathlib`、`collections.abc`。
- 无第三方依赖，`pyproject.toml` 无需修改。

---

## 6. 错误处理

| 场景 | 行为 |
|------|------|
| 数据库文件不存在 | `CodeGraphDB.__init__` 抛 `FileNotFoundError` |
| SQLite 查询出错 | 向上传播原始 `sqlite3.OperationalError` |
| 其他异常 | 不做兜底，由调用方决定 |

---

## 7. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 文件级 ID | POSIX 路径字符串 | 与 CodeGraph 索引保持一致，跨平台可比较 |
| resolve_id（私有） | Python 用点号名；TS/JS 去扩展名路径 | 与 import 语句书写方式对齐，支持模糊匹配 |
| 外部依赖标识 | `external::` 前缀 | 视觉上与内部路径明显区分，无歧义 |
| 内外依赖判断 | 优先看 `tgt_node.kind != "import"` | 新版 CodeGraph 已解析内部 import；旧版回退 name 匹配 |
| 包级聚合去自环 | `include_self_loops=False` 默认 | 同包内循环不算包间依赖，默认过滤更有用 |
| SQLite 只读模式 | `file:...?mode=ro` URI | 防止意外写入，CodeGraph DB 是只读约定 |
| 单一 SQLite 边界 | 所有 SQL 只在 `db.py` | schema 变更时只需改一处 |
