## 一句话定位
CodeGraph SQLite 数据库的只读查询层，提供文件/模块/依赖/架构分析数据。

## 架构简析
模块内部按「数据源 → 加工 → 分析 → 缓存Hash」分层：
- **数据源层**：`db.py` — 唯一直接访问 `.codegraph/codegraph.db` 的模块，提供只读 SQL 查询和 `CodeGraphDB` 上下文管理器
- **基础加工层**：`files.py`（文件列表+目录树）、`structure.py`（顶级目录分类）、`modules.py`（文件级依赖边提取）
- **架构分析层**：`architecture.py`（中心性/拓扑分层/循环检测/公开API/外部依赖）、`aggregate.py`（目录级依赖聚合）
- **元数据层**：`project_info.py`（README/配置文件/包文档字符串收集）、`docstrings.py`（文档字符串提取，唯一可做文件 I/O 的模块）、`ref_docs.py`（参考文档发现）
- **Hash层**：`hashes.py` — 基于结构数据（非LLM生成文本）的缓存段 hash 计算

## 文件清单
- `__init__.py` — 导出所有核心符号：`CodeGraphDB`、`Module`/`ModuleEdge`、`ArchitectureFeatures`/`DirCentrality`、`TopLevelDir`、`IdentitySource` 及各分析函数
- `db.py` — `CodeGraphDB` 类（只读 SQLite 封装），数据类 `FileRow`/`NodeRow`/`EdgeRow`，提供 `iter_files/nodes/edges`、`get_node`、`stats`
- `modules.py` — `Module`/`ModuleEdge` 数据类，`list_modules`、`module_dependencies`（文件级依赖边，支持 imports+calls，含外部依赖识别）、`to_file_dependency_dict`/`to_package_dependency_dict` 转换器
- `architecture.py` — `ArchitectureFeatures`/`DirCentrality` 数据类，`compute_centrality`（扇入/扇出）、`topological_layers`（SCC收缩后的拓扑分层）、`find_cycles`（Tarjan SCC）、`cross_dir_public_api`（跨目录导入符号）、`external_dependencies_by_dir`、`architecture_features`（一次性打包）
- `aggregate.py` — `directory_dependencies`（目录级依赖聚合）、`directory_edges`（扁平边列表）、`directory_symbols`（目录→符号映射）
- `files.py` — `list_files`（过滤 gitignore 的文件列表）、`directory_tree`（`DirectoryNode` 层级树）
- `structure.py` — `TopLevelDir` 数据类，`classify_top_dirs`（L1主目录/L2辅助目录/L3噪声目录分类）、`compute_tree_max_depth`（自适应树深度）、`auxiliary_category`/`AUXILIARY_DIR_NAMES`/`AUXILIARY_CATEGORY`
- `hashes.py` — `compute_identity_hash`、`compute_structure_hash`、`compute_architecture_hash`、`compute_dependencies_hash`（均基于结构数据 SHA256）
- `project_info.py` — `IdentitySource` 数据类，`collect_identity_sources`（README→配置文件→包docstring 优先级收集）、`extract_tech_stack_hint`、`read_readme`
- `docstrings.py` — `extract_file_docstring`/`extract_symbol_docstrings`（多语言支持：Python/TS/JS/Go/Rust/Erlang/Ruby/Shell），`is_enabled` 开关（环境变量 `CODESENSE_EXTRACT_DOCSTRINGS`）
- `ref_docs.py` — `discover_ref_docs`（扫描 `CODESENSE_REF_DOCS_DIR` 下 .md/.txt/.rst/.adoc/.docx/.pdf）、`ref_docs_prompt_section`（生成提示用文档清单）

## 上下游关系
- **上游**（依赖 data 的模块）：`summarizer`、`tools`、`tests`、`scripts`
- **下游**（data 依赖的内部模块）：无 — data 是项目最底层，只依赖标准库和第三方库（`sqlite3`、`pathspec`、`hashlib`、`json`）

## 实现约束清单
- `db.py` 是唯一与 SQLite 交互的边界；CodeGraph schema 变更只需改此文件
- `docstrings.py` 是 data 层唯一执行文件 I/O（读源文件）的模块；其余模块均为纯 CodeGraph DB 只读
- `docstrings.py` 的提取均为 best-effort：任何失败（文件不存在、编码错误、不支持的语言）均返回 `None` 或空 dict，调用方必须优雅降级
- `module_dependencies` 的 calls 边有严格过滤规则：仅信任 callable→callable 且同文件、或已有 imports 边的跨文件 calls；文件节点跨文件 calls 视为误判丢弃
- `topological_layers` 和 `find_cycles` 使用迭代式 Tarjan SCC 算法，避免 Python 递归深度限制
- `hashes.py` 所有 hash 仅基于结构数据（文件清单、边集合、目录分组），不依赖 LLM 生成文本，避免措辞变化导致误失效
- `ref_docs.py` 通过环境变量 `CODESENSE_REF_DOCS_DIR`/`CODESENSE_REF_DOCS_RECURSIVE` 控制，未配置时静默返回空列表
- `docstrings.py` 的 `is_enabled()` 由环境变量 `CODESENSE_EXTRACT_DOCSTRINGS` 控制，设为 `false` 可全局禁用文件读取
- `structure.py` 的 `classify_top_dirs` 将点开头目录和含扩展名的文件视为噪声自动丢弃
- `.codesense/.codesenseignore` 文件会自动与 `.gitignore` 合并用于过滤文件列表（`files.py`）
- 外部依赖在字典视图中统一加 `external::` 前缀以区分内部模块