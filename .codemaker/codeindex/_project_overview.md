---
repo: CodeSense_V1
generated_at: 2026-06-29
---

# CodeSense_V1 项目概览

## 仓库定位

**CodeSense_V1** 是一个 Python MCP Server，读取 CodeGraph 已构建的代码知识图谱（SQLite DB），把"架构层面的语义理解"通过 MCP Tool 暴露给 AI Agent，让 AI 不需主动探索就能获得项目全局/模块级理解。核心目标：解决 AI 编程助手"浅层理解"问题——即使有 CodeGraph 也只做点状搜索，缺乏架构认知。

与 CodeGraph 的分工：CodeGraph 提供结构层（符号/调用图/类层次等实时检索），CodeSense 提供语义层（项目定位/模块划分/模块职责等架构描述）。二者互补：CodeSense 给"代码在系统里的位置和角色"，CodeGraph 给"谁调用了某函数"。

核心工作机制——segment 化 project_map：项目架构概览由 4 段拼接而成（01_identity 仓库定位+技术栈 / 02_structure 顶层目录结构 / 03_modules 模块列表 / 04_dependencies 模块间依赖）。02/04 段由程序纯渲染；01/03 段需 Agent 按 CodeSense 给出的提示词生成后回写缓存。模块级理解（explore_module）同理：缓存命中直接返回，未命中引导 Agent 走"取提示词→生成摘要→保存"流程。**CodeSense 自身不直接调用 LLM**，LLM 调用由宿主 Agent 完成。

> 📄 本节内容来源于仓库内置文档：`doc/Week3/project_overview_for_qa.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

## 技术栈

| 项 | 选型 |
|----|------|
| 语言 | Python 3.14（Windows） |
| MCP SDK | `mcp==1.27.2`（官方 Python SDK，版本锁定） |
| 传输 | stdio（单进程、单线程异步 asyncio） |
| 数据源 | CodeGraph 的 SQLite DB（`<project>/.codegraph/codegraph.db`） |
| 参数校验 | `jsonschema`（Draft202012Validator，集中在 registry） |
| 依赖管理 | uv + `pyproject.toml` + `uv.lock` |
| 测试 | pytest + pytest-asyncio（`asyncio_mode=auto`） |
| 静态检查 | `mypy --strict`（python_version=3.14）零错误 + `ruff check`（line-length=100，select E/F/I/B/UP） |
| 安装方式 | `uv tool install --editable .`，命令行入口 `codesense_v1` |
| 运行时依赖 | `mcp`、`jsonschema`、`openai`（LLM 客户端，由宿主 Agent 使用）、`json-repair`（可选）、`pathspec`（.codesenseignore 解析） |

## 顶层目录结构

```
CodeSense_V1/
├── src/codesense_v1/          # 源码主包
│   ├── server/                # L1 入口：MCP Server 启动 + 回调绑定 + SERVER_INSTRUCTIONS
│   ├── registry/              # L2 注册分发：@tool 装饰器 + jsonschema 校验 + 错误兜底
│   ├── tools/                 # L3 工具层：8 个 MCP 工具（project_map/explore_module/...）
│   ├── summarizer/            # 协调层：组合 data+cache，产出 prompt + 解析 + 渲染 Markdown
│   ├── data/                  # 数据查询层：CodeGraph DB 只读封装 + 架构分析 + 内容指纹
│   ├── cache/                 # 缓存层：.codesense/ 读写与失效（segment 缓存 + 模块摘要缓存）
│   └── errors.py              # 错误类型体系（ToolError/ValidationError/InvalidArgumentError/LLMError）
├── tests/                     # 单元 + 集成测试（pytest）
├── doc/                       # 设计文档（Week2~Week5，部分已过时，以源码为准）
├── scripts/                   # 辅助脚本
├── .codemaker/                # CodeMaker 配置（codemap 图谱 / skills / rules / codeindex 知识库）
├── pyproject.toml             # 项目元数据 + 依赖 + 工具配置
└── uv.lock                    # 依赖锁定
```

## 运行时环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `CODESENSE_PROJECT_ROOT` | 目标项目根目录（决定去哪找 `.codegraph/codegraph.db` 和 `.codesense/`） | 无（三级 fallback：env → MCP roots/list → CWD 向上查找） |
| `CODESENSE_LLM_API_KEY` | LLM API Key（宿主 Agent 用，CodeSense 自身不读） | — |
| `CODESENSE_LLM_BASE_URL` | LLM Base URL | `https://api.gemai.cc/v1` |
| `CODESENSE_LLM_MODEL` | LLM 模型名 | `deepseek-v4-flash` |
| `CODESENSE_INCLUDE_DIRS` | 逗号分隔的纳入分析根目录（覆盖默认 src/ 自动检测） | 自动检测 |
| `CODESENSE_CACHE_AUTO_EXPIRE` | 缓存随 DB hash 变化自动失效；设 `false` 则始终返回旧缓存 | `true` |
| `CODESENSE_DOCSTRINGS` | 是否提取源码 docstring 注入 prompt（data.docstrings.is_enabled 读取） | 开 |
| `CODESENSE_REF_DOCS_DIR` / `CODESENSE_REF_DOCS_RECURSIVE` | 参考文档目录与递归开关（ref_docs.py） | — |
