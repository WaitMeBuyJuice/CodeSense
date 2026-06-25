# Data 层：数据提炼过程

本文档描述 `codesense_v1/data/` 数据层从 CodeGraph SQLite 数据库到 LLM 提示词的完整提炼流程。

---

## 一、数据来源

数据层**不解析源码**，而是读取 CodeGraph 工具预先构建的 SQLite 数据库（`<project_root>/.codegraph/codegraph.db`），以**只读模式**（URI `?mode=ro`）打开。

数据库三张核心表：

| 表 | 关键字段 |
|---|---|
| `files` | `path`, `language`, `size`, `node_count` |
| `nodes` | `id`, `kind`(file/import/function/class/method…), `name`, `qualified_name`, `file_path`, `signature` |
| `edges` | `source`, `target`, `kind`(contains/imports/calls…), `line` |

---

## 二、提炼流程

数据经四个模块逐层提炼，`db.py` 是唯一接触 SQLite 的边界；CodeGraph schema 变更只需修改 `db.py`。

```
SQLite (.codegraph/codegraph.db)
        │
        │  db.py — 只读查询，封装为强类型 frozen dataclass
        ▼
FileRow / NodeRow / EdgeRow
        │
        │  modules.py — 节点 ID → 文件路径，import 解析，external 标记
        ▼
Module / ModuleEdge（文件粒度）
        │
   ┌────┴──────────────────────┐
   │                           │
   │ aggregate.py              │ architecture.py
   │ 目录级聚合                 │ 图拓扑计算（语言无关）
   ▼                           ▼
目录级依赖 / 符号清单        DirCentrality / layers / cycles /
                             public_api / external_by_dir
   │                           │
   └──────────┬────────────────┘
              │
              │  summarizer.py — 格式化为自然语言段落
              ▼
        LLM 提示词
```

### `db.py` — 原始边界

SQLite Row → 强类型 dataclass，全程只读：

```python
NodeRow(id="n-001", kind="class", name="CodeGraphDB",
        qualified_name="codesense_v1.data.db.CodeGraphDB",
        file_path="src/data/db.py", signature="class CodeGraphDB")
EdgeRow(source="n-002", target="n-003", kind="imports", line=8)
```

### `modules.py` — 文件级依赖

节点级边 → 文件级边，关键转换三步：
1. 每个文件映射为 `Module`，赋予 `id`（POSIX 路径）和内部 `resolve_id`（匹配 import 语句用）。
2. `imports` 边：`file_A → import_placeholder → file_B` 折叠为 `file_A → file_B`；解析失败的目标标记 `external::<name>`。
3. `calls` 边：仅在源文件已有 `imports` 边到目标文件时才信任，过滤 CodeGraph 误识别。

```python
ModuleEdge(source="src/summarizer/summarizer.py", target="src/data/db.py",
           kind="imports", is_external=False)
ModuleEdge(source="src/data/modules.py", target="sqlite3",
           kind="imports", is_external=True)   # external::sqlite3
```

### `aggregate.py` — 目录级聚合

文件边 → 目录边（多条合并为一条），同时按目录归集符号清单：

```python
# directory_dependencies 输出
{"src/summarizer": {"imports": ["src/data", "src/cache"]}}

# directory_symbols 输出
{"src/data": [{"name": "CodeGraphDB", "kind": "class", "file": "src/data/db.py"}, ...]}
```

### `architecture.py` — 图拓扑信号（语言无关）

| 函数 | 输出 | 语义 |
|---|---|---|
| `compute_centrality()` | `dict[dir, DirCentrality]` | fan-in（被依赖数）/ fan-out（依赖他人数）/ 外部 fan-out |
| `topological_layers()` | `list[list[dir]]` | 层级 0=基础，最高层=入口；循环用 SCC 收缩 |
| `find_cycles()` | `list[list[dir]]` | 大小 > 1 的强连通分量（真实循环依赖） |
| `cross_dir_public_api()` | `dict[dir, list[symbol]]` | 被外部目录实际 import 的符号（图推导，无语言偏见） |
| `external_dependencies_by_dir()` | `dict[dir, list[str]]` | 每目录依赖的外部包/标准库 |

---

## 三、写入提示词的内容

### `get_project_map_prompt`（模块划分任务）

视角：全项目俯瞰，目录级，共六类数据。

| # | 数据 | 来源 | 提示词示例 | 作用 |
|---|---|---|---|---|
| ① | 目录符号清单 | `aggregate.directory_symbols()` | `- \`src/data\`: 12 个符号  [CodeGraphDB, iter_nodes, ...]` | LLM 通过符号名推断目录职责 |
| ② | 目录中心性 | `architecture.compute_centrality()` | `(←4 →0)` 嵌在①行内 | `←4 →0`=基础设施，`←0 →3`=入口层，省去 LLM 自己推依赖方向 |
| ③ | 外部依赖包名 | `architecture.external_dependencies_by_dir()` | `外部: sqlite3, mcp` 嵌在①行内 | 包名是职责强信号（`sqlite3`→存储，`mcp`→RPC，`openai`→LLM层） |
| ④ | 架构层级 | `architecture.topological_layers()` | `第 0 层（基础层）: \`src/data\`, \`src/errors\`` | 直接给出分层结论，减少层次颠倒的错误划分 |
| ⑤ | 目录间内部依赖 | `aggregate.directory_dependencies()` | `\`src/summarizer\` → src/data [imports]` | 辅助 LLM 判断哪些目录职责相近、可合并 |
| ⑥ | 循环依赖警告 | `architecture.find_cycles()` | `⚠️ \`src/core\` ↔ \`src/utils\`` | 提示强耦合目录，引导合并或标注 |

---

### `get_module_prompt`（模块详细分析任务）

视角：单模块聚焦，文件+符号级，共七类数据。

| # | 数据 | 来源 | 提示词示例 | 作用 |
|---|---|---|---|---|
| ① | 模块元信息 | modules_index 缓存 | `模块名称: 数据层` / `初步描述: 封装 CodeGraph DB 查询` | 为 LLM 提供上下文锚点 |
| ② | 包含文件清单 | `_expand_module_files()` | `- \`src/codesense_v1/data/db.py\`` | 让 LLM 逐文件分析分工 |
| ③ | 对外接口（图推导） | `architecture.cross_dir_public_api()` | `- \`codesense_v1.data.db.CodeGraphDB\`` | 真实公开 API，取代"Python 看 `_` 前缀"等语言启发式，跨语言通用；若为空表明是纯内部实现 |
| ④ | 外部依赖库 | `architecture.external_dependencies_by_dir()` | `- \`sqlite3\`` | 揭示模块技术栈 |
| ⑤ | 模块内符号（含签名） | `db.iter_nodes()` | `- \`iter_nodes\` (function): iter_nodes(self, kinds) -> Iterator[NodeRow]` | 签名比裸名信息量高数倍，LLM 可据此写准确接口说明 |
| ⑥ | 上游依赖 | `aggregate.directory_dependencies()` | `- \`src/codesense_v1/errors\`` | 描述该模块依赖的基础设施 |
| ⑦ | 下游依赖 | 同上 | `- \`src/codesense_v1/summarizer\`` | 理解修改影响范围 |

---

## 四、局限、取舍与实验验证

### 核心局限

| 局限 | 具体表现 |
|---|---|
| **缺失 docstring / 注释** | LLM 只能靠符号名猜行为语义；`process()`、`handle()` 等通用名无法推断 |
| **符号截断** | `max_per_dir=50`，大目录可能丢失关键符号 |
| **图推导公开 API 对入口层失效** | 入口层（`tools/`、`server/`）由外部 Agent 通过 MCP 调用，无内部 import 记录，`cross_dir_public_api` 必然返回空 |
| **`calls` 边不全** | 反射、动态导入、运行时多态的调用不可见 |
| **拓扑层级退化** | 大型 SCC 收缩后分层信号弱化；孤岛目录落入 layer 0 与真正的基础层混在一起 |
| **不感知运行时** | 无项目清单解析（`pyproject.toml`/`package.json`等），外部依赖无法区分运行时与开发依赖 |
| **签名依赖 CodeGraph** | 动态类型语言无类型注解时签名可能为空 |

### 设计取舍

data 层在"信号丰富度"与"语言无关 / 实现成本"之间选择了后者：

- ✅ **收录**：可从图结构纯算的信号（拓扑、中心性、跨目录引用）
- ❌ **不收录**：需要解析源码文本的信号（docstring、类型注解、注释）

原因：CodeGraph DB 不索引注释文本；提取需要额外文件 IO 与按语言适配的注释模式（Python `"""`、TS `/** */`、Go `//`、Rust `///`……约 6 种 pattern）。剩余语义补全交由 LLM 完成。

### 实验验证（基于本项目两次测试）

| 模块 | 提示词贡献 | 读码占比 | 主因 |
|---|---|---|---|
| `tools`（入口层，6 符号） | ~35% | ~65% | 符号少；图推导公开 API 必然为空 |
| `cache`（中间层，18 符号） | ~45% | ~55% | 符号全（含私有 helper）；下游依赖明确 |
| 预测：`data`（基础层） | ~55% | ~45% | 符号密度最高；公开 API 充实 |

**核心结论**：提示词是"数据清单 + 格式模板"，价值在于省去 glob/grep/追 import 的机械开销，而非生成理解本身。行为语义、设计要点、文件一句话职责——这些有信息密度的内容必须读源码补全。

**天花板**：当前信号体系上限约 55%。若提取 docstring 并附入提示词（`cache.py` 的 docstring 已详细描述容错约定、哈希兼容等），价值可从 45% 提升至 70%+，读码成本降至 20% 以下。
