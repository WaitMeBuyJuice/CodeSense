# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 核心基础 | 提供版本号与工具领域异常基类 | `src/codesense_v1` |
| 缓存层 | 管理 .codesense 缓存文件的读写与失效校验 | `src/codesense_v1/cache` |
| 数据层 | 封装 CodeGraph SQLite 只读查询与模块目录依赖聚合及架构特征计算 | `src/codesense_v1/data` |
| 工具注册 | 提供 MCP 工具注册装饰器与 JSON Schema 校验分发 | `src/codesense_v1/registry` |
| 服务器入口 | 构建 MCP stdio 服务器并加载工具注册 | `src/codesense_v1/server` |
| 摘要生成 | 协调数据层与缓存生成架构 Markdown 摘要及分析提示词 | `src/codesense_v1/summarizer` |
| 工具实现 | 实现六个 MCP 工具并注册到 registry | `src/codesense_v1/tools` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| 工具实现 | 工具注册 | imports |
| 工具实现 | 摘要生成 | imports |
| 工具实现 | 数据层 | imports |
| 工具实现 | 核心基础 | imports |
| 工具实现 | 缓存层 | imports |
| 工具注册 | 核心基础 | imports |
| 摘要生成 | 数据层 | imports |
| 摘要生成 | 核心基础 | imports |
| 摘要生成 | 缓存层 | imports |
| 服务器入口 | 工具注册 | imports |

## 其他目录

| 目录 | 类型 | 文件数 |
|------|------|--------|
| `tests` | 测试代码 | 11 |
| `scripts` | 辅助脚本 | 1 |