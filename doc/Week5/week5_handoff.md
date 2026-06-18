# CodeSense_V1 — Week 5 起步前情提要

> 目的：让接手 Week 5 的对话快速掌握 Week 1–4 已完成的内容、当前代码结构、外部依赖、约束与流程规约，直接进入"三组对比实验"阶段。
> 
> 总执行计划参考：`doc/vibecoding_rules/codesense-intern-project-plan.md`

---

## 1. 项目身份信息

| 项                    | 值                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| 项目根目录                | `e:\Python_Project\CodeSense_V1`                                                                  |
| Python 包名            | `codesense_v1`                                                                                    |
| `pyproject.toml` 项目名 | `codesense-v1`                                                                                    |
| MCP `SERVER_NAME`    | `CodeSense`                                                                                       |
| 命令行入口                | `codesense_v1`（已 `uv tool install --editable` 到 `C:\Users\leikaixin\.local\bin\codesense_v1.exe`） |
| Python               | 3.14（Windows）                                                                                     |
| 依赖管理                 | uv + `pyproject.toml` + `uv.lock`                                                                 |
| 核心运行时依赖              | `mcp`（版本 1.27.2）、`jsonschema`、`openai>=2.41.1`                                                    |
| 测试                   | pytest + pytest-asyncio（`asyncio_mode=auto`）                                                      |
| 静态检查                 | `mypy --strict`（python_version=3.14）、`ruff check`（line-length=100，select E/F/I/B/UP）              |

---

## 2. 上一阶段（含此前所有阶段）已完成情况

### Week 1（不在本仓库内）

- CodeGraph 原理理解文档、对比实验报告、差距分析文档
- 验证证据：文档存放于 `E:\Python_Project\CodeSense_Learn\Week1`（仓库外）

### Week 2 完成情况

**交付物**：

- 可运行的 MCP Server 骨架（agent 能连接）
- Data Layer：从 CodeGraph SQLite DB 查询文件、模块、跨模块依赖

**关键源码**：

```
src/codesense_v1/
├── data/db.py            # CodeGraphDB：iter_files/iter_nodes/iter_edges/get_node/stats
├── data/files.py         # list_files / directory_tree / DirectoryNode
├── data/modules.py       # list_modules / module_dependencies / Module / ModuleEdge
├── data/aggregate.py     # directory_dependencies / directory_edges
├── errors/errors.py      # ToolError / ValidationError / InvalidArgumentError / LLMError
├── registry/registry.py  # @tool 装饰器 + list_tools() + dispatch()
├── schemas/schemas.py    # ADD_INPUT_SCHEMA（Week 2 仅有 add）
├── tools/add.py          # demo 工具 add(a, b) -> str
└── server/server.py      # build_server() / run_stdio() / main()
```

**测试数**：Week 2 末期约 38 passed（现已合并入 111，不再单独追踪）

### Week 3 完成情况

**交付物**：

- `project_map` MCP Resource（`codesense://project_map`，MIME `text/markdown`）
- `explore_module` MCP Tool
- LLM 调用层 / 缓存层 / 协调（Summarizer）层

**关键源码新增**：

```
src/codesense_v1/
├── llm/llm.py            # call_llm(prompt: str) -> str（OpenAI 兼容）
├── cache/cache.py        # db_hash/is_cache_valid/read_project_map/write_project_map/
│                         #   read_module/write_module/invalidate/module_key
├── summarizer/summarizer.py # project_map_summary / module_summary
├── resources/project_map.py # RESOURCE_URI/NAME/DESCRIPTION/MIME_TYPE + read_project_map()
└── tools/explore_module.py  # explore_module(module_path: str) -> str
```

**缓存结构**（`<project_root>/.codesense/`）：

```
.codesense/
├── project_map.md
├── modules_index.json           # {"generated_at", "modules": [{name, description, directories, files}]}
├── modules/<safe_key>.json      # {"module_name", "summary", "generated_at"}
└── meta.json                    # {"db_hash": "<sha256>", "generated_at": "..."}
```

Lazy 失效：hash 一致 → 命中缓存；hash 不一致 → `invalidate()` 全清后重生。  
`write_modules_index` 写入时额外清空 `modules/` 子缓存（防止模块名变动导致孤儿缓存）。

**验证证据**：`uv run pytest -q` → 111 passed（见下节）

**设计文档**：`doc/Week3/design/`（overview/cache/llm/summarizer/resources_project_map/tools_explore_module）

### Week 4 完成情况（刚完成）

**交付物清单**：

| 交付物                     | 路径                                                                   | 状态             |
| ----------------------- | -------------------------------------------------------------------- | -------------- |
| MCP Server Instructions | `src/codesense_v1/server/server.py`（`SERVER_INSTRUCTIONS` 常量，L17–41） | ✅              |
| CodeMaker Skill 文件      | `.codemaker/skills/codesense-workflow/SKILL.md`                      | ✅ 已安装，已验证可自动激活 |
| Skill 交付物文档             | `doc/Week4/codesense_skill.md`                                       | ✅              |
| 集成测试观察日志                | `doc/Week4/CodeSense_Agent行为观察总结.md`                                 | ✅              |
| 集成测试记录（原始）              | `doc/Week4/CodeSense_集成测试记录.md`                                      | ✅              |

**MCP Server Instructions 关键内容**（`server.py:17-41`）：

- 说明 CodeSense 与 CodeGraph 的分工（语义层 vs 结构层）
- `project_map` 已自动注入，无需主动调用
- `explore_module` 在修改模块前调用
- 决策指引：新任务→看 project_map / 要改模块→先 explore_module / 查调用链→CodeGraph / 查精确代码→grep

**Skill 格式**：YAML Frontmatter + `## Instructions / ## Examples / ## Notes`，文件名 `SKILL.md`，放在 `.codemaker/skills/<skill-name>/` 下。

**集成测试结论**（3 组，详见 `doc/Week4/CodeSense_Agent行为观察总结.md`）：

| 组别            | Skill | explore_module 调用               | 任务结果   |
| ------------- | ----- | ------------------------------- | ------ |
| 场景A + 开Skill  | ✅     | ✅ 主动调用1次 + codegraph_callers 4次 | ✅ 全部通过 |
| 场景A + 未开Skill | ❌     | ❌ 未调用（退回 grep+文件遍历）             | ✅ 全部通过 |
| 场景B + 开Skill  | ✅     | ✅ 主动调用2次                        | ✅ 全部通过 |

**核心结论**：`project_map`（被动注入）无论是否开 Skill 都被使用；`explore_module`（主动工具）**高度依赖 Skill 引导**，仅靠 Instructions 建议性措辞不足以稳定触发。

**计划外代码**（集成测试期间 AI 自动创建，已确认为实验产物，不计入交付物）：

- `src/codesense_v1/tools/list_cached.py`（`list_cached` 工具）
- `src/codesense_v1/tools/list_cached_modules.py`（`list_cached_modules` 工具）
- 两者已注册到 `tools/__init__.py` 和 `schemas.py`，功能可用但**无测试覆盖**
- Week 5 可选：补测试或清理，视需要决定

**测试数**：`uv run pytest -q` → **111 passed**（mypy --strict 零错误，ruff check 零警告，2026-06-16 验证）

---

### Week 5 前置改动（2026-06-17，Week 5 正式开始前完成，不计入 Week 4 交付物）

> **背景**：Week 4 集成测试暴露 `explore_module` 依赖 `__init__.py` 判断模块边界，导致 TypeScript / Go 等非 Python 项目直接报错。Week 5 对比实验需要在 codegraph-main（TypeScript）上运行，因此在进入实验前先把模块界定机制改造为语言无关的 LLM 推断方式。
> 
> 详细设计文档：`doc/Week4/LLM模块界定实现.md`  
> 实验验证记录：`doc/Week5/LLM模块界定实验.md`

#### 核心变更

**1. `explore_module` 入参：`module_path` → `module_name`**

|       | 旧                                     | 新                                           |
| ----- | ------------------------------------- | ------------------------------------------- |
| 参数名   | `module_path: str`（目录路径，如 `src/auth`） | `module_name: str`（LLM 给出的模块名，如 `缓存层`）      |
| 校验    | 检查目录存在 + `__init__.py` 存在             | 在 `modules_index.json` 中按名查找（trim + 大小写不敏感） |
| 找不到时  | 报"路径不存在"或"不是 Python 包"                | 报"模块不存在"并列出可用模块名                            |
| 索引缺失时 | 不涉及                                   | 报"请先读取 codesense://project_map"             |

**2. `project_map_summary` 重构（两步替代原一步）**

原来：一次 LLM 调用生成 Markdown 概览（无结构化数据）  
现在：

1. 第一次调用：LLM 输出**竖线分隔文本**（`模块名|职责|目录`，每行一个模块），解析为结构化模块列表
2. 用结构化数据展开文件列表（`directories → files`），写入 `.codesense/modules_index.json`
3. 代码**模板渲染** Markdown（不再调 LLM），写入 `project_map.md`

切换为竖线文本原因：JSON 输出在大项目（~200 文件）下 LLM 频繁遗漏逗号，改为每行独立的文本格式后失败率大幅降低（单行坏了跳过，不影响其他行）。

**3. 缓存结构变更**

```
.codesense/
├── project_map.md              ← 不变（Markdown 概览）
├── modules_index.json          ← 【新增】结构化模块映射
│                               #   {"generated_at", "modules": [{name, description, directories, files}]}
├── modules/<safe_key>.json     ← module summary 缓存（key 规则变更）
└── meta.json                   ← 不变 {"db_hash", "generated_at"}
```

`modules_index.json` 新增语义：

- `project_map` 生成时写入；`explore_module` 读取此文件查找模块名→文件映射
- `write_modules_index` 写入时**同步清空** `modules/` 子缓存（防止旧 module summary 与新模块名不一致）
- `invalidate()` 同时删除 `modules_index.json`

**4. 模块 key 生成规则变更：`module_key(path)` → `safe_key(name)`**

|     | 旧                                       | 新                                         |
| --- | --------------------------------------- | ----------------------------------------- |
| 函数  | `module_key("src/auth")` → `"src_auth"` | `safe_key("缓存层")` → `sha1[:12]`（12 位十六进制） |
| 输入  | 目录路径                                    | 模块名（trim + lower 后 hash）                  |
| 可读性 | 文件名可读                                   | 文件名不可读（但 `modules_index.json` 中反查）        |

`module_key` 函数**保留不删**（旧代码中仍引用），新代码改用 `safe_key`。

**5. 新增数据层函数 `directory_symbols`**

位置：`data/aggregate.py`  
作用：按目录聚合符号列表（`name / kind / file`），给 `project_map_summary` 的 LLM prompt 用  
参数：`max_per_dir=50`（防 token 超限）

**6. `_build_module_prompt` 补充真实符号**

旧版只传文件列表，LLM 猜测接口（幻觉）；新版在 `module_summary` 里先查 `db.iter_nodes()` 取该模块实际符号，拼入 prompt，并加提示"仅列出下方实际存在的符号，不要编造"。

**7. Skill 同步更新**

`.codemaker/skills/codesense-workflow/SKILL.md` 中对 `explore_module` 的描述由"传目录路径 + 需有 `__init__.py`"改为"传 project_map 中列出的模块名"。

#### 代码改动范围

| 文件                                              | 变更类型                                                                                                                                                       |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/codesense_v1/data/aggregate.py`            | 新增 `directory_symbols` 函数                                                                                                                                  |
| `src/codesense_v1/cache/cache.py`               | 新增 `safe_key` / `read_modules_index` / `write_modules_index`；`write_module` 改 `module_name` 字段；`invalidate` 增删 `modules_index.json`                        |
| `src/codesense_v1/cache/__init__.py`            | 导出新函数                                                                                                                                                      |
| `src/codesense_v1/summarizer/summarizer.py`     | 完全重写 `project_map_summary` / `module_summary`；新增 `_call_llm_for_modules` / `_parse_modules_text` / `_expand_module_files` / `_render_project_map_markdown` |
| `src/codesense_v1/schemas/schemas.py`           | `EXPLORE_MODULE_INPUT_SCHEMA` 的 `module_path` 改为 `module_name`                                                                                             |
| `src/codesense_v1/tools/explore_module.py`      | 入参改 `module_name`，删除目录/`__init__.py` 校验                                                                                                                    |
| `.codemaker/skills/codesense-workflow/SKILL.md` | 更新 `explore_module` 使用说明                                                                                                                                   |
| `tests/test_data_aggregate.py`                  | 新增 `directory_symbols` 测试                                                                                                                                  |
| `tests/test_cache.py`                           | 新增 `safe_key` / `read_modules_index` / `write_modules_index` 测试，更新 `write_module` 断言                                                                       |
| `tests/test_summarizer.py`                      | 完全重写（JSON mock → 竖线文本 mock）                                                                                                                                |
| `tests/test_explore_module.py`                  | 完全重写（`module_path` → `module_name`，删除路径/包检查测试）                                                                                                             |
| `pyproject.toml`                                | 新增依赖 `json-repair>=0.30`（可选，import 失败时静默跳过）                                                                                                                |

**测试数**：`uv run pytest -q` → **142 passed**（mypy --strict 零错误，ruff check 零警告，2026-06-17 验证）

---

## 3. 下一阶段任务（Week 5）

### 原文摘抄（来自 `doc/vibecoding_rules/codesense-intern-project-plan.md`）

> **Week 5：效果评估 + 对比实验**
> 
> 目标：证明/证伪 CodeSense 的实际效果
> 
> 任务：
> 
> - [ ] 设计对比实验：选 2-3 个跨模块修改任务，分三组跑：
>   - 纯 grep/read（无 CodeGraph、无 CodeSense）
>   - 有 CodeGraph、无 CodeSense
>   - 有 CodeGraph + CodeSense
> - [ ] 记录指标：AI 工具调用次数、是否正确识别模块边界、修改是否破坏依赖、代码是否符合现有模式
> - [ ] 分析 project_map 和 explore_module 对 AI 决策的实际影响
> - [ ] 根据实验结果调优 prompt 和 instructions（最后一轮迭代）
> - [ ] 基本错误处理（CodeGraph DB 不存在时给清晰提示即可，不追求完美）
> 
> 交付物：
> 
> - [ ] 三组对比的实验数据和分析
> - [ ] 结论：CodeSense 在什么场景有效、什么场景无效

### 人话翻译

**做什么**：设计 2-3 个"跨模块修改"任务，在相同任务上分别用"纯 grep"、"有 CodeGraph"、"有 CodeGraph+CodeSense" 三种配置让 AI 来做，记录指标、写分析报告。最后根据实验结果微调 prompt 和 Instructions 措辞。

**验证项目**（两个）：

1. **CodeSense_V1 本身**（`e:\Python_Project\CodeSense_V1`）
2. **CodeGraph 源码**（`E:\Python_Project\codegraph-main`，TypeScript，已下载）

**明确不做**：

- 不新增 MCP Tool / Resource
- 不做大规模重构
- 错误处理只补"DB 不存在时的清晰提示"，不追求完美
- Week 6 的 Slides 和 Demo 不在本周范围

**三组实验配置**：

| 组号     | MCP 服务配置                     | CodeMaker 设置                |
| ------ | ---------------------------- | --------------------------- |
| 组1（基准） | 关闭 codegraph 和 codesense_v1  | 无 Skill                     |
| 组2     | 开启 codegraph，关闭 codesense_v1 | 无 Skill                     |
| 组3     | 开启 codegraph + codesense_v1  | 开启 codesense-workflow Skill |

**关键指标**（每组每任务记录）：

1. AI 工具调用次数及类型
2. 是否正确识别需修改的模块（无遗漏、无越界）
3. 修改是否破坏现有测试（`uv run pytest -q`）
4. 是否符合现有代码模式（命名、结构、类型注解）
5. 是否主动使用 `explore_module`（仅组3有机会）

---

## 4. 外部依赖与凭据

### LLM API

| 项           | 值                                                    |
| ----------- | ---------------------------------------------------- |
| 环境变量        | `CODESENSE_LLM_API_KEY`                              |
| 占位符         | `SK-xxxx`（**建议使用环境变量，不要硬编码**）                        |
| Base URL 变量 | `CODESENSE_LLM_BASE_URL`，值 `https://api.gemai.cc/v1` |
| 模型变量        | `CODESENSE_LLM_MODEL`，值 `deepseek-v4-flash`          |
| 协议          | OpenAI 兼容                                            |

> ⚠️ 真实 API Key 不写入文档。使用时通过 `codemaker_mcp_settings.json` 的 `env` 字段注入。

### CodeGraph 依赖

- CodeSense 读取 CodeGraph 生成的 SQLite DB（路径：`<project_root>/.codegraph/codegraph.db`）
- CodeGraph MCP Server 需单独启动（`codegraph serve --mcp`）
- Week 5 对比实验需要对两个项目都先跑 `codegraph index`，生成 `.codegraph/codegraph.db`

### CodeGraph 源码路径

- `E:\Python_Project\codegraph-main`（用于 Week 5 第二个验证项目）

---

## 5. 流程与代码规约（Week 5 必须遵守）

### 5.1 vibecoding 流程（沿用）

模板路径：`doc/vibecoding_rules/vibecoding_rules.md`

流程顺序：需求澄清 → `doc/Week5/requirement.md` → 概要设计 → 任务拆分 → prompts → 执行

### 5.2 代码规约

- `mypy --strict` 零错误（python_version=3.14）
- `ruff check` 零警告（line-length=100，select E/F/I/B/UP）
- `uv run pytest -q` 全量通过
- 新增 MCP Tool 步骤（Week 4 已验证）：`schemas.py` → `tools/<name>.py` → `tools/__init__.py`
- 类型注解：所有公开接口必须有完整类型注解

### 5.3 MCP SDK 已知陷阱（曾踩过的坑）

| 陷阱                                                                                      | 最小重现 / 定位                                        |
| --------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `@server.call_tool` 必须加 `validate_input=False`                                          | `server.py:27`。SDK 默认校验会拒绝自定义 schema，必须关闭        |
| `@server.list_resources` / `@server.read_resource` 回调返回类型是 `list[ReadResourceContents]` | `server.py:43-45`。不是 `ReadResourceResult`，否则类型错误 |
| pytest 测试中 `stdio_client` / `ClientSession` 不能共享 async fixture                          | `tests/conftest.py`。每个测试需独立创建 session            |
| `mcp` 版本锁定在 `1.27.2`                                                                    | 升级版本可能破坏 SDK API，`uv.lock` 已锁定                   |
| `@server.list_tools()` 装饰器无类型注解需 `# type: ignore`                                       | `server.py:23`。SDK 未导出 decorator 类型              |

### 5.4 错误处理规范

- **业务错误**：抛 `ToolError` 子类（`ValidationError` / `InvalidArgumentError` / `LLMError`）→ registry 转 `isError=true` 的 `CallToolResult`
- **Resource 错误**：返回包含错误描述的 Markdown 字符串，不抛异常（`resources/project_map.py` 模式）
- **缓存错误**：`read_*` 返回 `None`（视为 miss）；`write_*` 传播 `OSError`；`invalidate` 静默忽略

### 5.5 命名规约

- 工具函数名 = MCP tool name（全小写加下划线）
- 模块 key（新）：`safe_key(module_name)` → `sha1[:12]`；旧 `module_key(path)` 仍保留但不再用于新缓存
- 测试文件：`tests/test_<module_name>.py`

---

## 6. 工具/产品集成现状

### MCP 配置文件

路径：`c:\Users\leikaixin\AppData\Roaming\Code\User\globalStorage\techcenter.codemaker\settings\codemaker_mcp_settings.json`

当前配置（Week 4 末状态）：

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph",
      "args": ["serve", "--mcp"],
      "timeout": 60,
      "type": "stdio",
      "disabled": false,
      "autoApprove": true
    },
    "codesense_v1": {
      "command": "codesense_v1",
      "env": {
        "CODESENSE_PROJECT_ROOT": "E:/Python_Project/CodeSense_V1",
        "CODESENSE_LLM_API_KEY": "SK-xxxx",
        "CODESENSE_LLM_BASE_URL": "https://api.gemai.cc/v1",
        "CODESENSE_LLM_MODEL": "deepseek-v4-flash"
      },
      "args": [],
      "timeout": 60,
      "type": "stdio",
      "disabled": false,
      "autoApprove": true
    }
  }
}
```

Week 5 对比实验需要手动切换三种配置（改 `disabled` 字段 + 重启 VSCode）。

### Skill 安装状态

- 路径：`.codemaker/skills/codesense-workflow/SKILL.md`
- 状态：已安装，Week 4 实测可自动激活
- 格式：YAML Frontmatter（`name` + `description`）+ `## Instructions/Examples/Notes`

### 源码改动后重新安装

```bat
uv tool install --editable . --reinstall
```

然后重启 VSCode，新工具/Instructions 生效。

### CI 配置

无（本项目无 CI pipeline）。

---

## 7. 仍未做的工作（Week 5 之外，仅供参考）

- **Week 6**：整理项目文档（README、安装指南）、制作汇报 Slides（HTML）、内部 Demo 演示
- **Stretch Goal - 单文件独立模块检测**：对目录下 `.py` 文件判断"被目录外 import 且不依赖同目录兄弟"→ 视为隐藏独立模块（`doc/Week3/module_boundary_redesign.md` 有背景）
- **Stretch Goal - CodeGraph MCP 代理**：合并为一个 Server，用户只需配置一个 MCP
- **Stretch Goal - Watch 机制**：监听文件变化实时更新 `.codesense` 缓存
- **Stretch Goal - 多粒度 explore**：`explore_module` 支持递归展开子模块（`max_depth` 参数）
- **计划外工具清理**：`list_cached.py`、`list_cached_modules.py` 是实验产物，可选清理或补测试

---

## 8. 下一阶段验证对象

| 项目                | 路径                                 | 语言         | 规模      | 备注                                              |
| ----------------- | ---------------------------------- | ---------- | ------- | ----------------------------------------------- |
| CodeSense_V1（本项目） | `e:\Python_Project\CodeSense_V1`   | Python     | ~15 个模块 | 有 CodeGraph DB（`.codegraph/codegraph.db`），需提前确认 |
| CodeGraph 源码      | `E:\Python_Project\codegraph-main` | TypeScript | ~15k 行  | 已下载，需先跑 `codegraph index` 生成 DB                 |

**准备步骤**：

1. 确认两个项目的 `.codegraph/codegraph.db` 是否存在
2. 若不存在，先在项目根目录执行 `codegraph index`
3. 将 `CODESENSE_PROJECT_ROOT` 对应切换到目标项目根目录（改 `codemaker_mcp_settings.json`）

---

## 9. 给 Week 5 对话的开场建议

以下步骤按顺序执行，每一步是一条命令或一个文件路径：

1. **读本文件**（已读到这里，继续）

2. **读 Week 5 任务原文**：
   
   ```
   doc/vibecoding_rules/codesense-intern-project-plan.md
   ```
   
   定位 "Week 5：效果评估 + 对比实验" 章节

3. **读 Week 4 集成测试结论**（理解已有数据，避免重复）：
   
   ```
   doc/Week4/CodeSense_Agent行为观察总结.md
   ```

4. **确认测试环境**：
   
   ```bat
   cd /d e:\Python_Project\CodeSense_V1
   uv run pytest -q
   ```
   
   应输出 `142 passed`

5. **确认静态检查干净**：
   
   ```bat
   uv run mypy --strict src/codesense_v1/server/server.py
   uv run ruff check src/codesense_v1/server/server.py
   ```
   
   均应零错误

6. **确认 CodeGraph DB 存在**（两个项目都要）：
   
   ```bat
   dir e:\Python_Project\CodeSense_V1\.codegraph\codegraph.db
   dir E:\Python_Project\codegraph-main\.codegraph\codegraph.db
   ```
   
   若不存在，在对应目录执行 `codegraph index`

7. **按 vibecoding 流程澄清需求**（`doc/vibecoding_rules/vibecoding_rules.md` 步骤 1）：
   
   - 与用户澄清：实验任务具体选哪 2-3 个、指标如何量化、三组配置切换方式
   - 写 `doc/Week5/requirement.md`

8. **设计 → 任务拆分 → prompts → 执行**（严格按 vibecoding 流程，不确定必须问用户）
