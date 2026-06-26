---
module_id: _global
architectural_role: "模块索引导航"
---

## 模块清单

| 模块 | 概要职责 | 概览文档 | kb_path |
|------|---------|---------|---------|
| server | MCP stdio 服务启动与请求路由 | `server/_overview.md` | `.codemaker/codeindex/src/codesense_v1/server` |
| registry | @tool 装饰器注册与 dispatch 调度 | `registry/_overview.md` | `.codemaker/codeindex/src/codesense_v1/registry` |
| tools | 6 个 MCP Tool endpoint 适配层 | `tools/_overview.md` | `.codemaker/codeindex/src/codesense_v1/tools` |
| summarizer | LLM Prompt 生成与摘要管理 | `summarizer/_overview.md` | `.codemaker/codeindex/src/codesense_v1/summarizer` |
| data | CodeGraph SQLite 查询 + 架构分析算法 | `data/_overview.md` | `.codemaker/codeindex/src/codesense_v1/data` |
| cache | .codesense/ 缓存文件读写与校验 | `cache/_overview.md` | `.codemaker/codeindex/src/codesense_v1/cache` |
| errors | 统一异常层次，被所有模块依赖 | `errors/_overview.md` | `.codemaker/codeindex/src/codesense_v1/errors` |

## 依赖关系速查

```
server ──→ registry ──→ tools ──→ summarizer ──→ data
                                    │              │
                                    └──→ cache     └──→ SQLite DB (codegraph.db)

errors ←── 所有模块 (横切依赖)
```

- **server** 上游：MCP Client（外部）| 下游：registry
- **registry** 上游：server、tools | 下游：errors
- **tools** 上游：MCP Client（通过 registry）| 下游：summarizer、cache、data
- **summarizer** 上游：tools | 下游：data、cache
- **data** 上游：summarizer、tools | 下游：SQLite DB
- **cache** 上游：summarizer、tools | 下游：无
- **errors** 上游：所有模块 | 下游：无（叶子模块）
