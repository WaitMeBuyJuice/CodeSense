---
module_id: _global
architectural_role: "系统架构与模块边界"
---

## 系统分层

```
┌─────────────────────────────────────────┐
│  MCP Client (Claude Desktop / VS Code)  │  ← 外部
└──────────────┬──────────────────────────┘
               │ stdio
┌──────────────▼──────────────────────────┐
│  server           传输层                │   MCP stdio 启动与请求路由
│  (__main__.py / server.py)             │
└──────────────┬──────────────────────────┘
               │ list_tools() / dispatch()
┌──────────────▼──────────────────────────┐
│  registry         调度层                │   @tool 装饰器注册 + dispatch
│  (registry.py)                         │
└──────────────┬──────────────────────────┘
               │ handler lookup + jsonschema
┌──────────────▼──────────────────────────┐
│  tools            适配层                │   6 个 MCP tool endpoint
│  (6 个 tool 文件)                       │   参数校验 → 缓存查询 → 委派
└──────┬──────────┬──────────┬───────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│summarizer│ │  cache   │ │  data    │
│ 业务层   │ │ 缓存层   │ │ 数据层   │
└────┬─────┘ └──────────┘ └────┬─────┘
     │                         │
     │  prompt 构建             │  查询
     │  摘要保存               │  CodeGraphDB
     ▼                         ▼
┌──────────┐             ┌──────────────┐
│  cache   │             │  SQLite DB   │
│ .codesense│             │ .codegraph/  │
└──────────┘             └──────────────┘

┌─────────────────────────────────────────┐
│  errors           横切层                │   统一异常层次
│  (errors.py)                           │   被所有层依赖
└─────────────────────────────────────────┘
```

## 层次职责

| 层次 | 模块 | 职责 |
|------|------|------|
| **传输层** | server | MCP stdio 服务启动、tools/list 与 tools/call 请求路由 |
| **调度层** | registry | @tool 装饰器注册、JSON Schema 校验、dispatch 统一调度与错误转换 |
| **适配层** | tools | 6 个 MCP Tool endpoint：参数校验、缓存查询、委派给 summarizer |
| **业务层** | summarizer | LLM Prompt 构建、Agent 响应解析与保存、模块哈希计算 |
| **数据层** | data | CodeGraphDB 封装、文件级依赖分析、目录级聚合、架构特征提取、docstring 提取 |
| **缓存层** | cache | .codesense/ 目录读写、缓存有效性校验 (db_hash + module_hashes) |
| **横切层** | errors | 统一异常层次：ToolError → ValidationError / InvalidArgumentError / LLMError |

## 模块边界规则

1. **tools 是 Agent 唯一入口**：所有外部 MCP 请求经 tools 层进入，其他模块不暴露为 MCP Tool。
2. **summarizer 只被 tools 调用**：summarizer 的 4 个公开函数 (`get_project_map_prompt`、`submit_project_map`、`get_module_prompt`、`save_module_summary`) 仅供 tools 层使用。
3. **data 层只读**：CodeGraph SQLite 和源码 docstring 提取均为只读操作，不修改数据库或源文件。
4. **cache 层仅做 I/O**：不包含业务逻辑，仅提供文件系统读写 + hash 校验。
5. **errors 是叶子模块**：不依赖任何其他业务模块，被所有上层模块引用。
6. **循环依赖禁止**：依赖方向严格自上而下：server → registry → tools → summarizer → data/cache；errors 被所有层依赖（横切）。

## 核心数据流

```
MCP Client → server → registry.dispatch → tools
  ├─ 缓存命中: 直接返回
  └─ 缓存未命中: tools → summarizer → data(CodeGraphDB)
                   → LLM Prompt 组装
                   → Agent 生成内容
                   → summarizer 解析保存
                   → cache 写入 .codesense/
```
