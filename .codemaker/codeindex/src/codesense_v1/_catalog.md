---
module_id: _global
architectural_role: "模块目录快查"
---

## 模块目录

| 模块 | 一句话职责 | 概览文档 |
|------|-----------|---------|
| server | MCP stdio 服务启动与 tools/list、tools/call 请求路由 | `server/_overview.md` |
| registry | @tool 装饰器注册、JSON Schema 校验与 dispatch 统一调度 | `registry/_overview.md` |
| tools | 6 个 MCP Tool endpoint 适配层：参数校验、缓存查询、委派 summarizer | `tools/_overview.md` |
| summarizer | LLM 分析 Prompt 构建、Agent 响应解析与缓存写入 | `summarizer/_overview.md` |
| data | CodeGraph SQLite 只读查询、文件/目录级依赖分析与架构特征提取 | `data/_overview.md` |
| cache | .codesense/ 缓存目录的文件 I/O 与 db_hash/module_hashes 有效性校验 | `cache/_overview.md` |
| errors | 统一异常层次 (ToolError → ValidationError / InvalidArgumentError / LLMError) | `errors/_overview.md` |
