# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 数据持久化层 | 管理缓存文件的读写、校验与失效逻辑 | `src/codesense_v1/cache` |
| 数据访问层 | 封装CodeGraph数据库的查询、节点/边迭代与模块依赖聚合 | `src/codesense_v1/data` |
| 错误处理模块 | 定义统一的自定义异常类型与错误消息 | `src/codesense_v1/errors` |
| LLM调用模块 | 封装对大语言模型的外部调用接口 | `src/codesense_v1/llm` |
| 工具注册与调度 | 管理工具规范定义、装饰器及JSON Schema错误翻译与分发 | `src/codesense_v1/registry` |
| 资源管理 | 读取项目映射等静态资源配置 | `src/codesense_v1/resources` |
| 服务层 | 构建MCP服务器，暴露工具列表、调用、资源列表与读取接口 | `src/codesense_v1/server` |
| 摘要生成器 | 调用LLM生成项目地图摘要和模块摘要，解析与渲染Markdown | `src/codesense_v1/summarizer` |
| 工具函数层 | 实现加法、模块探索、缓存列表等具体工具 | `src/codesense_v1/tools` |
| 测试层 | 包含 | `覆盖各模块的单元测试与集成测试` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| LLM调用模块 | 错误处理模块 | imports |
| 工具函数层 | 工具注册与调度 | imports |
| 工具函数层 | 摘要生成器 | imports |
| 工具函数层 | 错误处理模块 | imports |
| 工具注册与调度 | 错误处理模块 | imports |
| 摘要生成器 | LLM调用模块 | imports |
| 摘要生成器 | 数据持久化层 | imports |
| 摘要生成器 | 数据访问层 | imports |
| 摘要生成器 | 错误处理模块 | imports |
| 服务层 | 工具注册与调度 | imports |
| 服务层 | 资源管理 | imports |
| 资源管理 | 摘要生成器 | imports |
| 资源管理 | 错误处理模块 | imports |