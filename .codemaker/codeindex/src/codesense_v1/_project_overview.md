---
module_id: _global
architectural_role: "项目全局概览"
---

## 仓库定位

CodeSense V1 是一个基于 MCP (Model Context Protocol) 的代码智能分析服务，为 AI Coding Agent 提供代码库结构探索、模块摘要生成、架构分析等能力。通过 stdio 传输与 MCP Client（如 Claude Desktop、VS Code）集成，Agent 可按需调用工具获取项目架构、模块详情和代码符号信息。

## 技术栈

- **语言**: Python ≥3.14
- **MCP 框架**: `mcp` 库 (StdioServerTransport)
- **数据存储**: SQLite (CodeGraph 索引，只读)
- **Schema 校验**: `jsonschema`
- **LLM 集成**: `openai` ≥2.41.1
- **JSON 修复**: `json-repair` ≥0.30
- **构建**: hatchling
- **测试**: pytest + pytest-asyncio
- **类型检查**: mypy (strict mode)
- **Lint**: ruff

## 顶层目录结构

| 目录 | 用途 |
|------|------|
| `src/codesense_v1/` | 主包源码 |
| `src/codesense_v1/server/` | MCP 服务入口，stdio 传输与请求路由 |
| `src/codesense_v1/tools/` | MCP 工具适配层，6 个 tool endpoint |
| `src/codesense_v1/summarizer/` | LLM Prompt 生成与摘要管理 |
| `src/codesense_v1/data/` | 数据访问层，CodeGraph SQLite 查询 + 架构分析算法 |
| `src/codesense_v1/cache/` | .codesense/ 缓存读写 |
| `src/codesense_v1/registry/` | @tool 装饰器注册与 dispatch 调度 |
| `src/codesense_v1/errors.py` | 统一异常层次 |
| `scripts/` | 辅助脚本（目录依赖校验） |
| `tests/` | 测试用例 |
| `doc/` | 项目文档与设计记录 |
