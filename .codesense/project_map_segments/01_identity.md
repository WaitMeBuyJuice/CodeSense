## 仓库定位

CodeSense 是一个 MCP（Model Context Protocol）服务，帮助 AI Agent 快速理解代码仓库的高层架构：项目组织方式、模块职责、内部结构以及模块间协作关系。

它读取 CodeGraph 生成的代码知识图谱（`.codegraph/codegraph.db`），按"全局 → 模块 → 子模块"的层级，向 Agent 提供结构化的认知信息，并把生成的摘要缓存到 `.codesense/` 目录复用。目标用户为宿主 AI Agent（如 CodeMaker）及通过 MCP 协议接入的客户端。核心价值在于：不直接调用 LLM，而是把 Data Layer 抽取的结构数据拼装成 prompt 返回给宿主 Agent，由 Agent 生成自然语言摘要后通过 `save_*` / `submit_*` 工具写回缓存——这种"Agent 即 LLM"协作模式避免了 API Key 硬编码，并让 prompt 迭代与生成解耦。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python（>=3.14） |
| 核心框架 | MCP（Model Context Protocol，stdio 服务） |
| 关键依赖 | mcp、jsonschema、openai>=2.41.1、json-repair>=0.30、pathspec>=0.12 |
| 构建工具 | hatchling（wheel 打包，packages=src/codesense_v1） |
| 类型检查 | mypy（strict，python_version=3.14） |
| Linter | ruff（line-length=100，规则 E/F/I/B/UP） |
| 测试框架 | pytest + pytest-asyncio（asyncio_mode=auto，testpaths=tests） |
| 包管理 | uv（推荐） |
| 入口 | `codesense = codesense_v1.server:main` |