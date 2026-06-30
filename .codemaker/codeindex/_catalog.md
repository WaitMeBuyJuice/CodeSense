# CodeSense_V1 知识库目录

> 按模块名或职责关键词定位，找到后进入对应 `_overview.md` 阅读详情。
> 业务概念检索请优先查 `_concept_index.md`（关键词 → 子文档直达）。

## 模块索引

| 模块 | 一句话职责 | 概览文档 |
|------|-----------|---------|
| `server` | MCP Server 入口，启动 stdio + 绑定回调 + 注入 Instructions | `.codemaker/codeindex/server/_overview.md` |
| `registry` | @tool 注册 + jsonschema 校验 + ToolError→MCP 错误响应 | `.codemaker/codeindex/registry/_overview.md` |
| `tools` | 8 个 MCP 工具（project_map/explore_module 等），参数校验+委派+缓存引导 | `.codemaker/codeindex/tools/_overview.md` |
| `summarizer` | 摘要协调层，组合 data+cache 产 prompt 与渲染 Markdown（不调 LLM） | `.codemaker/codeindex/summarizer/_overview.md` |
| `data` | CodeGraph SQLite DB 只读查询层 + 架构分析 + 内容指纹 | `.codemaker/codeindex/data/_overview.md` |
| `cache` | `.codesense/` 缓存读写与失效（segment 缓存 + 模块摘要缓存） | `.codemaker/codeindex/cache/_overview.md` |
| `errors` | 工具领域异常体系（ToolError/Validation/InvalidArgument/LLMError） | `.codemaker/codeindex/errors/_overview.md` |

## 全局文档

| 文档 | 内容 |
|------|------|
| `_project_overview.md` | 仓库定位、技术栈、顶层目录结构、运行时环境变量 |
| `_architecture.md` | 系统层次划分、模块边界规则、核心数据流、架构约束、外部接口规范 |
| `_core_systems.md` | 核心子系统列表与关键流程描述、设计取舍 |
| `_concept_index.md` | 业务概念 → 模块/子文档 速查表（RAG 检索入口） |
| `_index.md` | 全局架构索引（模块清单 + 依赖关系 + kb_path 元数据） |
