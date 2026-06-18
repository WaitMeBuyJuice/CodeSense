# CodeSense_V1 — 项目概要（答疑用）

> 本文件用于在新对话中快速建立项目背景。先读这份文件，再提具体问题。
> 完整背景请参考：
> - `doc/vibecoding_rules/codesense-intern-project-plan.md`（六周总计划）
> - `doc/Week3/week3_handoff.md`（Week 1/2 已完成事项）

---

## 1. 项目一句话定位

**CodeSense_V1** 是一个 Python MCP Server，读取 CodeGraph 已构建的代码知识图谱，用 LLM 加工成"架构层面的语义描述"，通过 MCP Resource（被动注入）和 MCP Tool（主动调用）暴露给 AI Agent，让 AI 不需要主动探索就能获得项目全局/模块级理解。

**核心目标**：解决 AI 编程助手"浅层理解"问题——即使有 CodeGraph 也只做点状搜索，缺乏架构认知。

---

## 2. 当前进度（2026-06-15）

| 阶段 | 状态 |
|------|------|
| Week 1：认知建立 + CodeGraph 体验 | ✅ 完成 |
| Week 2：项目骨架 + Data Layer | ✅ 完成 |
| Week 3：project_map + explore_module 实现 | ✅ 完成（111 测试通过，已在 CodeMaker 中验证） |
| Week 4：MCP Instructions + Skill + 集成测试 | ⏳ 未开始 |
| Week 5：对比实验 + 效果评估 | ⏳ 未开始 |
| Week 6：总结 + Slides + Demo | ⏳ 未开始 |

---

## 3. 技术栈

| 项 | 选型 |
|----|------|
| 语言 | Python 3.14（Windows） |
| MCP SDK | `mcp==1.27.2`（官方 Python SDK） |
| 传输 | stdio |
| LLM | OpenAI 兼容 API（中转网关 `https://api.gemai.cc/v1`，模型 `deepseek-v4-flash`） |
| 数据源 | CodeGraph 的 SQLite DB（`<project>/.codegraph/codegraph.db`） |
| 依赖管理 | uv + `pyproject.toml` |
| 测试 | pytest + pytest-asyncio（`asyncio_mode=auto`） |
| 静态检查 | `mypy --strict` 零错误 + `ruff check`（line-length=100，select E/F/I/B/UP） |
| 安装方式 | `uv tool install --editable .`，命令行入口 `codesense_v1` |

---

## 4. 架构分层（当前实现）

```
src/codesense_v1/
├── server.py              # L1 入口：MCP Server 启动 + stdio + 回调绑定
├── registry.py            # L2 注册/分发：@tool 装饰器 + jsonschema 校验 + 错误兜底
├── schemas.py             # L4 基础设施：JSON Schema 常量
├── errors.py              # L4 基础设施：ToolError / LLMError 体系
├── llm.py                 # L7 基础设施：OpenAI 兼容 API 封装（环境变量配置）
├── cache.py               # L7 基础设施：.codesense/ 读写 + DB hash 计算
├── summarizer.py          # L6 协调：Data Layer + Cache + LLM，生成 Markdown 摘要
├── tools/
│   ├── add.py             # L3 工具：演示用 add(a, b)
│   └── explore_module.py  # L3 工具：MCP Tool — 模块级架构理解
├── resources/
│   └── project_map.py     # L5 Resource：MCP Resource — 项目级架构概览
└── data/                  # Data Layer（Week 2 完成）
    ├── db.py              #   CodeGraph DB 只读封装
    ├── files.py           #   list_files + directory_tree
    ├── modules.py         #   list_modules + module_dependencies
    └── aggregate.py       #   directory_dependencies（按 max_depth 聚合）
```

**依赖方向**（单向无环）：
```
server → registry → tools/explore_module ──► summarizer → llm
                  → resources/project_map ──►           ↘ cache
                                                         ↘ data/*
```

---

## 5. 两个核心功能

### 5.1 `project_map`（MCP Resource，被动注入）

- **URI**：`codesense://project_map`
- **MIME**：`text/markdown`
- **职责**：项目整体架构概览（模块列表 + 每模块一句话 + 跨模块依赖关系）
- **触发**：AI 连接 Server 时自动可读，无需主动调用
- **数据流**：CodeGraph DB → Data Layer（list_modules + module_dependencies）→ 拼 Markdown prompt → LLM → Markdown 摘要 → 缓存到 `.codesense/project_map.md`

### 5.2 `explore_module`（MCP Tool，主动调用）

- **签名**：`explore_module(module_path: str) -> str`
- **参数**：相对于 `CODESENSE_PROJECT_ROOT` 的目录路径，如 `src/codesense_v1/data`
- **职责**：返回该模块的 Markdown 描述（一句话描述 + 对外接口列表 + 内部子模块 + 依赖模块）
- **模块边界**：目录必须含 `__init__.py`（Python 包）
- **公开接口定义**：函数/类名不以 `_` 开头
- **数据流**：参数校验 → CodeGraph DB → 提取该模块下文件/符号/依赖 → 拼 Markdown prompt → LLM → 缓存到 `.codesense/modules/<module_key>.json`

---

## 6. 缓存设计（`.codesense/`）

```
<project_root>/.codesense/
├── project_map.md             # project_map 的 LLM 输出
├── modules/
│   └── <module_key>.json      # {module_path, summary, generated_at}
└── meta.json                  # {db_hash, generated_at}
```

**Lazy 失效策略**：
- 每次工具调用前计算当前 `codegraph.db` 的 SHA-256，与 `meta.json` 中 `db_hash` 对比
- **DB hash 一致**（项目未重新索引）：
  - 命中缓存 → 直接返回
  - 未命中（首次查询某模块）→ 仅生成该模块缓存，其他缓存保留
- **DB hash 不一致**（项目重新索引过）：
  - 全量 `invalidate()`（清空 `.codesense/` 内所有内容）
  - 重新生成本次请求的内容并写回

> **历史 Bug**（已修复）：曾经把 `invalidate()` 放在 `if is_cache_valid` 之外，导致同一 hash 下首次查询新模块也会清空其他模块的缓存。当前版本已改为 `else: invalidate()`。

---

## 7. 配置与运行时

### 环境变量（通过 MCP 配置的 `env` 字段传入）

| 变量 | 说明 |
|------|------|
| `CODESENSE_PROJECT_ROOT` | 目标项目根目录（决定去哪里找 `.codegraph/codegraph.db` 和 `.codesense/`） |
| `CODESENSE_LLM_API_KEY` | LLM API Key（必填） |
| `CODESENSE_LLM_BASE_URL` | LLM Base URL（默认 `https://api.gemai.cc/v1`） |
| `CODESENSE_LLM_MODEL` | LLM 模型名（默认 `deepseek-v4-flash`） |

### CodeMaker MCP 配置示例

```json
"codesense_v1": {
  "command": "codesense_v1",
  "args": [],
  "env": {
    "CODESENSE_PROJECT_ROOT": "E:/Python_Project/CodeSense_V1",
    "CODESENSE_LLM_API_KEY": "sk-...",
    "CODESENSE_LLM_BASE_URL": "https://api.gemai.cc/v1",
    "CODESENSE_LLM_MODEL": "deepseek-v4-flash"
  },
  "type": "stdio",
  "disabled": false,
  "autoApprove": true
}
```

### 用户首次安装

```bat
uv tool install --editable "E:\Python_Project\CodeSense_V1"
```

> 加新依赖（如 Week 3 加 `openai`）后必须 `--reinstall`，否则 `codesense_v1.exe` 隔离环境模块缺失。

---

## 8. 错误处理约定

- 业务/校验错误统一抛 `ToolError` 子类（`InvalidArgumentError` / `LLMError` / `ValidationError`）
- 文案模板：`"参数错误：..."` / `"未知工具：..."` / `"内部错误：<ExcType>"`
- 工具错误：`registry.dispatch` 兜底捕获 → MCP `isError=true` 响应
- Resource 错误：**不**用 MCP 错误机制，而是返回包含错误描述的 Markdown 字符串（避免破坏被动注入语义）

---

## 9. vibecoding 流程产物

```
doc/
├── stack.md                            # 技术栈定义
├── usage_codemaker.md                  # CodeMaker 接入说明
├── vibecoding_rules/
│   ├── vibecoding_rules.md             # 7 步 vibecoding 模板
│   └── codesense-intern-project-plan.md# 六周总计划
├── Week2/                              # add demo + Data Layer 全套（requirement/design/tasks/prompts）
└── Week3/                              # project_map + explore_module 全套
    ├── requirement.md
    ├── design/
    │   ├── overview.md
    │   ├── cache.md / llm.md / summarizer.md
    │   ├── resources_project_map.md / tools_explore_module.md
    ├── tasks/                          # 8 个任务，全部 [x] 完成
    ├── prompts/                        # 8 个独立任务 prompt + index.md
    ├── week3_handoff.md                # Week 1/2 → Week 3 前情提要
    └── MCP服务工具测试手册.md          # 端到端验证手册
```

---

## 10. 测试现状

- **单元 + 集成测试**：`uv run pytest -q` → **111 passed**
  - `test_registry.py`（14）/ `test_add.py`（15）/ `test_mcp_integration.py`（9）— Week 2
  - `test_data_*.py` — Week 2 Data Layer
  - `test_cache.py`（20）/ `test_llm.py`（9）/ `test_summarizer.py`（11）— Week 3
  - `test_resources_project_map.py`（6）/ `test_explore_module.py`（8）— Week 3
- **CodeMaker 端到端**：在 CodeSense_V1 自身仓库上验证通过
  - `project_map` Resource：成功返回项目架构 Markdown
  - `explore_module`：对各子模块（`src/codesense_v1`、`src/codesense_v1/data`、`src/codesense_v1/tools`）均正常返回
  - 缓存策略：同 hash 下查询不同模块互不覆盖

---

## 11. 已知设计取舍 / 局限性（可作为提问切入点）

| # | 取舍 | 理由 |
|---|------|------|
| T1 | 缓存粒度 = project 级（一个 db_hash） | 简单可靠；不用维护每模块独立 hash |
| T2 | DB 变化触发全量重生 | 避免部分失效导致 project_map 与 module 摘要不一致 |
| T3 | 模块边界 = `__init__.py` | 仅支持 Python 包；TypeScript / 其他语言暂未支持 |
| T4 | LLM 失败不重试 | 保持简单，错误直接暴露给 AI（让 AI 自己决定重试） |
| T5 | `project_root` 通过环境变量传入 | 一个 MCP Server 实例只服务一个项目；不支持多项目切换 |
| T6 | Resource 错误返回 Markdown 而非 MCP error | 保证被动注入语义不被破坏 |
| T7 | LLM Provider 用中转网关而非官方 OpenAI | 公司环境与可用性考虑（原计划 `deepseek-v4-pro` 不可用，切到 `flash`） |
| T8 | 没有 LSP / CodeMap 集成 | Stretch goals 仅做调研，未实现 |

---

## 12. 待办（按 Week 计划）

- **Week 4**：写 MCP Server `instructions`、Skill 文件（引导 AI"先看全局 → 再看模块 → 再看细节"工作流）；端到端集成测试观察 AI 行为变化
- **Week 5**：三组对比实验（无 CG / 有 CG / 有 CG+CS），量化 AI 工具调用次数、模块边界识别准确率等
- **Week 6**：总结文档、汇报 Slides、Demo

---

## 13. 提问建议

可以从以下角度切入：
- **设计层面**：第 11 节任一取舍 T1~T8 的权衡
- **实现细节**：缓存策略、prompt 构建、错误处理、MCP SDK 兼容性
- **测试与质量**：覆盖率、mock 策略、集成测试陷阱（如 anyio cancel scope）
- **效果评估**：如何衡量 CodeSense 的真实价值
- **扩展方向**：多语言支持、增量更新、多项目隔离、与 CodeMap/LSP 整合
