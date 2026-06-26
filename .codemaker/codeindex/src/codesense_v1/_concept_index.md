---
module_id: _global
architectural_role: "业务概念到模块映射索引"
---

## 概念映射表

| 业务概念 / 需求关键词 | module_id | 子文档 | 关键符号 | 一句话说明 |
|----------------------|-----------|--------|---------|-----------|
| 探索模块 / 查看模块详情 / 模块摘要 | tools | `tools_endpoints.md` | `explore_module` | `explore_module` 工具返回模块的深度架构理解，缓存命中直接返回摘要 |
| 项目架构 / 项目地图 / 模块划分 | tools | `tools_endpoints.md` | `project_map` | `project_map` 工具返回模块列表、依赖关系和辅助目录说明 |
| 生成 prompt / LLM 提示词 / 分析提示词 | summarizer | `summarizer_core.md` | `get_project_map_prompt`, `get_module_prompt` | summarizer 从 data 层提取结构化数据组装为 Markdown 分析 prompt |
| 提交模块划分结果 | summarizer | `summarizer_core.md` | `submit_project_map` | 解析 Agent 的 pipe-delimited 响应，写入 modules_index 和 project_map |
| 保存模块摘要 | summarizer | `summarizer_core.md` | `save_module_summary` | 保存 Agent 生成的模块 Markdown 摘要并更新模块哈希 |
| 代码图 / 符号索引 / 依赖查询 / SQLite | data | `data_db.md` | `CodeGraphDB`, `FileRow`, `NodeRow`, `EdgeRow` | CodeGraphDB 封装对 .codegraph/codegraph.db 的只读查询 |
| 文件依赖 / import 关系 / 模块依赖 | data | `data_modules.md` | `Module`, `ModuleEdge`, `module_dependencies` | 将 CodeGraph 节点/边映射为文件级依赖模型 |
| 循环依赖检测 / 拓扑分层 / 架构特征 | data | `data_architecture.md` | `find_cycles`, `topological_layers`, `compute_centrality`, `ArchitectureFeatures` | 在 ModuleEdge 列表上执行 Tarjan SCC、拓扑排序等语言无关算法 |
| 跨目录公开 API / Fan-in Fan-out | data | `data_architecture.md` | `cross_dir_public_api` | 分析跨目录符号引用，提取公开 API 和中心性指标 |
| 目录聚合 / 目录树 / 文件列表 | data | `data_aggregate.md` | `directory_dependencies`, `directory_symbols`, `directory_tree` | 文件级依赖聚合到目录级，生成目录树视图 |
| docstring 提取 / 文档字符串 / 源码文档 | data | `data_docstrings.md` | `extract_file_docstring`, `extract_symbol_docstrings` | 从源文件直接提取模块和符号的 docstring |
| 参考文档 / ref_docs | data | `data_docstrings.md` | `discover_ref_docs`, `ref_docs_prompt_section` | 扫描项目参考文档目录并生成 prompt 片段 |
| 缓存读写 / 增量更新 / .codesense | cache | `cache_core.md` | `read_project_map`, `read_module`, `write_module`, `db_hash` | 封装 .codesense/ 目录 I/O，通过 db_hash 和 module_hashes 实现增量更新 |
| 缓存有效性 / 哈希校验 | cache | `cache_core.md` | `is_cache_valid`, `read_module_hashes` | db_hash (CodeGraph SHA256) 用于 project_map 失效；module_hashes 用于模块级失效 |
| 工具注册 / MCP Tool 定义 / JSON Schema | registry | `registry_core.md` | `tool`, `dispatch`, `list_tools` | @tool 装饰器声明式注册工具函数，含 JSON Schema 校验和 dispatch 调度 |
| 错误处理 / 异常分类 / ToolError | errors | `errors_core.md` | `ToolError`, `ValidationError`, `InvalidArgumentError`, `LLMError` | 四层异常体系：基类 → Schema 层 → 语义层 → 外部服务层 |
| 服务启动 / MCP 连接 / stdio | server | `server_core.md` | `main`, `CodeSenseServer` | 启动 MCP stdio 传输、注册 tools/list 和 tools/call 处理器 |

## 易混淆系统区分

| 用户意图 | 正确目标 | 说明 |
|---------|---------|------|
| "想要项目架构概览" | **tools `project_map`** | 返回缓存或工作流指令。不要混淆：`data architecture` 是算法层，不直接面向用户 |
| "想要查看模块内容" | **tools `explore_module`** | 返回摘要。不要混淆：`data modules` 是数据模型层，提供原始依赖数据给 summarizer 消费 |
| "想要生成 prompt 给 LLM" | **summarizer** | prompt 构建逻辑在 summarizer。不要混淆：tools 是薄适配层，只做参数校验 + 委派 |
| "模块间怎么依赖" | **data `data_modules.py`** | 文件级 `ModuleEdge` 模型。不要混淆：`data_architecture` 是在此之上的图算法 |
| "项目有哪些循环依赖" | **data `data_architecture.py`** | `find_cycles` 基于 `module_dependencies` 结果执行 Tarjan SCC |
| "想知道 .codesense/ 缓存结构" | **cache** | 文件系统 I/O + hash 校验。不要混淆：summarizer 决定缓存的内容和格式 |
| "MCP Tool 怎么注册和校验参数" | **registry** | @tool 装饰器 + JSON Schema + dispatch。不要混淆：tools 是具体 tool 的实现 |
