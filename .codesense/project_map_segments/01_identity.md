## 仓库定位

CodeSense V1 是一款基于 MCP（Model Context Protocol）的代码智能分析服务，为 AI 编程助手提供代码库的结构化理解能力。

项目解决的核心问题：大型代码库中，AI 助手缺乏对项目架构、模块职责、符号关系的全局认知。CodeSense V1 通过代码索引、缓存管理和结构化摘要，将代码库的架构信息以 MCP 工具形式暴露给 LLM Agent。

目标用户为集成 MCP 客户端的 AI 编程工具（如 Cursor、VS Code Cline 等），核心价值在于让 AI 助手在回答代码问题时能快速定位模块边界、理解调用链和评估变更影响范围，无需每次都从零扫描整个代码库。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python 3.14+ |
| 核心框架 | MCP (mcp.server.stdio) |
| 关键依赖 | openai (LLM 调用), json-repair (JSON 修复), pathspec (文件忽略规则), jsonschema (工具参数校验) |
| 构建工具 | hatchling |
| 类型检查 | mypy (strict mode) |
| 代码检查 | ruff |
| 测试框架 | pytest + pytest-asyncio |