# Week 3 需求文档

> 基于 `doc/stack.md`、`doc/Week3/week3_handoff.md`，以及 Week 3 启动前的需求澄清对话。
> Week 2 技术选型与规约保持不变，本文件仅覆盖 Week 3 新增内容。

---

## 1. 项目背景与目标

Week 2 完成了 MCP Server 骨架和 Data Layer，能从 CodeGraph DB 提取结构数据。
Week 3 在此基础上实现两个核心功能：

1. **`project_map`（MCP Resource）**：项目整体架构概览，AI 打开项目时被动注入，无需主动调用。
2. **`explore_module`（MCP Tool）**：按目录路径查询某模块的完整理解（接口、内部结构、边界），AI 主动调用。

两个功能均通过 LLM（OpenAI 兼容 API）将结构数据转化为架构语义描述，结果持久化在 `.codesense/` 目录，使用 Lazy 缓存策略（DB hash 驱动）。

---

## 2. 用户角色与使用场景

| 角色                  | 场景                                            |
| ------------------- | --------------------------------------------- |
| AI Agent（CodeMaker） | 连接 MCP Server 后自动获取 `project_map` 作为背景知识      |
| AI Agent（CodeMaker） | 修改某模块前主动调用 `explore_module("src/auth")` 了解该模块 |
| 开发者                 | 首次运行工具时 `.codesense/` 被自动创建并填充                |
| 开发者                 | CodeGraph DB 更新后，再次调用工具时缓存自动失效重建              |

---

## 3. 功能需求列表

### FR-1  `project_map` MCP Resource

- **FR-1.1** 作为 MCP Resource 暴露，URI 为 `codesense://project_map`，在 AI 连接 Server 时自动可用。
- **FR-1.2** 内容包含：
  - 模块列表（每个模块即一个顶层目录/包）
  - 每模块一句话描述（LLM 生成）
  - 跨模块依赖关系（哪个模块依赖哪些模块，精简文字或表格形式）
- **FR-1.3** 内容为 Markdown 格式。
- **FR-1.4** 读取时触发 Lazy 缓存检查（见 FR-5），命中直接返回缓存，未命中调用 LLM 重新生成。

### FR-2  `explore_module` MCP Tool

- **FR-2.1** 工具名 `explore_module`，接受参数 `module_path: str`（相对目录路径，如 `src/auth`）。
- **FR-2.2** 模块边界由 Python 包的 `__init__.py` 层级界定：
  - 传入路径对应一个含 `__init__.py` 的目录 → 该目录即为模块范围。
  - 若路径不含 `__init__.py` 或不存在，返回 `isError=true` 的清晰错误信息。
- **FR-2.3** 返回内容包含（Markdown 格式）：
  - 一句话模块描述（LLM 生成）
  - 对外接口列表：仅包含公开函数和类（名称不以 `_` 开头），含函数/类签名
  - 内部子模块列表（模块内各文件/子包）
  - 依赖的其他模块（来自 Data Layer 的 `module_dependencies`）
- **FR-2.4** 结果按模块路径缓存到 `.codesense/modules/<module_key>.json`（见 FR-5）。
- **FR-2.5** 遵循现有工具注册流程（`schemas.py` + `@tool` 装饰器 + `tools/__init__.py`）。

### FR-3  LLM 调用层

- **FR-3.1** 使用 OpenAI 兼容 API，配置通过环境变量读取：
  - `CODESENSE_LLM_API_KEY`
  - `CODESENSE_LLM_BASE_URL`（默认 `https://api.gemai.cc/v1`）
  - `CODESENSE_LLM_MODEL`（默认 `deepseek-v4-flash`）
- **FR-3.2** Prompt 格式为 Markdown，LLM 输出为 Markdown。
- **FR-3.3** LLM 调用失败时（网络错误、超时、非 200 响应）抛出 `ToolError` 子类，由 registry 转为 `isError=true` 响应。
- **FR-3.4** 不做自动重试（保持简单，出错直接报错）。

### FR-4  `.codesense/` 持久化

- **FR-4.1** 结构：
  
  ```
  .codesense/
  ├── project_map.md          # project_map 的 LLM 生成内容
  ├── modules/
  │   └── <module_key>.json   # 每个模块：结构数据 + LLM 摘要
  └── meta.json               # DB hash + 生成时间
  ```

- **FR-4.2** `.codesense/` 目录不存在时自动创建。

- **FR-4.3** `meta.json` 结构：
  
  ```json
  {
    "db_hash": "<sha256 of codegraph.db file>",
    "generated_at": "<ISO 8601 timestamp>"
  }
  ```

- **FR-4.4** `<module_key>` 为模块路径以 `_` 替换路径分隔符，如 `src/auth` → `src_auth`。

- **FR-4.5** `modules/<module_key>.json` 结构：
  
  ```json
  {
    "module_path": "src/auth",
    "summary": "<LLM 生成的 Markdown 文本>",
    "generated_at": "<ISO 8601 timestamp>"
  }
  ```

### FR-5  Lazy 缓存策略

- **FR-5.1** 缓存粒度为项目级：`meta.json` 中记录一个整体 DB hash（`codegraph.db` 文件的 SHA-256）。
- **FR-5.2** 每次调用 `project_map` 或 `explore_module` 时：
  1. 计算当前 `codegraph.db` 的 SHA-256。
  2. 与 `meta.json` 中的 `db_hash` 对比。
  3. 一致 → 直接使用缓存内容返回。
  4. 不一致（或 `meta.json` 不存在）→ 删除 `.codesense/` 内所有缓存，重新生成并写入。
- **FR-5.3** 重新生成时，`project_map` 和对应 `modules/*.json` 均更新，同时更新 `meta.json`。

### FR-6  MCP Resource 注册

- **FR-6.1** `project_map` 通过 MCP SDK 的 `@server.list_resources` / `@server.read_resource` 回调暴露。
- **FR-6.2** Resource URI：`codesense://project_map`，MIME type：`text/markdown`。
- **FR-6.3** `server.py` 中新增 Resource 回调绑定，不破坏现有 `list_tools` / `call_tool` 逻辑。

---

## 4. 非功能需求

| 类别   | 要求                                   |
| ---- | ------------------------------------ |
| 代码质量 | `mypy --strict` 零错误；`ruff check` 零警告 |
| 测试覆盖 | 每个新模块均有 pytest 单元测试，覆盖正常路径和异常路径      |
| 安全   | LLM API Key 严禁硬编码，必须从环境变量读取          |
| 兼容性  | Windows Python 3.14；mcp SDK 1.27.2   |
| 性能   | 缓存命中时响应无需等待 LLM，毫秒级返回                |

---

## 5. 明确的输入/输出定义

### `project_map` Resource

- **输入**：无（MCP Resource 读取）
- **环境依赖**：`<project_root>/.codegraph/codegraph.db` 存在且可读；LLM 环境变量已设置
- **输出**：Markdown 字符串，包含模块列表 + 一句话描述 + 跨模块依赖关系

### `explore_module` Tool

- **输入**：`{"module_path": "src/auth"}`（相对于项目根目录的目录路径）
- **成功输出**：Markdown 字符串，包含一句话描述 + 对外接口 + 内部子模块 + 依赖模块
- **错误情况**：
  - `module_path` 对应目录不存在 → `isError=true`，`"参数错误：模块路径不存在: src/auth"`
  - `module_path` 目录下无 `__init__.py` → `isError=true`，`"参数错误：路径 src/auth 不是 Python 包（缺少 __init__.py）"`
  - LLM 调用失败 → `isError=true`，`"内部错误：LLMError"`
  - DB 不存在 → `isError=true`，`"内部错误：FileNotFoundError"`

---

## 6. 需求确认记录

| 条目                  | 决策                                 | 时间         |
| ------------------- | ---------------------------------- | ---------- |
| project_map 内容      | 精简版：模块列表 + 每模块一句话 + 跨模块依赖关系图       | 2026-06-15 |
| explore_module 返回字段 | 一句话描述 + 对外接口（签名）+ 内部子模块 + 依赖模块     | 2026-06-15 |
| 缓存失效粒度              | project 级，一个 meta.json 管整个 DB hash | 2026-06-15 |
| 模块标识参数              | 按目录路径传入（如 src/auth）                | 2026-06-15 |
| 对外接口定义              | 仅公开函数和类（名称不以 _ 开头）                 | 2026-06-15 |
| LLM 交互格式            | Markdown prompt + 返回 Markdown      | 2026-06-15 |
| 错误处理                | isError=true 返回清晰错误信息              | 2026-06-15 |
| 模块边界检测              | 包级：__init__.py 层界定义模块              | 2026-06-15 |
