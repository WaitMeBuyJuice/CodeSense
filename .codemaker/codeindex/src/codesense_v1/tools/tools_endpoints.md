## entity_names.constants

| 常量名 | 位置 | 说明 |
|--------|------|------|
| `_CODESENSE_DIR` | `explore_module.py:15`, `project_map.py:12` | `".codesense"` — 缓存目录名称（在两个文件中独立定义） |
| `CODESENSE_PROJECT_ROOT` | 环境变量，6 个 tool 文件均读取 | 项目根路径，MCP 配置的 `env` 字段注入 |

> 注：不存在其他模块级公开常量。`_EXPLORE_MODULE_INPUT_SCHEMA`、`_PROJECT_MAP_INPUT_SCHEMA`、`_SCHEMA` 等为 MCP tool 的 JSON Schema 定义，是 `@tool` 装饰器的参数，不对外暴露。

## 对外接口（6 个 MCP Tool Endpoints）

| Tool Name | 签名 | 输入字段 | 返回类型 | 职责 |
|-----------|------|---------|---------|------|
| `explore_module` | `async (module_name: str) -> str` | `module_name`（必填，非空） | `str`（Markdown 摘要 or 工作流指令） | 获取模块摘要；缓存命中直接返回，未命中返回生成指令 |
| `project_map` | `async () -> str` | 无 | `str`（project_map.md or 工作流指令） | 获取项目架构概览；缓存命中直接返回，未命中返回生成指令 |
| `get_project_map_prompt` | `async () -> str` | 无 | `str`（LLM prompt Markdown） | 返回项目模块划分的分析提示词 |
| `get_module_prompt` | `async (module_name: str) -> str` | `module_name`（必填，非空） | `str`（LLM prompt Markdown） | 返回指定模块的详细分析提示词 |
| `save_module_summary` | `async (module_name: str, summary: str) -> str` | `module_name`（必填，非空）、`summary`（必填，非空） | `str`（确认消息） | 保存 Agent 生成的模块摘要到缓存 |
| `submit_project_map` | `async (response: str) -> str` | `response`（必填，pipe-delimited 文本） | `str`（project_map.md Markdown） | 解析并提交 Agent 生成的模块划分结果 |

### 输入字段详细说明

**explore_module**
- `module_name`: 模块名称（project_map 返回的 L1 模块名之一，或辅助目录名）

**get_module_prompt**
- `module_name`: 模块名称（project_map 返回的 L1 模块名之一）

**save_module_summary**
- `module_name`: 模块名称（必须已存在于 modules_index）
- `summary`: Agent 生成的 Markdown 摘要全文

**submit_project_map**
- `response`: pipe-delimited 文本，每行格式 `模块名|一句话职责|目录1,目录2`

## retrieval_hints

1. **找 MCP Tool 注册逻辑**：每个 tool 文件顶部的 `@tool()` 装饰器定义了 tool 名称、描述和 input_schema；`registry.py` 负责扫描并注册所有 tool。
2. **找缓存命中/未命中分支**：`project_map()` 的 `cache.is_cache_valid` + `cache.read_project_map` 和 `explore_module()` 的 `cache.read_module` + hash 比较是关键路径。
3. **找环境变量使用**：所有 6 个 tool 函数均以 `os.environ.get("CODESENSE_PROJECT_ROOT", "")` 开头，**不可硬编码项目路径**。
4. **找 Agent 工作流指令**：`project_map()` 和 `explore_module()` 缓存未命中时返回的字符串包含完整的步骤指引（方式1：子 Agent / 方式2：主 Agent 直接执行）。
5. **反向排除**：如果你找的是 **LLM prompt 的具体内容**（目录符号列表、依赖拓扑、docstring 提取结果），不在这里——在 `summarizer._build_project_map_prompt` 和 `summarizer._build_module_prompt`。
6. **反向排除**：如果你找的是 **缓存文件 I/O 细节**（JSON 读写、hash 计算），不在这里——在 `cache.py` 的 `read_*` / `write_*` 函数。

## 跨模块依赖

### tools → summarizer（所有 6 个 tool 函数）

| Tool 函数 | 调用的 summarizer 函数 | 调用方式 |
|-----------|----------------------|---------|
| `get_project_map_prompt_tool` | `summarizer.get_project_map_prompt` | 直接委托 |
| `submit_project_map_tool` | `summarizer.submit_project_map` | 直接委托 |
| `get_module_prompt_tool` | `summarizer.get_module_prompt` | 直接委托 |
| `save_module_summary_tool` | `summarizer.save_module_summary` | 直接委托 |
| `project_map` | （间接）Agent → `get_project_map_prompt` → `submit_project_map` | 通过 Agent 工作流指令 |
| `explore_module` | `summarizer._compute_module_hash`（直接导入）；（间接）Agent → `get_module_prompt` → `save_module_summary` | 直接导入 + Agent 工作流指令 |

### tools → cache

| Tool 函数 | 调用的 cache 函数 |
|-----------|------------------|
| `project_map` | `db_hash`, `is_cache_valid`, `read_project_map` |
| `explore_module` | `safe_key`, `read_modules_index`, `read_module`, `read_module_hashes` |

## 典型调用链

### 1. project_map — 缓存命中

```
Agent 调用 project_map() →
  os.environ["CODESENSE_PROJECT_ROOT"] → Path
  db_path.exists() → True
  cache.db_hash(db_path) → current_hash
  cache.is_cache_valid(codesense_dir, current_hash) → True
  cache.read_project_map(codesense_dir) → project_map.md
  return project_map.md  ✅
```

### 2. project_map — 缓存未命中

```
Agent 调用 project_map() →
  CODESENSE_PROJECT_ROOT → Path
  db_path.exists() → True
  cache.db_hash → current_hash
  cache.is_cache_valid → False → 返回工作流指令
Agent 按指令:
  get_project_map_prompt() → summarizer.get_project_map_prompt() → prompt
  Agent 生成模块划分 → submit_project_map(response=...) →
    summarizer.submit_project_map() → cache.write_modules_index + write_project_map
Agent 重新 project_map() → 缓存命中 ✅
```

### 3. explore_module — 缓存命中

```
Agent 调用 explore_module("数据层") →
  module_name.strip() → 非空
  CODESENSE_PROJECT_ROOT → Path
  db_path.exists() → True
  cache.read_modules_index → index 存在
  L2 辅助目录检查 → 不是辅助目录
  L1 模块查找 → 找到 entry
  _compute_module_hash(entry, db) → current_module_hash
  cache.read_module → cached_md 存在
  cache.read_module_hashes[module_key] == current_module_hash → True
  return cached_md  ✅
```

### 4. explore_module — 缓存未命中

```
Agent 调用 explore_module("数据层") →
  ...（同上到 hash 比较）→ 缓存未命中或 hash 不匹配
  返回工作流指令（包含 get_module_prompt → 生成 → save_module_summary 步骤）
Agent 按指令:
  get_module_prompt("数据层") → summarizer.get_module_prompt() → prompt
  Agent 生成摘要 → save_module_summary("数据层", summary) →
    summarizer.save_module_summary() → cache.write_module
Agent 重新 explore_module("数据层") → 缓存命中 ✅
```

## 实现约束

### 必须遵守的规则

| 约束 | 原因 | 违反后果 |
|------|------|---------|
| **环境变量 `CODESENSE_PROJECT_ROOT` 必须读取，不可硬编码项目路径** | 支持多项目复用同一 MCP Server，路径由 MCP 配置注入 | 硬编码路径 → 其他项目无法使用 |
| **所有 tool 必须通过 `@tool()` 装饰器注册** | MCP registry 通过装饰器发现 tool，未注册的 tool 对 Agent 不可见 | 缺少 `@tool` → Agent 看不到该端点 |
| **`explore_module` 和 `project_map` 缓存未命中必须返回工作流指令，不能直接调用 LLM** | tools 层不持有 LLM 调用能力，必须引导 Agent 完成生成闭环 | 直接调 LLM → 阻塞或无响应 |
| **参数校验必须在委托 summarizer 之前完成** | summarizer 假设参数有效；空 module_name/response 会导致下游错误 | 跳过校验 → summarizer 抛异常信息不友好 |
| **DB 不存在时返回友好错误消息，不抛异常** | Agent 看到友好指引后可以执行修复步骤（`codegraph init -i`） | 抛异常 → Agent 收到原始 traceback |

### 每个 tool 函数的实现清单

| Tool | 必须做的事 |
|------|----------|
| `project_map` | 读 `CODESENSE_PROJECT_ROOT` → 检查 DB 存在性 → 检查 `cache.is_cache_valid` → 命中返回/未命中返回指令 |
| `explore_module` | 读 `CODESENSE_PROJECT_ROOT` → 参数非空校验 → DB 存在性 → `read_modules_index` → L2 辅助目录检查 → L1 模块查找 → per-module hash 比较 → 命中返回/未命中返回指令 |
| `get_project_map_prompt_tool` | 读 `CODESENSE_PROJECT_ROOT` → 委托 `summarizer.get_project_map_prompt` → 捕获 `FileNotFoundError` |
| `get_module_prompt_tool` | 读 `CODESENSE_PROJECT_ROOT` → 参数非空校验 → 委托 `summarizer.get_module_prompt` → 捕获 `FileNotFoundError` |
| `save_module_summary_tool` | 读 `CODESENSE_PROJECT_ROOT` → 参数非空校验 → 委托 `summarizer.save_module_summary` → 返回字符数确认 |
| `submit_project_map_tool` | 读 `CODESENSE_PROJECT_ROOT` → 委托 `summarizer.submit_project_map` → 捕获 `FileNotFoundError` |
