## 仓库定位

CodeSense V1 是一个 MCP（Model Context Protocol）服务器，为 AI 编码助手（CodeMaker Agent）提供代码仓库的架构理解能力。

项目解决的核心问题是：当 AI Agent 面对一个不熟悉的代码仓库时，缺乏高层级的架构认知。CodeSense 通过对仓库进行静态分析（文件结构、符号提取、目录依赖），自动划分模块并生成 Markdown 格式的架构摘要，使 Agent 能够快速理解模块职责、接口契约和依赖关系。

目标用户是通过 MCP 协议接入的 AI 编码助手，特别是 CodeMaker VSCode 插件。核心价值是将代码仓库的结构化知识按需注入 Agent 上下文，大幅提升 Agent 在大型代码库中的导航和修改准确率。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python 3.14 |
| 核心框架 | MCP Python SDK（官方 mcp 包） |
| 传输协议 | MCP stdio |
| 关键依赖 | openai（LLM 调用）、jsonschema（参数校验）、json-repair（JSON 修复）、pathspec（gitignore 解析） |
| 构建工具 | Hatchling（wheel 构建） |
| 类型检查 | mypy（strict 模式） |
| 代码检查 | ruff |
| 测试框架 | pytest + pytest-asyncio |
| 目标平台 | Windows |