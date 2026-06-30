# CodeSense

CodeSense 是一个 MCP（Model Context Protocol）服务，帮助 AI Agent 快速理解代码仓库的**高层架构**：项目组织方式、模块职责、内部结构以及模块间协作关系。

它读取 [CodeGraph](https://) 生成的代码知识图谱（`.codegraph/codegraph.db`），按"全局 → 模块 → 子模块"的层级，向 Agent 提供结构化的认知信息，并把生成的摘要缓存到 `.codesense/` 目录复用。

## 核心理念

CodeSense **不直接调用 LLM**。它把 Data Layer 抽取的结构数据拼装成 prompt 返回给宿主 Agent，由 Agent 生成自然语言摘要后，再通过 `save_*` / `submit_*` 工具写回缓存。这种"Agent 即 LLM"的协作模式避免了 API Key 硬编码，并让 prompt 迭代与生成解耦。

## 工具层级

由全局到细节，逐层下钻：

| 层级 | 工具 | 职责 |
|------|------|------|
| 全局 | `project_map` | 项目架构、模块分布、跨模块依赖 |
| 模块 | `explore_module` | 模块职责、公开接口、内部文件、依赖关系 |
| 子模块 | `explore_submodule` | 子模块内文件结构、关键符号、实现细节 |

配套的写回工具：`submit_project_map`、`save_project_map_segment`、`save_module_summary`、`save_submodule_summary`。

更细粒度的符号 / 调用链 / 原文检索，交给 codegraph MCP 或 `grep` + `read_file`。

## 内置 Skills

CodeSense 服务**启动时**自动将两个内置 Skill 写入项目的 `.claude/skills/` 目录，CodeMaker 从该目录读取后即可激活，无需手动安装：

| Skill | 适用场景 |
|-------|---------|
| `codesense-flow` | 理解项目架构、探索模块关系、修改代码前的四层递进探索工作流 |
| `codesense-init` | 首次初始化 CodeSense 知识文档（project_map → 模块文档 → 子模块文档三阶段流程） |

Skill 文件随 Python 包分发（`src/codesense_v1/skills/`），版本与服务始终对齐；若内容未变则跳过写入，不产生额外开销。同时通过 MCP Prompts 协议（`prompts/list` / `prompts/get`）对外暴露，供支持该协议的客户端按需获取。

## 架构分层

```
CodeMaker Agent (Host)
        │ spawn stdio
        ▼
┌─────────────────────────────────────────────┐
│ L1 入口层      server/         MCP stdio 服务  │
│ L2 注册/分发层 registry/       工具注册与派发   │
│ L3 工具层      tools/          project_map 等  │
│ L6 摘要层      summarizer/     结构数据 → prompt│
│ L4 数据层      data/           查询 CodeGraph DB│
│ L7 基础设施    cache/ errors   .codesense/ 读写 │
└─────────────────────────────────────────────┘
        │ 只读
        ▼
.codegraph/codegraph.db   (CodeGraph 生成)
.codesense/               (CodeSense 缓存)
```

## 项目结构

```
src/codesense_v1/
├── server/        # L1 MCP stdio 入口（list_tools / call_tool / list_prompts / get_prompt）
├── registry/      # L2 @tool 注册、JSON Schema 校验、派发
├── tools/         # L3 project_map / explore_module / explore_submodule / save_* / submit_*
├── skills/        # 内置 Skill 文件（启动时写入 .claude/skills/，MCP Prompts 协议备用）
├── summarizer/    # L6 将 Data Layer 数据拼装为 Markdown prompt
├── data/          # L4 查询 CodeGraph SQLite（modules / architecture / docstrings / files ...）
├── cache/         # L7 .codesense/ 读写、DB hash 计算、缓存失效判断
└── errors.py      # 统一异常（ToolError 体系）
```

## 环境要求

- Python >= 3.14
- [uv](https://github.com/astral-sh/uv)（推荐）
- 目标仓库需先用 CodeGraph 生成 `.codegraph/codegraph.db`

## 安装

```bash
uv sync
```

## 运行

CodeSense 以 MCP stdio 服务方式运行，由宿主 Agent（如 CodeMaker）拉起。

在 MCP 客户端配置文件中注册（CodeMaker 路径示例：`%APPDATA%\Code\User\globalStorage\techcenter.codemaker\settings\codemaker_mcp_settings.json`）：

```json
{
  "mcpServers": {
    "codesense": {
      "command": "codesense",
      "args": [],
      "type": "stdio",
      "disabled": false,
      "autoApprove": true,
      "timeout": 180,
      "env": {
        "CODESENSE_PROJECT_ROOT": "e:\\Python_Project\\CodeSense_V1"
      }
    }
  }
}
```

> `command` 为已安装的 `codesense` 可执行入口；`CODESENSE_PROJECT_ROOT` 按实际项目路径调整，其余配置项在 `.codesense/.codesense_config` 中设置（见下方）。本地开发也可用 `uv run codesense` 直接启动。

## 项目根目录解析

按优先级三级回退：

1. 环境变量 `CODESENSE_PROJECT_ROOT`（显式指定，最高优先级）
2. MCP `roots/list`（IDE 工作区根目录）
3. 从当前工作目录向上查找 `.codegraph/codegraph.db`

## 环境变量

只有一个必填项：

| 变量 | 说明 |
|------|------|
| `CODESENSE_PROJECT_ROOT` | 显式指定项目根目录（最高优先级，推荐在 MCP env 中设置） |

其余配置项统一在 `.codesense/.codesense_config` 中管理（首次启动自动生成模板）：

## 项目配置文件（`.codesense/.codesense_config`）

首次启动时自动在项目的 `.codesense/` 目录下生成配置文件模板，可按需编辑：

```json
{
  "cache_auto_expire": true,
  "extract_docstrings": true,
  "include_dirs": [],
  "ref_docs": {
    "comment": "参考文档路径列表（可以是文件或目录），用于分析时注入到 prompt 中，帮助 AI 理解项目背景",
    "paths": [],
    "recursive": false
  },
  "ignore_docs": {
    "comment": "分析时需要排除的路径（可以是文件或目录），这些路径下的代码不会被分析",
    "paths": []
  }
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `cache_auto_expire` | `true` | `false` 时始终使用旧缓存，不自动失效 |
| `extract_docstrings` | `true` | `false` 时关闭函数/类 docstring 抽取 |
| `include_dirs` | `[]`（自动推断） | 指定作为顶层模块的目录（逗号分隔字符串列表） |
| `ref_docs.paths` | `[]` | 参考文档路径列表（文件或目录），注入到 prompt 辅助分析 |
| `ref_docs.recursive` | `false` | `true` 时递归扫描 `ref_docs.paths` 中的目录 |
| `ignore_docs.paths` | `[]` | 分析时排除的路径列表（精确路径，文件或目录） |

## 开发

```bash
uv run pytest        # 运行测试
uv run mypy          # 类型检查（strict）
uv run ruff check    # Lint
```

## 许可

内部项目。
