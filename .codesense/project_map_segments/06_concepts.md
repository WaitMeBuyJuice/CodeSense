## 概念索引

| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |
|-----------------|---------|---------|------|
| 项目映射 | 工具实现 / 摘要协调 | project_map / get_project_map_prompt | 工具实现 是 MCP 入口，摘要协调 是核心逻辑 |
| 模块划分 | 摘要协调 | submit_project_map / _parse_modules_text | 将模块文本解析为结构化缓存 |
| 模块探索 | 工具实现 | explore_module / get_module_prompt | 查看模块内部结构、文件和符号 |
| 缓存失效 | 缓存管理 | invalidate / invalidate_segments / is_cache_valid | 对比 db_hash 判断缓存是否需要重建 |
| segment(段落) | 缓存管理 / 摘要协调 | read_segment / write_segment / save_project_map_segment | project_map 由多个 segment 组成，可独立缓存和重建 |
| prompt 生成 | 摘要协调 | get_identity_segment_prompt / get_module_prompt / get_project_map_prompt | 为 LLM 分析生成上下文 prompt |
| 工具注册 | 工具注册 | ToolSpec / tool(装饰器) / dispatch | 声明式 MCP 工具定义，参数 JSON Schema 自动校验 |
| MCP 工具调用 | 服务入口 / 工具实现 | _call_tool / build_server | 服务入口 接收 → 工具注册 分发 → 工具实现 执行 |
| 项目根路径 | 工具实现 | resolve_project_root | 通过 MCP roots / 环境变量 / CWD 搜索定位项目根 |
| 代码图数据库 | 数据层 | CodeGraphDB / NodeRow / EdgeRow | 文件/符号/边的结构化存储与查询 |
| 目录依赖 | 数据层 | directory_edges / directory_dependencies | 模块间 import 依赖关系聚合 |
| 架构特征 | 数据层 | ArchitectureFeatures / DirCentrality | 计算目录中心性和架构层级 |
| 缓存哈希 | 缓存管理 | db_hash / compute_structure_hash | 用于检测代码变更以触发缓存失效 |
| project_map vs save_project_map_segment | 工具实现 vs 缓存管理 | project_map / save_project_map_segment_tool | project_map 返回完整架构概览；save_project_map_segment 仅保存单个段落到缓存 |
| submit_project_map vs submit_project_map_tool | 摘要协调 vs 工具实现 | submit_project_map / submit_project_map_tool | 摘要协调 是核心逻辑；工具实现 是 MCP 包装入口 |
| 错误处理 | 错误定义 | ToolError / ValidationError / LLMError / InvalidArgumentError | 所有异常继承 ToolError 基类 |
| 架构摘要 | 摘要协调 | render_project_map_markdown / get_architecture_segment_prompt | 将模块数据渲染为 Markdown 架构文档 |