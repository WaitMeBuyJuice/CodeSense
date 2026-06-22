# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 错误定义 | 定义工具与LLM相关错误类型 | `src/codesense_v1` |
| 缓存管理 | 提供查询结果与中间数据的缓存能力 | `src/codesense_v1/cache` |
| 数据管理 | 加载、组织并提供代码库相关数据访问 | `src/codesense_v1/data` |
| LLM交互 | 封装大语言模型调用、提示构造与响应处理 | `src/codesense_v1/llm` |
| 注册中心 | 统一注册和发现工具、资源等服务能力 | `src/codesense_v1/registry` |
| MCP资源 | 定义并对外暴露可读的MCP资源 | `src/codesense_v1/resources` |
| MCP服务端 | 启动MCP服务并协调请求、工具与资源调度 | `src/codesense_v1/server` |
| 摘要生成 | 对代码库或代码实体生成结构化摘要 | `src/codesense_v1/summarizer` |
| 工具实现 | 定义并执行代码分析相关的MCP工具 | `src/codesense_v1/tools` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| LLM交互 | 错误定义 | imports |
| MCP服务端 | MCP资源 | imports |
| MCP服务端 | 注册中心 | imports |
| MCP资源 | 摘要生成 | imports |
| MCP资源 | 错误定义 | imports |
| 工具实现 | 摘要生成 | imports |
| 工具实现 | 注册中心 | imports |
| 工具实现 | 错误定义 | imports |
| 摘要生成 | LLM交互 | imports |
| 摘要生成 | 数据管理 | imports |
| 摘要生成 | 缓存管理 | imports |
| 摘要生成 | 错误定义 | imports |
| 注册中心 | 错误定义 | imports |