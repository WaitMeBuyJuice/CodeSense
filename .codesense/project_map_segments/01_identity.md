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