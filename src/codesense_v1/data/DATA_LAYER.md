# Data 层：数据提炼过程

本文档描述 `codesense_v1/data/` 数据层从 CodeGraph SQLite 数据库到 LLM 提示词的完整提炼流程。

---

## 一、数据来源

数据层的数据来源有两类：

**① SQLite 数据库（主要来源）**

读取 CodeGraph 工具预先构建的数据库（`<project_root>/.codegraph/codegraph.db`），以**只读模式**（URI `?mode=ro`）打开。

| 表 | 关键字段 |
|---|---|
| `files` | `path`, `language`, `size`, `node_count` |
| `nodes` | `id`, `kind`(file/import/function/class/method…), `name`, `qualified_name`, `file_path`, `start_line`, `end_line`, `signature` |
| `edges` | `source`, `target`, `kind`(contains/imports/calls…), `line` |

**② 源码文件（补充来源，最小 IO）**

仅 `docstrings.py` 模块读取源文件，提取 docstring / 注释文本。这是 data 层**唯一做文件 IO 的模块**，其余模块全程只读 SQLite。

---

## 二、提炼流程

数据经五个模块逐层提炼：

```
SQLite (.codegraph/codegraph.db)        源码文件（按需）
        │                                      │
        │  db.py — 只读查询，强类型 dataclass   │  docstrings.py — 提取 docstring
        ▼                                      ▼
FileRow / NodeRow / EdgeRow          file_docstring / symbol_docstrings
        │                                      │
        │  modules.py — 节点 ID → 文件路径      │
        ▼                                      │
Module / ModuleEdge（文件粒度）                │
        │                                      │
   ┌────┴──────────────────────┐               │
   │                           │               │
   │ aggregate.py              │ architecture.py│
   │ 目录级聚合                 │ 图拓扑计算     │
   ▼                           ▼               │
目录级依赖 / 符号清单        DirCentrality /  │
                             layers / cycles / │
                             public_api /      │
                             external_by_dir   │
   │                           │               │
   └──────────┬────────────────┘               │
              │  ◄─────────────────────────────┘
              │  summarizer.py — 格式化为自然语言段落
              ▼
        LLM 提示词
```

### `db.py` — 原始边界

SQLite Row → 强类型 frozen dataclass，全程只读：

```python
NodeRow(id="n-001", kind="class", name="CodeGraphDB",
        qualified_name="codesense_v1.data.db.CodeGraphDB",
        file_path="src/data/db.py", start_line=44, signature="class CodeGraphDB")
EdgeRow(source="n-002", target="n-003", kind="imports", line=8)
```

### `modules.py` — 文件级依赖

节点级边 → 文件级边，关键转换三步：
1. 每个文件映射为 `Module`，赋予 `id`（POSIX 路径）和内部 `resolve_id`（匹配 import 语句用）。
2. `imports` 边：`file_A → import_placeholder → file_B` 折叠为 `file_A → file_B`；解析失败的目标标记 `external::<name>`。
3. `calls` 边：仅在源文件已有 `imports` 边到目标文件时才信任，过滤 CodeGraph 误识别。

### `aggregate.py` — 目录级聚合

文件边 → 目录边（多条合并为一条），同时按目录归集符号清单：

```python
{"src/summarizer": {"imports": ["src/data", "src/cache"]}}   # directory_dependencies
{"src/data": [{"name": "CodeGraphDB", "kind": "class", ...}]}  # directory_symbols
```

### `architecture.py` — 图拓扑信号（语言无关）

| 函数 | 输出 | 语义 |
|---|---|---|
| `compute_centrality()` | `dict[dir, DirCentrality]` | fan-in / fan-out / 外部 fan-out |
| `topological_layers()` | `list[list[dir]]` | 层级 0=基础，最高层=入口；循环用 SCC 收缩 |
| `find_cycles()` | `list[list[dir]]` | 大小 > 1 的强连通分量（真实循环依赖） |
| `cross_dir_public_api()` | `dict[dir, list[symbol]]` | 被外部目录实际 import 的符号（图推导，无语言偏见） |
| `external_dependencies_by_dir()` | `dict[dir, list[str]]` | 每目录依赖的外部包/标准库 |

### `docstrings.py` — 源码文本提取

data 层**唯一做文件 IO 的模块**。利用 `NodeRow.start_line` 定位，按语言分发提取：

| 语言 | 文件级 docstring | 符号级 docstring |
|---|---|---|
| Python | 文件顶部（跳过 shebang/encoding）的三引号字符串 | `def`/`class` 行之后的三引号字符串 |
| TypeScript/JS | 文件顶部 JSDoc `/** ... */`，fallback 到 `//` | 声明行之前的 JSDoc 块，fallback 到 `//` |
| Go | 文件顶部连续 `//` 注释块 | 声明行之前连续 `//` 注释块 |
| Rust | 文件顶部 `//!` 或 `//` | 声明行之前 `///` 或 `//` |
| Erlang | 文件顶部连续 `%%` 注释块 | 声明行之前连续 `%%` |
| Ruby / Shell | 文件顶部连续 `#` 注释块 | 声明行之前连续 `#` |

截断策略：取首行，上限 200 字符。每个源文件只读一次（函数批量提取共用同一次 IO）。可通过 `CODESENSE_EXTRACT_DOCSTRINGS=false` 关闭。

---

## 三、写入提示词的内容

### `get_project_map_prompt`（模块划分任务）

视角：全项目俯瞰，目录级，共七类数据。

| # | 数据 | 来源 | 提示词示例 | 作用 |
|---|---|---|---|---|
| ① | 目录符号清单 | `aggregate.directory_symbols()` | `- \`src/data\`: 12 个符号  [CodeGraphDB, ...]` | LLM 通过符号名推断目录职责 |
| ② | 目录中心性 | `architecture.compute_centrality()` | `(←4 →0)` 嵌在①行内 | 基础设施 vs 入口层，省去 LLM 自己推依赖方向 |
| ③ | 外部依赖包名 | `architecture.external_dependencies_by_dir()` | `外部: sqlite3, mcp` 嵌在①行内 | 包名是职责强信号 |
| ④ | **文件级 docstring** | `docstrings.extract_file_docstring()` | `> [文件注释] 封装 CodeGraph DB 查询…` 嵌在①行内 | 直接提供目录职责文字描述，消除靠符号名猜的需要 |
| ⑤ | 架构层级 | `architecture.topological_layers()` | `第 0 层（基础层）: \`src/data\`…` | 直接给出分层结论 |
| ⑥ | 目录间内部依赖 | `aggregate.directory_dependencies()` | `\`src/summarizer\` → src/data [imports]` | 辅助判断哪些目录职责相近 |
| ⑦ | 循环依赖警告 | `architecture.find_cycles()` | `⚠️ \`src/core\` ↔ \`src/utils\`` | 提示强耦合，引导合并或标注 |

---

### `get_module_prompt`（模块详细分析任务）

视角：单模块聚焦，文件+符号级，共九类数据。

| # | 数据 | 来源 | 提示词示例 | 作用 |
|---|---|---|---|---|
| ① | 模块元信息 | modules_index 缓存 | `模块名称: 缓存层` | 上下文锚点 |
| ② | 包含文件清单 | `_expand_module_files()` | `- \`cache.py\`  — [文件注释] 管理缓存文件读写` | 让 LLM 逐文件分析，文件级 docstring 直接给出用途 |
| ③ | 对外接口（图推导） | `architecture.cross_dir_public_api()` | `- \`cache.read_project_map\`` | 真实公开 API，跨语言通用 |
| ④ | 外部依赖库 | `architecture.external_dependencies_by_dir()` | `- \`pathlib\`` | 揭示技术栈 |
| ⑤ | 模块内符号（含签名） | `db.iter_nodes()` | `- \`db_hash\` (function): db_hash(db_path) -> str` | 签名揭示接口契约 |
| ⑥ | **符号级 docstring** | `docstrings.extract_symbol_docstrings()` | `> [docstring] Return a hex SHA-256 digest of the database file.` 附在⑤每个符号下 | 直接提供函数行为语义，消除靠名字猜的需要 |
| ⑦ | 上游依赖 | `aggregate.directory_dependencies()` | `- \`src/errors\`` | 描述依赖的基础设施 |
| ⑧ | 下游依赖 | 同上 | `- \`src/summarizer\`` | 理解修改影响范围 |
| ⑨ | **数据可信度说明** | 硬编码 | `[文件注释]/[docstring] 反映写作时意图…⚠️ 标注符号建议 read_file` | 防假饱和，见第五节 |

---

## 四、鲁棒性设计：防假饱和

### 问题

docstring 加入后，Agent 可能在提示词数据自洽时完全停止读源码（实测缓存层 100% 零读码）。若 docstring 过时或与实现不符，Agent 无法察觉，产生"假饱和"——提示词数据表面完整，实际描述已失真。

### 三项措施

**① 数据来源标签**

所有来自文本提取（非图推导）的内容统一加前缀标签，让 Agent 区分"权威图数据"和"文本提取数据"：

```
- `iter_nodes` (function): iter_nodes(self, kinds) -> Iterator[NodeRow]
  > [docstring] Yield nodes from the graph, optionally filtered by kind.

**`src/data/db.py`**  — [文件注释] Read-only access to CodeGraph's SQLite database.
```

**② 触发式 ⚠️ 警告**

两种条件自动触发，显式提示 Agent 读码验证：

| 条件 | 提示词输出 |
|---|---|
| 符号无 docstring + 名称通用（`run`/`handle`/`process`/`create` 等） | `⚠️ 无 docstring 且名称通用，建议 read_file 确认实现语义` |
| 图推导公开 API 为空 + 目录名暗示入口/服务层（`tools`/`server`/`cli`/`api` 等） | `（未检测到项目内部 import——目录名称暗示此模块为入口/服务层。对外接口由外部协议定义，不在图推导范围；建议查阅协议文档或 read_file）` |

**③ 固定的数据可信度说明段落**

每份 `get_module_prompt` 输出末尾固定附加：

```
---

**数据可信度说明**

以上信息由静态图分析（CodeGraph）与源码文本提取生成，存在以下已知局限：
- `[文件注释]` / `[docstring]` 标注内容反映写作时的设计意图，与最新实现可能存在偏差；
- 函数签名不显示副作用（I/O、全局状态、异常路径）；
- 图推导对外接口仅统计项目内部 import，不覆盖外部调用方（MCP/CLI/HTTP）；
- 标注 ⚠️ 的符号，建议调用 `read_file` 核实实现细节。
```

### 鲁棒性设计原则

提示词的目标不是让 Agent **停止探索**，而是让 Agent **高效探索**：

- 数据完整时：零读码完成摘要（缓存层实测）
- 数据有疑点时：标签 + ⚠️ 引导 Agent 精准读码，而不是全文盲读
- 数据缺失时：明确告知缺口（入口层公开 API 空集 + 协议提示）

---

## 五、局限与取舍

| 局限 | 具体表现 |
|---|---|
| **docstring 可能过时** | 代码重构但注释未更新；提示词数据自洽不代表与实现一致（已通过标签 + 可信度说明缓解） |
| **符号截断** | `max_per_dir=50`，大目录可能丢失关键符号 |
| **图推导公开 API 对入口层失效** | `tools/`、`server/` 等由外部调用，无内部 import，`cross_dir_public_api` 必然返回空（已通过入口层专属提示缓解） |
| **`calls` 边不全** | 反射、动态导入、运行时多态的调用不可见 |
| **拓扑层级退化** | 大型 SCC 收缩后分层弱化；孤岛目录与基础层混在 layer 0 |
| **不感知运行时** | 外部依赖无法区分运行时与开发依赖；无项目清单解析 |
| **签名依赖 CodeGraph** | 动态类型语言无注解时签名可能为空 |
| **文件 IO 新增** | `docstrings.py` 引入文件读取；源码不可访问时优雅降级为空，但会降低提示词质量 |

**设计边界**：data 层收录"可从图结构或文件文本提取的静态信号"，不收录"需要运行时或构建产物才能获得的信息"（如实际调用栈、性能数据、运行时类型）。

---

## 六、实验验证

| 模块 | 阶段 | 提示词贡献 | 读码次数 | 主要原因 |
|---|---|---|---|---|
| `tools`（入口层，6 符号） | 加 docstring 前 | ~35% | 多次 | 符号少；图推导必然空 |
| `cache`（中间层，18 符号） | 加 docstring 前 | ~45% | 多次 | 行为语义需读 docstring 补全 |
| `cache`（中间层，18 符号 + docstring） | **加 docstring 后** | **100%** | **0** | 签名 + docstring 五要素全齐 |

**结论**：

- **签名**（接口长什么样）+ **docstring**（做什么）两者相互补充，共同消除了对"读源码"的依赖
- **有利样本条件**：项目 docstring 维护良好、模块内聚、无复杂运行时行为
- **实测数据来源**：缓存层 18 符号全带 docstring，Agent 确认未调用任何 `read_file` / `grep_search` / `glob_search`；还通过 `# noqa: ARG001` 注解交叉验证了签名与实现的一致性

**待补充**：`tools`（入口层）加 docstring 后的实验结果——入口层结构性问题（公开 API 必然空）docstring 无法完全解决，是更真实的边界案例。
