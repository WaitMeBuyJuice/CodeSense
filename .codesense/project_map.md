# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 异常基类 | 定义工具领域可预期业务与校验异常基类 | `src/codesense_v1` |
| 缓存层 | 管理 .codesense 缓存文件的读写与失效 | `src/codesense_v1/cache` |
| 数据层 | 封装 CodeGraph DB 查询与目录级依赖聚合 | `src/codesense_v1/data` |
| 工具注册 | 负责 MCP 工具的注册、JSON Schema 校验与分发 | `src/codesense_v1/registry` |
| 摘要引擎 | 协调数据层与缓存层生成模块架构 Markdown 摘要 | `src/codesense_v1/summarizer` |
| MCP 工具 | 暴露 explore_module、project_map 等 MCP 工具入口 | `src/codesense_v1/tools` |
| 服务入口 | 构建 MCP Server 并通过 stdio 传输启动服务 | `src/codesense_v1/server` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| MCP 工具 | 工具注册 | imports |
| MCP 工具 | 异常基类 | imports |
| MCP 工具 | 摘要引擎 | imports |
| MCP 工具 | 数据层 | imports |
| MCP 工具 | 缓存层 | imports |
| 工具注册 | 异常基类 | imports |
| 摘要引擎 | 异常基类 | imports |
| 摘要引擎 | 数据层 | imports |
| 摘要引擎 | 缓存层 | imports |
| 服务入口 | 工具注册 | imports |

## 其他目录

| 目录 | 类型 | 文件数 |
|------|------|--------|
| `tests` | 测试代码 | 12 |
| `scripts` | 辅助脚本 | 1 |