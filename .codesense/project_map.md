## 仓库定位

CodeSense V1 是基于 MCP（Model Context Protocol）的代码智能分析服务，为 AI Coding Agent 提供代码库结构探索、模块摘要生成与架构分析能力。

服务通过 stdio 传输与 MCP Client（如 Claude Desktop、VS Code）集成，Agent 可按需调用工具获取项目架构概览、模块内部细节与代码符号信息。核心价值在于为 Agent 建立对代码库的高层认知，减少长上下文中重复扫描源码的开销，并支持跨模块影响分析与依赖评估。

目标用户为代码助手开发者与 AI Agent 集成方。服务以只读方式消费 CodeGraph 生成的 SQLite 索引，自身不重建代码图谱。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python ≥3.14 |
| 核心框架 | `mcp` 库（StdioServerTransport）、`jsonschema` |
| 关键依赖 | `openai` ≥2.41.1、`json-repair` ≥0.30、`pathspec` ≥0.12 |
| 数据存储 | SQLite（CodeGraph 索引，只读）+ `.codesense/` 文件缓存 |
| 构建工具 | hatchling |
| 类型检查 | mypy（strict mode） |
| Lint | ruff（E/F/I/B/UP 规则，line-length=100） |
| 测试框架 | pytest + pytest-asyncio（asyncio_mode=auto） |

---

## 顶层目录结构

```
CodeSense_V1/
├── scripts/  [辅助脚本]
├── src/
│   └── codesense_v1/
│       ├── cache/
│       ├── data/
│       ├── registry/
│       ├── server/
│       ├── summarizer/
│       ├── tools/
│       └── errors.py
└── tests/  [测试代码]
```

**辅助目录**

- `scripts/` — 辅助脚本（1 个文件）
- `tests/` — 测试代码（12 个文件）

---

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|----------|
| 错误定义 | 统一工具与业务异常层次 | src/codesense_v1/errors.py |
| 数据层 | 构建代码图谱(CodeGraph DB)并聚合目录/符号/依赖信息 | src/codesense_v1/data |
| 缓存层 | 管理 .codesense 缓存文件读写与失效 | src/codesense_v1/cache |
| 工具注册 | 声明工具规格并通过 jsonschema 校验与分发 | src/codesense_v1/registry |
| 摘要生成 | 协调数据层与缓存层生成架构/模块 Markdown 摘要 | src/codesense_v1/summarizer |
| 工具实现 | MCP 工具入口实现与项目根解析 | src/codesense_v1/tools |
| 服务入口 | 构建 stdio MCP 服务并加载工具 | src/codesense_v1/server |

---

## 依赖关系图

```
工具实现 ──→ 工具注册
工具实现 ──→ 摘要生成
工具实现 ──→ 数据层
工具实现 ──→ 缓存层
工具实现 ──→ 错误定义
工具注册 ──→ 错误定义
摘要生成 ──→ 数据层
摘要生成 ──→ 缓存层
摘要生成 ──→ 错误定义
服务入口 ──→ 工具注册
```

## 上下游详表

| 模块 | 上游（依赖于我） | 下游（我依赖） |
|------|----------------|--------------|
| 工具实现 | 无 | 工具注册、摘要生成、数据层、缓存层、错误定义 |
| 工具注册 | 工具实现、服务入口 | 错误定义 |
| 摘要生成 | 工具实现 | 数据层、缓存层、错误定义 |
| 数据层 | 工具实现、摘要生成 | 无 |
| 服务入口 | 无 | 工具注册 |
| 缓存层 | 工具实现、摘要生成 | 无 |
| 错误定义 | 工具实现、工具注册、摘要生成 | 无 |

> 无循环依赖。