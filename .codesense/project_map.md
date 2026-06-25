# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 异常定义 | 定义工具领域异常基类与具体错误类型 | `src/codesense_v1` |
| 缓存层 | 管理 .codesense 缓存文件的读写与失效 | `src/codesense_v1/cache` |
| 数据层 | 封装 CodeGraph DB 查询与目录依赖聚合 | `src/codesense_v1/data` |
| 工具注册 | 注册并分发 MCP 工具调用 | `src/codesense_v1/registry` |
| 摘要生成 | 协调数据层与缓存层生成 Markdown 摘要 | `src/codesense_v1/summarizer` |
| MCP 服务 | 构建并运行 MCP stdio 服务入口 | `src/codesense_v1/server` |
| MCP 工具 | 暴露 project_map 与 explore_module 等 MCP 工具 | `src/codesense_v1/tools` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| MCP 工具 | 工具注册 | imports |
| MCP 工具 | 异常定义 | imports |
| MCP 工具 | 摘要生成 | imports |
| MCP 工具 | 数据层 | imports |
| MCP 工具 | 缓存层 | imports |
| MCP 服务 | 工具注册 | imports |
| 工具注册 | 异常定义 | imports |
| 摘要生成 | 异常定义 | imports |
| 摘要生成 | 数据层 | imports |
| 摘要生成 | 缓存层 | imports |

## 其他目录

| 目录 | 类型 | 文件数 |
|------|------|--------|
| `tests` | 测试代码 | 12 |
| `scripts` | 辅助脚本 | 1 |