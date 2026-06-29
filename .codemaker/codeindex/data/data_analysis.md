---
entity_names:
  constants:
    - name: AUXILIARY_DIR_NAMES
      value: "frozenset({\"test\",\"tests\",\"testing\",\"__tests__\",\"spec\",\"specs\",\"script\",\"scripts\",\"doc\",\"docs\",\"documentation\",\"dev-docs\",\"devdocs\",\"example\",\"examples\",\"sample\",\"samples\",\"demo\",\"demos\"})"
      source: src/codesense_v1/data/structure.py
    - name: AUXILIARY_CATEGORY
      value: "{\"test\":\"测试代码\",\"tests\":\"测试代码\",\"testing\":\"测试代码\",\"__tests__\":\"测试代码\",\"spec\":\"测试代码\",\"specs\":\"测试代码\",\"script\":\"辅助脚本\",\"scripts\":\"辅助脚本\",\"doc\":\"文档\",\"docs\":\"文档\",\"documentation\":\"文档\",\"dev-docs\":\"文档\",\"devdocs\":\"文档\",\"example\":\"示例代码\",\"examples\":\"示例代码\",\"sample\":\"示例代码\",\"samples\":\"示例代码\",\"demo\":\"示例代码\",\"demos\":\"示例代码\"}"
      source: src/codesense_v1/data/structure.py
    - name: _HAS_EXTENSION_RE
      value: "re.compile(r\"\\.[a-zA-Z0-9]+$\")"
      source: src/codesense_v1/data/structure.py
retrieval_hints:
  - "正向疑问句：怎么做架构拓扑分层和环检测？"
  - "正向疑问句：目录中心度（fan_in/fan_out）怎么算？"
  - "正向疑问句：顶层目录怎么分类为业务目录/测试/文档/脚本？"
  - "正向疑问句：segment 缓存失效判断的 4 个 hash 各基于什么数据？"
  - "⚠️ 反向排除：若找文件级依赖边提取，不在本子文档，在 data_query.md（modules.py）"
  - "⚠️ 反向排除：若找 README/配置文件读取或文档字符串提取，不在本子文档，在 data_context.md"
  - "架构归属句：架构图算法（SCC/拓扑分层/中心度）属 data 层，语言无关，不可在 summarizer 内重写图算法"
  - "架构归属句：4 个内容指纹是 segment 缓存失效核心，hash 输入必须是结构数据而非 LLM 文本，避免改措辞触发假失效"
architectural_role: "CodeGraph 数据查询层"
---

# data_analysis — 架构分析 + 目录分类 + 内容指纹

覆盖：`architecture.py` / `structure.py` / `hashes.py`。

## 对外接口

| 函数/类 | 用途 | 所在文件 |
|---|---|---|
| `DirCentrality` | frozen dataclass：`directory`/`fan_in`/`fan_out`/`fan_out_external` | architecture.py |
| `ArchitectureFeatures` | frozen dataclass：`centrality`/`layers`/`cycles`/`public_api`/`external_by_dir` | architecture.py |
| `compute_centrality(edges, modules, *, max_depth)` | 每目录 fan_in/fan_out（内部）+ 外部 fan_out 计数 | architecture.py |
| `find_cycles(edges, modules, *, max_depth)` | 强连通分量（SCC）size>1 即真实环 | architecture.py |
| `topological_layers(edges, modules, *, max_depth)` | 目录拓扑分层（layer 0=基础，环收缩为超节点） | architecture.py |
| `cross_dir_public_api(db, *, max_depth, max_per_dir, symbol_kinds)` | 每目录被外部 import 的符号列表 | architecture.py |
| `external_dependencies_by_dir(edges, modules, *, max_depth, max_per_dir)` | 每目录的 `external::` 依赖聚合 | architecture.py |
| `architecture_features(db, edges, modules, *, max_depth)` | 一次性算全部架构信号 → `ArchitectureFeatures` | architecture.py |
| `TopLevelDir` | frozen dataclass：`name`/`file_count`/`is_auxiliary`/`category` | structure.py |
| `classify_top_dirs(all_file_paths)` | 顶层目录分类（L1 业务/L2 辅助/L3 噪声丢弃），按 file_count 降序 | structure.py |
| `auxiliary_category(name)` | 辅助目录归类（精确名 + `_`/`-` 分词复合名匹配）→ 中文标签或 None | structure.py |
| `compute_tree_max_depth(file_paths, aux_dir_names, floor)` | 自适应目录树最大深度（取叶子源目录最小深度，clamp 到 floor） | structure.py |
| `compute_identity_hash(sources)` | 身份源文件 manifest 的 sha256 | hashes.py |
| `compute_structure_hash(top_dirs)` | 顶层目录结构（name/file_count/is_auxiliary）的 sha256 | hashes.py |
| `compute_architecture_hash(module_dir_groups)` | 模块目录分组集合的 sha256 | hashes.py |
| `compute_dependencies_hash(edges)` | 模块级内部有向边集合的 sha256 | hashes.py |

## 跨模块依赖

外部依赖（data → 其他模块）：

| 依赖 | 用途 |
|---|---|
| `codesense_v1.data.db` | architecture 的 `cross_dir_public_api`/`architecture_features` 需 `CodeGraphDB` |
| `codesense_v1.data.modules` | architecture 依赖 `Module`/`ModuleEdge` |
| `codesense_v1.data.project_info` | hashes 的 `compute_identity_hash` 依赖 `IdentitySource` |
| `codesense_v1.data.structure` | hashes 的 `compute_structure_hash` 依赖 `TopLevelDir` |
| 标准库 `sys`/`collections.abc`/`dataclasses`/`pathlib`/`hashlib`/`json`/`re`/`collections` | 图算法与指纹计算 |

反向调用方：

| 调用方 | 调用的 data 函数 |
|---|---|
| `tools/project_map.py` | `classify_top_dirs`/`compute_tree_max_depth`/`find_cycles`/`topological_layers`/`compute_identity_hash`/`compute_structure_hash`/`compute_architecture_hash`/`compute_dependencies_hash` |
| `tools/save_project_map_segment.py` | `classify_top_dirs`/`find_cycles`/`compute_identity_hash`/`compute_structure_hash`/`compute_architecture_hash`/`compute_dependencies_hash` |
| `summarizer/summarizer.py` | `compute_centrality`/`topological_layers`/`find_cycles`/`cross_dir_public_api`/`external_dependencies_by_dir`/`architecture_features`/`classify_top_dirs`/`auxiliary_category`/`AUXILIARY_CATEGORY`/`AUXILIARY_DIR_NAMES`/`TopLevelDir`/`compute_architecture_hash`/`compute_dependencies_hash` |

## 典型调用链

1. `project_map tool → list_modules/module_dependencies → topological_layers(edges, modules) + find_cycles(...) + compute_centrality(...)`（架构 segment 渲染：分层 + 环 + 中心度）。
2. `summarizer → architecture_features(db, edges, modules)`（一次性取全部架构信号，供 module segment 渲染）。
3. `project_map tool → classify_top_dirs(all_paths) → compute_structure_hash(top_dirs)`（结构 hash 判断 02_structure segment 是否需重生）。

## 实现约束清单

| 类型 | 约束 |
|---|---|
| 设计决策 | architecture 全部输出为纯图指标或符号可达性，**语言无关**（Python/TS/Go/Rust/Java/Erlang 通用），不查语言特定导出规则（如 `__all__`/`pub`/大写名）；"公开 API"由跨目录 import 边推断。 |
| 设计决策 | `topological_layers`：layer 0 = 无出边的图叶子（基础层）；环用 Tarjan SCC 收缩为超节点，保证循环代码库结果良定义。 |
| 设计决策 | `_tarjan_sccs` 用迭代式 Tarjan（非递归）避免大图 Python 递归栈溢出；`topological_layers` 同样用迭代后序 DFS。 |
| 设计决策 | `classify_top_dirs` 三级：L1 业务目录（不匹配辅助模式）/ L2 辅助目录（匹配 `AUXILIARY_DIR_NAMES` 或复合名分词命中）/ L3 噪声（`.` 开头或像文件名带扩展名）静默丢弃。 |
| 设计决策 | `auxiliary_category` 匹配精确名 + `_`/`-` 分词复合名（如 `js_tests` → "测试代码"）。 |
| 设计决策 | `compute_tree_max_depth`：叶子源目录最小深度 clamp 到 `floor=3`；中间路径段只用窄集合（test/script）过滤，docs/example 仅顶层过滤（避免误伤 `com.example` 包名）。 |
| 必须实现的函数 | 4 个 hash 函数语义：`compute_identity_hash(sources)` 输入 `list[IdentitySource]`，manifest=sorted `[(path, sha256(content))]`，输出 sha256；源文件增删改触发失效。`compute_structure_hash(top_dirs)` 输入 `list[TopLevelDir]`，entries=sorted `[(name, file_count, is_auxiliary)]`；顶层目录增删或文件数变触发失效。`compute_architecture_hash(module_dir_groups)` 输入 `list[list[str]]`（每模块的目录列表），sorted_groups=sorted(sorted(dirs))；模块目录分配变触发失效，**改模块名/描述不变**。`compute_dependencies_hash(edges)` 输入 `list[ModuleEdge]`，edge_pairs=sorted `(source, target)` **仅内部边**（`is_external=False`）；import 关系变触发失效，函数体改/内部重构不触发。 |
| 阈值/默认值 | `cross_dir_public_api` 的 `max_per_dir` 默认 `30`，`symbol_kinds` 默认 `("function","class","method","variable")`。 |
| 阈值/默认值 | `external_dependencies_by_dir` 的 `max_per_dir` 默认 `20`。 |
| 阈值/默认值 | `compute_tree_max_depth` 的 `floor` 默认 `3`。 |
| 设计决策 | 4 个 hash 均基于结构数据（文件 manifest/目录列表/边集），**不基于 LLM 生成文本**，故改措辞不触发假缓存失效。 |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/data.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

- `doc/Week2/design/data.md`：未覆盖 architecture/structure/hashes（Week2 设计仅含 db/files/modules/aggregate 四子模块，architecture/structure/hashes/project_info/docstrings/ref_docs 为 Week3+ 演进新增）。关键设计决策（文件级 ID=POSIX 路径、`external::` 前缀、SQLite 只读、单一 SQLite 边界）沿用至本子文档涉及的图算法输入。
- `doc/Week5/week5_handoff.md`：Week5 前置改动中 `summarizer` 调用 `compute_architecture_hash(module_dir_groups)` 与 `compute_dependencies_hash(edges)` 判断 03_modules/04_dependencies segment 缓存失效（hash 一致命中缓存，不一致 `invalidate()` 全清后重生）。`structure.py` 从 summarizer 迁出供多层复用避免循环 import。
