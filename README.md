# CodeSense

CodeSense 是一个 MCP（Model Context Protocol）服务，帮助 AI Agent 快速理解代码仓库的**高层架构**：项目组织方式、模块职责、内部结构以及模块间协作关系。

它读取 [CodeGraph](https://) 生成的代码知识图谱（`.codegraph/codegraph.db`），按"全局 → 模块 → 子模块"的层级，向 Agent 提供结构化的认知信息，并把生成的摘要缓存到 `.codesense/` 目录复用。

## 核心理念

CodeSense **不直接调用 LLM**。它把 Data Layer 抽取的结构数据拼装成 prompt 返回给宿主 Agent，由 Agent 生成自然语言摘要后，再通过 `save_*` / `submit_*` 工具写回缓存。这种"Agent 即 LLM"的协作模式避免了 API Key 硬编码，并让 prompt 迭代与生成解耦。

## 工具层级

由全局到细节，逐层下钻：

| 层级 | 工具 | 职责 |
|------|------|------|
| 全局 | `project_map` | 项目架构、模块分布、关键流程、跨模块依赖 |
| 模块 | `explore_module` | 模块职责、架构简析、子模块列表、上下游依赖、实现约束 |
| 子模块 | `explore_submodule` | 子模块业务职责、对外能力、跨模块依赖、典型调用链 |

配套写回工具：`submit_project_map`、`save_project_map_segment`、`save_module_summary`、`save_submodule_summary`。

进度查询：`init_status`（查看三阶段初始化完成情况）。

更细粒度的符号 / 调用链 / 原文检索，交给 codegraph MCP 或 `grep` + `read_file`。

## 内置 Skills

CodeSense 服务**启动时**自动将两个内置 Skill 写入项目的 `.claude/skills/` 目录，Agent从该目录读取后即可激活，无需手动安装：

| Skill | 适用场景 |
|-------|---------|
| `codesense-flow` | 理解项目架构、探索模块关系、修改代码前的四层递进探索工作流 |
| `codesense-init` | 首次初始化 CodeSense 知识文档（project_map → 模块文档 → 子模块文档 → Review 自校流程） |

Skill 文件随 Python 包分发（`src/codesense_v1/skills/`），版本与服务始终对齐；若内容未变则跳过写入，不产生额外开销。同时通过 MCP Prompts 协议（`prompts/list` / `prompts/get`）对外暴露，供支持该协议的客户端按需获取。

## 架构分层

```
Agent (Host)
        │ spawn stdio
        ▼
┌─────────────────────────────────────────────┐
│ L1 入口层      server/         MCP stdio 服务  │
│ L2 注册/分发层 registry/       工具注册与派发   │
│ L3 工具层      tools/          project_map 等  │
│ L4 摘要层      summarizer/     结构数据 → prompt│
│ L5 数据层      data/           查询 CodeGraph DB│
│ L6 基础设施    cache/ errors   .codesense/ 读写 │
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

### 用户安装（推荐）

使用 `uv tool install` 从 Git 仓库直接安装，无需克隆源码：

```bash
uv tool install git+https://github.com/WaitMeBuyJuice/CodeSense.git
```

安装完成后 `codesense` 命令即可使用。后续升级：

```bash
uv tool upgrade codesense-v1
```

### 开发者安装

克隆仓库后使用 `uv sync` 安装依赖：

```bash
git clone https://github.com/WaitMeBuyJuice/CodeSense.git
cd CodeSense
uv sync
```

开发模式下用 `uv run codesense` 代替 `codesense` 命令。

## 运行

CodeSense 以 MCP stdio 服务方式运行，由宿主 Agent 拉起。

在 MCP 客户端配置文件中注册：

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
        "CODESENSE_PROJECT_ROOT": "代码仓库路径"
      }
    }
  }
}
```

> `command` 为已安装的 `codesense` 可执行入口；`CODESENSE_PROJECT_ROOT` 按实际项目路径调整，其余配置项在 `.codesense/.codesense_config` 中设置（见下方）。本地开发也可用 `uv run codesense` 直接启动。

## 快速上手

### 前置条件

1. 目标仓库已用 [CodeGraph](https://) 生成代码知识图谱：
   ```bash
   codegraph init -i
   ```
   确认 `.codegraph/codegraph.db` 存在。

2. CodeSense 已安装并在 MCP 客户端中完成注册（见上方「安装」与「运行」章节）。

### 第一步：初始化知识文档（首次使用）

首次为项目启用 CodeSense 时，通知 Agent 激活 `codesense-init` Skill：

> 请使用 codesense-init Skill 为本项目初始化 CodeSense 知识文档。

Agent 会按五阶段流程自动完成：

1. **Phase 0（配置）**：询问是否有参考文档和需要忽略的路径，写入 `.codesense/.codesense_config`
2. **Phase 1（项目概览）**：生成 `project_map`（仓库定位、技术栈、模块划分、关键流程）
3. **Phase 2（模块文档）**：为每个模块生成详细文档（职责、接口、子模块、依赖）
4. **Phase 3（子模块文档）**：为每个子模块生成实现细节文档
5. **Phase 4（Review 自校）**：对照源码 / CodeGraph 核对已生成文档，修正幻觉与过时内容

初始化完成后，知识文档保存在 `.codesense/` 目录下。**建议将该目录纳入版本控制**，团队成员无需重复初始化。

### 第二步：日常使用（自动更新）

初始化完成后，无需手动维护。CodeSense 内置缓存失效机制：

- 每次 Agent 调用 `project_map` / `explore_module` / `explore_submodule` 时，CodeSense 自动检测代码库是否有变更（基于 DB hash）
- 若检测到变更，相关文档缓存自动失效，工具返回的 prompt 会引导 Agent 重新生成
- 整个过程对 Agent 透明，无需用户介入

### 第三步：探索代码（日常工作流）

日常涉及代码理解、模块定位、修改影响评估等场景时，确保 `codesense-flow` Skill 处于启用状态，Agent 会自行激活并按「全局 → 模块 → 子模块 → 符号原文」四层递进探索，在合适层级获取所需信息后即可开始工作。

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

## 卸载 / 清理

### 移除知识文档缓存

`.codesense/` 目录存放所有生成的知识文档和配置文件。如需清除缓存（重新初始化）或彻底移除，直接删除该目录即可：

```bash
# 清空缓存，下次调用工具时自动触发重新生成
rm -rf .codesense/
```

删除后 CodeSense 服务仍正常运行，再次调用工具时会返回 cache miss 并引导重新生成。

### 卸载 CodeSense 服务

```bash
uv tool uninstall codesense-v1
```

卸载后 `.codesense/` 目录和 `.claude/skills/` 中的 Skill 文件不会自动删除，如不需要可手动清理。

