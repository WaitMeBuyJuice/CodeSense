## 概念索引

| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |
|-----------------|---------|---------|------|
| 项目架构概览 | tools | `project_map` | 返回缓存的项目级架构 Markdown，包含模块列表、依赖关系、概念索引 |
| 模块详情查询 | tools | `explore_module` | 返回单个模块的接口、文件职责、上下游依赖；与 project_map 不同——前者看全局，后者看模块内部 |
| 子模块/文件详情 | tools | `explore_submodule` | 返回单个文件级子模块文档；与 explore_module 不同——粒度更细，面向文件而非目录 |
| 架构段落保存 | tools | `save_project_map_segment` | Agent 生成 project_map 缺失段落后调用此工具写入缓存；与 summarizer 中同名函数不同——此为 MCP 工具入口 |
| 模块划分提交 | tools | `submit_project_map` | Agent 生成的模块列表通过此工具解析并持久化到 modules_index.json |
| 缓存校验 | cache | `is_cache_valid`, `is_segment_valid` | 对比当前 DB hash 与缓存中的 hash，判断缓存是否过期；is_segment_valid 针对单段落，is_cache_valid 针对整体 |
| 缓存失效 | cache | `invalidate`, `invalidate_segments` | 清除整个 .codesense 缓存目录或指定段落；invalidate 全量删除，invalidate_segments 删除 project_map_segments 子目录 |
| DB 哈希指纹 | cache | `db_hash` | 对 codegraph.db 文件计算 SHA-256 摘要，作为缓存有效性的基准 |
| 缓存渲染 | cache | `render_project_map` | 将 01~07 各段落按固定顺序拼接为完整 project_map.md |
| 依赖关系分析 | data | `module_dependencies`, `directory_dependencies` | 从 CodeGraph 提取模块/目录间 import 边；module_dependencies 按模块聚合，directory_dependencies 按目录聚合 |
| 架构特征计算 | data | `ArchitectureFeatures`, `compute_centrality`, `topological_layers`, `find_cycles` | 图分析套件：中心度（扇入/扇出）、拓扑分层（0 层=基础设施）、循环依赖检测 |
| 目录分类 | data | `TopLevelDir`, `classify_top_dirs`, `auxiliary_category` | 将顶层目录分为代码目录与辅助目录（如 docs、test、script）；辅助目录不参与模块划分 |
| 项目身份识别 | data | `IdentitySource`, `collect_identity_sources` | 从 README、pyproject.toml 等文件提取项目名、描述、技术栈线索 |
| 工具注册 | registry | `tool`, `ToolSpec`, `list_tools`, `dispatch` | @tool 装饰器注册 MCP 工具；ToolSpec 封装名称/描述/参数 schema/handler；dispatch 根据工具名路由调用 |
| 参数校验 | registry, errors | `ValidationError`, `dispatch` | registry.dispatch 用 jsonschema 校验参数，失败抛 ValidationError；与 InvalidArgumentError 不同——前者是 schema 级，后者是语义级 |
| 业务错误处理 | errors | `ToolError`, `InvalidArgumentError`, `LLMError` | 异常层级：ToolError 基类 → ValidationError/InvalidArgumentError/LLMError；LLMError 是 LLM 调用失败，InvalidArgumentError 是语义非法参数 |
| 服务器启动 | server | `build_server`, `main`, `run_stdio` | build_server 构建 MCP Server 实例；main/run_stdio 启动 stdio 传输层 |
| 架构摘要生成 | summarizer | `get_project_map_prompt`, `get_module_prompt`, `get_submodule_prompt` | 协调 Data Layer 与 Cache，为 LLM 生成分析提示词；get_project_map_prompt 用于模块划分，get_module_prompt 用于单模块摘要 |
| 段落渲染 | summarizer | `render_structure_segment`, `render_dependencies_segment` | 纯程序化生成 Markdown 段落（目录树、依赖关系），无需 LLM 参与 |
| 文档字符串提取 | data | `extract_file_docstring`, `extract_symbol_docstrings` | 从源码文件提取模块/类/函数的文档字符串，用于增强 LLM 提示词 |