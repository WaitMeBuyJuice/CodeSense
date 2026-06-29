## 概念索引

| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |
|-----------------|---------|---------|------|
| 项目架构概览 | tools | project_map | 返回整个仓库的高层架构信息 |
| 模块探索 | tools | explore_module | 深入查看单个模块的接口与依赖 |
| 子模块探索 | tools | explore_submodule | 查看模块内某个文件的细节 |
| 缓存失效 | cache | invalidate, invalidate_segments | 清除过期缓存数据 |
| 缓存校验 | cache | is_cache_valid, is_segment_valid | 比对 hash 判断缓存是否有效 |
| 缓存读取 | cache | read_project_map, read_module, read_segment | 从 .codesense/ 读取缓存 |
| 缓存写入 | cache | write_module, write_segment, write_project_map | 写入架构摘要到 .codesense/ |
| 模块划分提交 | summarizer | submit_project_map | Agent 提交模块划分结果，与 save_project_map_segment 不同：前者通过文本行提交全部模块，后者保存单个段落 |
| 段落保存 | summarizer | save_project_map_segment | 保存 project_map 的某个段落（如 01_identity），与 submit_project_map 不同 |
| 模块摘要保存 | summarizer | save_module_summary | 保存单个模块的完整架构摘要 |
| 提示词获取 | summarizer | get_project_map_prompt, get_module_prompt | 返回 LLM 分析提示词，供 Agent 生成摘要 |
| 工具注册 | registry | tool, deco, list_tools | 装饰器注册 MCP 工具 + 导出工具列表 |
| 工具分发 | registry | dispatch | jsonschema 校验 + 路由到具体工具函数 |
| 数据库查询 | data | CodeGraphDB | 封装 CodeGraph SQLite 数据库的查询接口 |
| 目录依赖 | data | directory_dependencies, directory_edges | 聚合同目录下文件级边为目录级依赖 |
| 架构特征 | data | ArchitectureFeatures, architecture_features | 提取项目的架构特征（循环依赖、层次等） |
| 文档字符串提取 | data | extract_file_docstring, extract_symbol_docstrings | 提取源码中的文件/符号文档注释 |
| 项目根定位 | tools | resolve_project_root | 通过环境变量/MCP根目录/CWD搜索定位项目根 |
| 服务器入口 | server | main, run_stdio | 启动 stdio MCP 服务器主循环 |
| 异常层级 | errors | ToolError, ValidationError, InvalidArgumentError, LLMError | 所有业务异常继承 ToolError，区分不同错误类型 |