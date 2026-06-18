# CodeSense_V1 — Week 3 起步前情提要

> 目的：让接手 Week 3 的对话快速掌握 Week 1/2 已完成的内容、当前代码结构、外部依赖、约束与流程规约，直接进入"实现 project_map + explore_module"阶段。
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
| 命令行入口 | `codesense_v1`（已 `uv tool install --editable` 到 `C:\Users\<user>\.local\bin\codesense_v1.exe`） |
| Python | 3.14（Windows） |
| 依赖管理 | uv + `pyproject.toml` + `uv.lock` |
| 测试 | pytest + pytest-asyncio（`asyncio_mode=auto`）|
| 静态检查 | `mypy --strict`、`ruff check`（line-length=100，select E/F/I/B/UP）|

---

## 2. Week 1 完成情况（认知建立）

已交付：
- CodeGraph 原理理解（索引流程、数据模型、查询原理、局限性）
- 对比实验：有/无 CodeGraph 时 AI 的行为差异
- 差距分析：CodeGraph 能力边界 + CodeSense 设计动机

> 这些文档不在 V1 仓库内；如果 Week 3 需要回看请联系用户索取。

---

## 3. Week 2 完成情况（项目骨架 + Data Layer）

### 3.1 MCP 骨架（add demo）

通过 vibecoding 流程（步骤 0-6）完整搭建，作为"最小可工作 MCP Server"骨架与 vibecoding 流程模板。

源码结构：

```
src/codesense_v1/
├── __init__.py          # __version__ = "0.1.0"
├── errors.py            # ToolError / ValidationError / InvalidArgumentError
├── schemas.py           # ADD_INPUT_SCHEMA: Final[dict[str, object]]
├── registry.py          # @tool 装饰器 + list_tools + dispatch（永不抛异常）
├── server.py            # mcp Server + stdio_server + build_server/run_stdio/main
├── tools/
│   ├── __init__.py      # from . import add  # 触发注册
│   └── add.py           # add(a, b) -> str，NaN/Inf/溢出自检
└── data/                # ← Week 2 后期由其他对话迁移过来的 Data Layer
    ├── __init__.py
    ├── db.py            # CodeGraphDB(project_root) 上下文管理器；iter_files/iter_nodes/iter_edges/get_node/stats
    ├── files.py         # list_files + directory_tree（DirectoryNode）
    ├── modules.py       # list_modules + module_dependencies + to_file/package_dependency_dict
    └── aggregate.py     # directory_dependencies / directory_edges（按 max_depth 聚合目录）
```

测试（38/38 全绿）：
- `tests/test_registry.py`（14）
- `tests/test_add.py`（15）
- `tests/test_mcp_integration.py`（9，端到端 stdio + 官方 mcp client）

### 3.2 Data Layer 关键接口（已验证可用）

```python
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.files import list_files, directory_tree
from codesense_v1.data.modules import (
    list_modules, module_dependencies,
    to_file_dependency_dict, to_package_dependency_dict,
)
from codesense_v1.data.aggregate import directory_dependencies, directory_edges
```

- `CodeGraphDB(project_root)`：自动定位 `<project_root>/.codegraph/codegraph.db`（具体路径见 `db.py`，Week 3 实际接入前请快速复查）
- 已在两个项目上验证：
  - CodeGraph 仓库本身
  - CodeSense_V1 自身（输出在 `out/CodeSense_V1/`：`dep_facts.json`、`files_deps.json`、`module_deps.json`、`summary.txt`）

`summary.txt` 示例（自身仓库）：
```
project_root  : E:\Python_Project\CodeSense_V1
index files   : 21
index nodes   : 238
index edges   : 535
file edges    : 82 (internal=36, external=46)
  by kind     : {'imports': 72, 'calls': 10}
modules (pkgs): 5
```

### 3.3 辅助脚本

- `scripts/validate_dir_deps.py`：手工验证目录依赖输出

### 3.4 vibecoding 流程产物（在 `doc/` 下）

```
doc/
├── stack.md
├── usage_codemaker.md
├── vibecoding_rules/
│   ├── vibecoding_rules.md
│   └── codesense-intern-project-plan.md
└── Week2/
    ├── requirement.md
    ├── design/
    │   ├── overview.md
    │   ├── errors.md
    │   ├── schemas.md
    │   ├── registry.md
    │   ├── tools.md
    │   ├── server.md
    │   └── data.md
    ├── tasks/
    │   ├── progress.md（12/12 全部完成）
    │   ├── bootstrap.md / errors.md / schemas.md / registry.md / tools.md / server.md / tests.md / data.md
    └── prompts/
        ├── index.md
        └── B-1 / B-2 / B-3 / E-1 / S-1 / R-1 / T-1 / T-2 / SV-1 / TS-1 / TS-2 / TS-3.md
```

> **重要**：`doc/Week2/` 下的 requirement/design 目前**只覆盖 add demo**，没有覆盖 Data Layer 与 Week 3 要新增的 project_map / explore_module。Week 3 需要为新功能补 stack 增量（如有）→ requirement → design → tasks → prompts → 执行。

---

## 4. Week 3 任务（来自总计划）

**目标**：实现两个核心功能

任务：
- 设计 LLM prompt（输入结构数据 → 输出架构摘要）
- 实现 `project_map`：LLM 调用 + 缓存 + 作为 **MCP Resource** 暴露
- 实现 `explore_module`：模块边界检测、模块内符号提取、LLM 生成模块描述（**MCP Tool**）
- `.codesense/` 目录持久化（结构见下）
- 在 CodeGraph 仓库上测试生成质量，迭代 prompt

`.codesense/` 持久化结构（来自总计划）：
```
.codesense/
├── project_map.md          # 项目整体架构摘要
├── modules/
│   ├── src_auth.json       # 模块结构 + LLM 摘要
│   └── ...
└── meta.json               # 生成时间、CodeGraph DB hash（用于 Lazy 失效检查）
```

策略：**Lazy 检查**——AI 调用工具时检查 CodeGraph DB 是否有变化（meta.json 中的 hash 对比），有变化才重新生成对应模块摘要。

---

## 5. LLM Provider（已确定）

中转网关 OpenAI 兼容协议。**真实 Key 已写入下方**，Week 3 实现时建议改读环境变量 `CODESENSE_LLM_API_KEY` / `CODESENSE_LLM_BASE_URL` / `CODESENSE_LLM_MODEL`，避免硬编码进仓库。

```python
BASE_URL = "https://api.gemai.cc/v1"
API_KEY  = "sk-0M3b4zj6lj8tvtegdDqB2LUGw4ueiFLWDMJ1JbU5Ghv566Dz"
MODEL    = "deepseek-v4-flash"
```

参考调用代码：`e:\Python_Project\API_test\test_api.py`（已跑通 chat completion）。

需要在 `pyproject.toml` 新增依赖 `openai`（uv add openai）。

> 备注：原计划用 `deepseek-v4-pro`，因不可用切到 `deepseek-v4-flash`。

---

## 6. 流程与代码规约（Week 3 必须遵守）

### 6.1 vibecoding 流程（沿用）
模板路径：`doc/vibecoding_rules/vibecoding_rules.md`

Week 3 新增模块（建议命名）：
- `cache`（`.codesense/` 读写 + meta hash）
- `llm`（OpenAI 客户端封装、prompt 模板、错误重试）
- `summarizer`（结构数据 → prompt → LLM → 摘要文本）
- `resources/project_map`（MCP Resource）
- `tools/explore_module.py`（新 Tool，按现有 `tools/add.py` 模式）

每个新模块按 vibecoding 走：requirement 增量 → design → tasks → prompts → 执行。

### 6.2 代码规约（来自现有 `pyproject.toml`）

- `mypy --strict` 零错误（注意：`dict` 必须写 `dict[str, object]`，`Callable` 用 `collections.abc`，禁用 `Union`/`Optional`，用 `X | Y`）
- `ruff check` 零警告（line-length=100；I 规则要求 import 块按 stdlib/3rd/local 分组排序）
- 所有公开符号必须类型注解
- 测试：pytest + `asyncio_mode=auto`；集成测试涉及 anyio cancel scope 时**不要用 fixture 共享 async session**，每个用例内联 `async with`（详见 `tests/test_mcp_integration.py` 的已知陷阱）

### 6.3 MCP SDK 关键点

- 版本 `mcp==1.27.2`
- `Server.call_tool` 默认会自动跑一次 `jsonschema.validate`；本项目 `registry.dispatch` 已自带校验并管理文案，所以 server.py 用 `@server.call_tool(validate_input=False)` **关掉 SDK 自带校验**，避免文案被覆写
- `Server.list_tools()` / `call_tool()` 装饰器无 type stub，需 `# type: ignore[no-untyped-call, untyped-decorator]`
- stdio_client / ClientSession 在 pytest-asyncio fixture 中共享会触发 anyio cancel scope 跨 task 报错；Week 3 写集成测试请直接内联 `async with`，不要用 module-scope async fixture

### 6.4 错误处理规范

- 业务/校验错误抛 `ToolError` 子类（`errors.py`），文案以 `"参数错误：..."` / `"未知工具：..."` / `"内部错误：<ExcType>"` 模板；不泄漏堆栈
- 新工具的语义级校验抛 `InvalidArgumentError`；不要在工具内 raise `ValidationError`（专属 registry 校验阶段）

### 6.5 工具注册流程

新增 MCP Tool 步骤：
1. `schemas.py` 加 schema 常量
2. `tools/<name>.py` 实现 + `@tool(name=..., description=..., input_schema=...)` 装饰
3. `tools/__init__.py` 加 `from . import <name>  # noqa: F401`

---

## 7. CodeMaker 接入现状

- MCP 配置文件：`c:\Users\leikaixin\AppData\Roaming\Code\User\globalStorage\techcenter.codemaker\settings\codemaker_mcp_settings.json`
- 详细使用文档：`doc/usage_codemaker.md`
- 当前用户机器上 `codesense_v1.exe` 已全局可用；用 `--editable` 安装，改源码后**重启 VSCode** 即生效
- 配置片段（用户需自行追加）：
  ```json
  "codesense_v1": {
    "command": "codesense_v1",
    "args": [],
    "timeout": 60,
    "type": "stdio",
    "disabled": false,
    "autoApprove": true
  }
  ```

---

## 8. 仍未做（Week 3 之外，仅供参考）

- Week 4：MCP Server Instructions、Skill 文件、端到端集成测试观察 AI 行为
- Week 5：三组对比实验（无 CG / 有 CG / 有 CG+CS）、指标量化
- Week 6：总结 + Slides + Demo

---

## 9. Week 3 验证对象

- **主**：CodeGraph 仓库本身（计划中指定，约 15k 行 TypeScript，模块清晰）
- **辅**：CodeSense_V1 自身（小型快验，迭代 prompt 时跑得快）

---

## 10. 给 Week 3 对话的开场建议

1. 先读本文件
2. 读 `doc/Week2/design/overview.md`（理解 add demo 的分层）和 `src/codesense_v1/data/` 各模块（Week 3 直接调用）
3. 跑一次 `uv sync && uv run pytest -q` 确认环境（应 38 passed）
4. 按 vibecoding 流程：
   - 与用户澄清 Week 3 需求（哪些字段进 project_map / explore_module、缓存粒度、失效策略细节）
   - 写 `doc/Week3/requirement.md`（Week 3 独立需求文档）
   - 详细设计：`doc/Week3/design/cache.md`、`doc/Week3/design/llm.md`、`doc/Week3/design/summarizer.md`、`doc/Week3/design/tools_explore_module.md`、`doc/Week3/design/resources_project_map.md`
   - 任务拆分 + prompts + 执行（产物放 `doc/Week3/tasks/`、`doc/Week3/prompts/`）
5. 不确定的地方**必须问用户**（vibecoding 全局规则）
