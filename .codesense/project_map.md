# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 错误定义 | 定义工具异常层次结构(ToolError/ValidationError/LLMError等) | `src/codesense_v1` |
| 缓存层 | 管理 .codesense 缓存文件的读写、校验与失效 | `src/codesense_v1/cache` |
| 数据层 | 封装 CodeGraph DB 查询、文件遍历与模块依赖聚合 | `src/codesense_v1/data` |
| 工具注册 | 提供装饰器式工具注册与 JSON Schema 参数校验分发 | `src/codesense_v1/registry` |
| MCP 服务 | 构建 MCP Server 并暴露 stdio 传输入口 | `src/codesense_v1/server` |
| 摘要生成 | 生成项目架构概览与模块摘要的提示词及渲染逻辑 | `src/codesense_v1/summarizer` |
| MCP 工具 | 定义对外暴露的 MCP 工具(project_map/explore_module等) | `src/codesense_v1/tools` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| MCP 工具 | 工具注册 | imports |
| MCP 工具 | 摘要生成 | imports |
| MCP 工具 | 数据层 | imports |
| MCP 工具 | 缓存层 | imports |
| MCP 工具 | 错误定义 | imports |
| MCP 服务 | 工具注册 | imports |
| 工具注册 | 错误定义 | imports |
| 摘要生成 | 数据层 | imports |
| 摘要生成 | 缓存层 | imports |
| 摘要生成 | 错误定义 | imports |

## 其他目录

| 目录 | 类型 | 文件数 |
|------|------|--------|
| `tests` | 测试代码 | 10 |
| `scripts` | 辅助脚本 | 1 |