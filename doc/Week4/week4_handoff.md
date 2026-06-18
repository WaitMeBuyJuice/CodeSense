# CodeSense_V1 — Week 4 起步前情提要

> 目的：让接手 Week 4 的对话快速掌握 Week 1/2/3 已完成的内容、当前代码结构、外部依赖、约束与流程规约，直接进入"MCP Instructions + Skill + 集成测试"阶段。
>
> 总执行计划参考：`doc/vibecoding_rules/codesense-intern-project-plan.md`

---

## 1. 项目身份信息

| 项 | 值 |
|----|----|
| 项目根目录 | `e:\Python_Project\CodeSense_V1` |
| Python 包名 | `codesense_v1` |
| `pyproject.toml` 项目名 | `codesense-v1` |
| MCP `SERVER_NAME` | `CodeSense` |
| 命令行入口 | `codesense_v1`（已 `uv tool install --editable` 到 `C:\Users\leikaixin\.local\bin\codesense_v1.exe`） |
| Python | 3.14（Windows） |
| 依赖管理 | uv + `pyproject.toml` + `uv.lock` |
| 测试 | pytest + pytest-asyncio（`asyncio_mode=auto`）|
| 静态检查 | `mypy --strict`、`ruff check`（line-length=100，select E/F/I/B/UP）|

---

## 2. Week 1/2 完成情况（简要）

- **Week 1**：CodeGraph 原理理解、对比实验、差距分析文档（不在 V1 仓库内）
- **Week 2**：MCP Server 骨架（add demo）+ Data Layer（从 CodeGraph DB 查文件/模块/依赖关系）

---

## 3. Week 3 完成情况（项目核心功能）

### 3.1 新增功能

| 功能 | 类型 | 状态 |
|------|------|------|
| `project_map` | MCP Resource（`codesense://project_map`） | ✅ 已实现并端到端验证 |
| `explore_module` | MCP Tool | ✅ 已实现并端到端验证 |
| LLM 调用层 | `llm/llm.py` | ✅ 完成 |
| 缓存层 | `cache/cache.py` | ✅ 完成 |
| 协调层 | `summarizer/summarizer.py` | ✅ 完成 |

### 3.2 当前源码结构

```
src/codesense_v1/
├── __init__.py
├── errors/              # 异常体系（ToolError / LLMError / InvalidArgumentError）
│   ├── __init__.py      # re-export
│   └── errors.py
├── schemas/             # JSON Schema 常量（ADD / EXPLORE_MODULE）
│   ├── __init__.py
│   └── schemas.py
├── registry/            # @tool 装饰器 + list_tools + dispatch
│   ├── __init__.py
│   └── registry.py
├── llm/                 # OpenAI 兼容 API 封装（环境变量配置）
│   ├── __init__.py
│   └── llm.py
├── cache/               # .codesense/ 读写 + DB hash + Lazy 失效
│   ├── __init__.py
│   └── cache.py
├── summarizer/          # Data Layer + Cache + LLM 协调，生成 Markdown 摘要
│   ├── __init__.py
│   └── summarizer.py
├── server/              # MCP Server 启动 + stdio + Tool/Resource 回调绑定
│   ├── __init__.py
│   ├── server.py
│   └── __main__.py
├── tools/
│   ├── __init__.py      # from . import add, explore_module
│   ├── add.py           # demo 工具
│   └── explore_module.py
├── resources/
│   ├── __init__.py
│   └── project_map.py   # MCP Resource 读取逻辑（错误返回 Markdown，不抛异常）
└── data/                # Week 2 Data Layer（不变）
    ├── __init__.py
    ├── db.py / files.py / modules.py / aggregate.py
```

> **结构变更说明**：Week 3 末期将原来的单文件模块（`llm.py`、`cache.py` 等）重构为子包形式（`llm/__init__.py` + `llm/llm.py`），以便未来在包内扩展新文件而不污染 `__init__.py`。

### 3.3 两个核心功能说明

**`project_map` Resource**：
- URI：`codesense://project_map`，MIME：`text/markdown`
- AI 连接 Server 时自动可读，返回项目整体架构 Markdown（模块列表 + 一句话描述 + 跨模块依赖）
- 错误时返回包含错误描述的 Markdown（不使用 MCP 错误机制）
- Lazy 缓存：DB hash 不变直接返回缓存，变了全量重生

**`explore_module` Tool**：
- 参数：`module_path: str`（相对于 `CODESENSE_PROJECT_ROOT` 的目录路径）
- 模块边界：目录必须含 `__init__.py`（Python 包）
- 对外接口：仅包含名称不以 `_` 开头的函数/类
- 返回：一句话描述 + 对外接口 + 内部文件 + 依赖模块（Markdown）

### 3.4 缓存设计

```
<project_root>/.codesense/
├── project_map.md
├── modules/<module_key>.json
└── meta.json  ← {"db_hash": "<sha256>", "generated_at": "..."}
```

Lazy 失效：hash 一致 → 命中缓存直接返回；hash 不一致 → `invalidate()` 全清后重生。

### 3.5 测试现状

```
111 passed（ruff + mypy --strict 零错误）
tests/test_registry.py（14）/ test_add.py（15）/ test_mcp_integration.py（9）
tests/test_cache.py（20）/ test_llm.py（9）/ test_summarizer.py（11）
tests/test_resources_project_map.py（6）/ test_explore_module.py（8）
tests/data/（其余 Data Layer 测试）
```

### 3.6 Week 3 振动流程产物

```
doc/Week3/
├── requirement.md
├── design/
│   ├── overview.md / cache.md / llm.md / summarizer.md
│   ├── resources_project_map.md / tools_explore_module.md
├── tasks/（8 个任务，全部 [x] 完成）
├── prompts/（8 个 prompt + index.md）
├── week3_handoff.md
├── MCP服务工具测试手册.md
├── project_overview_for_qa.md   # 项目概要答疑文件
├── module_boundary_redesign.md  # 单文件模块重构讨论（已实施）
└── week4_handoff.md             # 本文件
```

---

## 4. Week 4 任务（来自总计划）

**目标**：让 AI Agent 实际按预期使用 CodeSense

任务：
- [ ] 编写 MCP Server Instructions（引导 AI 理解工具分工）
- [ ] 编写 Skill 文件（定义"先看全局→再看模块→再看细节"的工作流）
- [ ] 端到端集成测试：接入 CodeMaker，观察 AI 行为
- [ ] 观察 AI 行为：是否使用 explore_module？使用后决策是否更好？
- [ ] 根据观察调整 instructions 和 skill 措辞

交付物：
- [ ] Skill 文件（CodeMaker Skill 格式）
- [ ] MCP Server Instructions（写在 `pyproject.toml` 或独立配置中）
- [ ] 集成测试记录（AI 行为观察日志）

---

## 5. Week 4 关键背景知识

### 5.1 MCP Instructions 是什么

MCP Server 可以在初始化握手时向 AI 注入一段文本（Instructions），AI 会将其作为"如何使用这组工具"的引导说明。
在 Python MCP SDK 中，通过 `Server(instructions="...")` 参数设置：

```python
server = Server(name="CodeSense", version="0.1.0", instructions="...")
```

当前 `server/server.py` 的 `build_server()` 没有传 `instructions`，Week 4 需要补上。

### 5.2 CodeMaker Skill 是什么

Skill 文件是 CodeMaker 的专有概念，定义 AI 在特定场景下的工作流程（类似 system prompt 片段）。格式参考 `doc/usage_codemaker.md` 或现有 Skill 文件。

Week 4 的 Skill 目标是引导 AI 在修改代码前遵循："先读 project_map → 再 explore_module 相关模块 → 再看具体代码"的顺序。

### 5.3 与现有工具的分工（AI 应理解的架构）

```
抽象度高 ──────────────────────────────────── 抽象度低
project_map → explore_module → codegraph_explore → grep/read_file
 全局鸟瞰     模块面           符号+邻域              精确文本
(被动注入)   (面级理解)        (点到邻域)             (原始文本)
```

这套分工逻辑需要写进 Instructions 和 Skill，让 AI 知道何时用哪个工具。

---

## 6. 流程与代码规约（Week 4 必须遵守）

### 6.1 vibecoding 流程（沿用）

模板路径：`doc/vibecoding_rules/vibecoding_rules.md`

Week 4 新增内容（建议命名）：
- `Instructions`（MCP Server 启动时注入的文字）
- `Skill`（CodeMaker Skill 文件）
- 集成测试日志（非代码，观察记录）

### 6.2 代码规约（沿用 Week 3）

- `mypy --strict` 零错误
- `ruff check` 零警告（line-length=100，select E/F/I/B/UP）
- 测试：pytest + `asyncio_mode=auto`
- 新增 MCP Tool 步骤：`schemas.py` → `tools/<name>.py` → `tools/__init__.py`

### 6.3 MCP SDK 关键点（沿用）

- 版本 `mcp==1.27.2`
- `@server.call_tool(validate_input=False)` — 关掉 SDK 自带校验
- `@server.list_resources` / `@server.read_resource` — 回调返回 `list[ReadResourceContents]`（不是 `ReadResourceResult`）
- 测试中 stdio_client/ClientSession 不共享 async fixture

### 6.4 错误处理规范（沿用）

- 业务错误：抛 `ToolError` 子类 → registry 转 `isError=true`
- Resource 错误：返回包含错误描述的 Markdown（不抛异常）

---

## 7. LLM Provider（沿用）

中转网关 OpenAI 兼容协议，通过环境变量配置：

```
CODESENSE_LLM_API_KEY  = sk-0M3b4zj6lj8tvtegdDqB2LUGw4ueiFLWDMJ1JbU5Ghv566Dz
CODESENSE_LLM_BASE_URL = https://api.gemai.cc/v1
CODESENSE_LLM_MODEL    = deepseek-v4-flash
```

---

## 8. CodeMaker 接入现状

- MCP 配置文件：`c:\Users\leikaixin\AppData\Roaming\Code\User\globalStorage\techcenter.codemaker\settings\codemaker_mcp_settings.json`
- 详细使用文档：`doc/usage_codemaker.md`
- 当前配置（`disabled: false`，已验证可用）：

```json
"codesense_v1": {
  "command": "codesense_v1",
  "env": {
    "CODESENSE_PROJECT_ROOT": "E:/Python_Project/CodeSense_V1",
    "CODESENSE_LLM_API_KEY": "sk-0M3b4zj6lj8tvtegdDqB2LUGw4ueiFLWDMJ1JbU5Ghv566Dz",
    "CODESENSE_LLM_BASE_URL": "https://api.gemai.cc/v1",
    "CODESENSE_LLM_MODEL": "deepseek-v4-flash"
  },
  "args": [],
  "timeout": 60,
  "type": "stdio",
  "disabled": false,
  "autoApprove": true
}
```

- 改源码后：`uv tool install --editable . --reinstall`，重启 VSCode 生效

---

## 9. 仍未做（Week 4 之外，仅供参考）

- Week 5：三组对比实验（无 CG / 有 CG / 有 CG+CS）、指标量化
- Week 6：总结 + Slides + Demo

---

## 10. Stretch Goals（记录，不在 Week 4 范围内）

- **单文件独立模块检测**（Step 1 of `docs/module_cohesion_detection.md`）：对目录下每个 `.py` 文件判断"被目录外 import 且不依赖同目录兄弟" → 视为隐藏独立模块，可单独 explore。实现简单（~20 行），但不急，放后续。
- **包内聚度评分**（Step 2）：三维度算分，主观权重难定，价值存疑，暂不做。
- **CodeGraph MCP 代理** — 合并为一个 server
- **Watch 机制** — 监听文件变化实时更新缓存
- **多粒度 explore** — 支持递归展开子模块（`max_depth` 参数）

---

## 11. 给 Week 4 对话的开场建议

1. 先读本文件
2. 读 `doc/vibecoding_rules/codesense-intern-project-plan.md`（Week 4 任务原文）
3. 读 `src/codesense_v1/server/server.py`（了解当前 Server 结构，Instructions 加在这里）
4. 跑一次 `uv run pytest -q` 确认环境（应 111 passed）
5. 按 vibecoding 流程（`doc/vibecoding_rules/vibecoding_rules.md`）：
   - 与用户澄清 Week 4 需求（Instructions 内容、Skill 格式、集成测试评估标准）
   - 写 `doc/Week4/requirement.md`
   - 设计 → 任务拆分 → prompts → 执行
6. 不确定的地方**必须问用户**
