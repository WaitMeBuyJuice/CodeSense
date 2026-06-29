## 仓库定位

CodeSense V1 是一个 MCP（Model Context Protocol）服务器，为 AI 编码助手（CodeMaker Agent）提供代码仓库的架构理解能力。

项目解决的核心问题是：当 AI Agent 面对一个不熟悉的代码仓库时，缺乏高层级的架构认知。CodeSense 通过对仓库进行静态分析（文件结构、符号提取、目录依赖），自动划分模块并生成 Markdown 格式的架构摘要，使 Agent 能够快速理解模块职责、接口契约和依赖关系。

目标用户是通过 MCP 协议接入的 AI 编码助手，特别是 CodeMaker VSCode 插件。核心价值是将代码仓库的结构化知识按需注入 Agent 上下文，大幅提升 Agent 在大型代码库中的导航和修改准确率。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python 3.14 |
| 核心框架 | MCP Python SDK（官方 mcp 包） |
| 传输协议 | MCP stdio |
| 关键依赖 | openai（LLM 调用）、jsonschema（参数校验）、json-repair（JSON 修复）、pathspec（gitignore 解析） |
| 构建工具 | Hatchling（wheel 构建） |
| 类型检查 | mypy（strict 模式） |
| 代码检查 | ruff |
| 测试框架 | pytest + pytest-asyncio |
| 目标平台 | Windows |

---

## 顶层目录结构

```
CodeSense_V1/
├── scripts/  [辅助脚本]
├── src/
│   └── codesense_v1/
│       ├── cache/
│       ├── data/
│       ├── registry/
│       ├── server/
│       ├── summarizer/
│       ├── tools/
│       └── errors.py
└── tests/  [测试代码]
```

---

## 系统分层与模块列表

### 架构分层

```
第2层（入口层）: server, tools
第1层（中间层）: summarizer, registry
第0层（基础层）: data, cache, errors
```

### 模块详情

| 模块名 | 职责 | 路径 |
|--------|------|------|
| errors | 工具领域异常基类，定义统一错误层级 | src/codesense_v1/errors.py |
| cache | 管理 .codesense 缓存文件的读写、校验与失效 | src/codesense_v1/cache |
| data | CodeGraph 数据库查询、目录级依赖聚合与文件分析 | src/codesense_v1/data |
| registry | MCP 工具注册中心，管理工具元数据与参数校验 | src/codesense_v1/registry |
| server | MCP stdio 服务器入口，构建并启动服务 | src/codesense_v1/server |
| summarizer | 协调 Data Layer 与 Cache，生成架构摘要 Markdown | src/codesense_v1/summarizer |
| tools | MCP 工具实现层（project_map、explore_module 等） | src/codesense_v1/tools |

---

## 模块边界规则

### 层次约束

- **依赖方向严格自上而下**：第2层（server/tools/tests）→ 第1层（registry/summarizer）→ 第0层（cache/data/errors）。反向依赖禁止。
- **第0层模块不可依赖上层**：`cache`、`data`、`errors` 不得 import registry、summarizer、server、tools 中的任何符号。
- **第1层模块不可依赖第2层**：`registry`、`summarizer` 不得 import server、tools 中的任何符号。
- **同层模块隔离**：同一层次内的模块应保持松耦合，禁止循环引用。`summarizer` ↔ `registry` 之间当前无直接静态依赖，若未来需要通信应通过上层编排（由 tools 桥接），不可直接互相 import。
- **server 仅为薄入口**：`server` 模块职责限定为：拼接 registry + 导入 tools 触发注册 + 构造 `mcp.Server` 实例并启动 stdio 传输。不得在 server 内实现业务逻辑、直接操作数据库或缓存。

### 访问禁忌

- **tools 不可直接访问 CodeGraphDB**：工具实现（`tools/` 下各模块）不得直接 `from codesense_v1.data.db import CodeGraphDB`。数据库访问应由 `summarizer` 或 `data` 层提供的封装函数完成；若 `project_map.py` 中已有 `CodeGraphDB` 引用则视为遗留技术债务，待重构。
- **tools 不可直接操作文件系统缓存**：工具不得直接调用 `cache.write_*` / `cache.read_*`。缓存读写由 `summarizer` 层编排。当前 `tools/project_map.py` 中存在与 cache 的直接耦合，后续应收敛到 summarizer。
- **交叉依赖的 data 子模块必须通过 data/__init__.py**：其他模块引用 data 层符号时，必须通过 `from codesense_v1.data import X`，禁止直接 `from codesense_v1.data.db import CodeGraphDB`（data 内部子模块间的交叉引用除外）。
- **禁止在非 server 模块中引用 mcp SDK**：只有 `server` 和 `registry` 模块允许 `import mcp`。tools、summarizer、data、cache 均不得直接依赖 `mcp` 包。
- **errors 为唯一异常层级**：所有业务/校验错误必须继承 `ToolError`（定义于 `codesense_v1.errors`）。禁止在 tools/summarizer 中抛出裸 `Exception` 或内置异常（`ValueError`、`RuntimeError` 等）直接暴露给上层。

### 职责边界

- **data 层**：纯数据访问。提供 CodeGraph SQLite 查询、目录树分析、拓扑排序、哈希计算、模块发现。不包含缓存逻辑、不生成 Markdown、不感知 MCP 协议。
- **cache 层**：纯缓存 I/O。提供 `.codesense/` 目录下 JSON/Markdown 文件的读写、校验（基于数据库哈希）、失效。不包含业务判断、不调用 data 层、不进行格式渲染。
- **summarizer 层**：协调 data + cache，生成面向 LLM 的 Markdown 提示词/摘要。所有 segment prompt 生成、模块摘要模板渲染、项目地图拼装逻辑集中于此。不可直接写入缓存（应通过 cache 层 write 函数）。
- **registry 层**：工具元数据中心。管理 `ToolSpec` 注册表、JSON Schema 校验、`tool` 装饰器、`dispatch` 分发。不包含任何业务逻辑或数据查询。
- **tools 层**：MCP 工具实现。每个模块对应一个 MCP tool，负责解析参数 → 调用 summarizer/data 获取数据 → 组装结果。不自行生成 Markdown、不做缓存有效性判断（应由 summarizer 提供的 is_auto_expire_enabled 等函数处理）。
- **server 层**：仅启动入口。`build_server()` 构造 Server 对象、注册 `list_tools`/`call_tool` handler，`main()`/`run_stdio()` 启动 asyncio 事件循环。不得包含工具实现或数据处理逻辑。
- **scripts 层**：开发者辅助脚本。依赖 data 层完成批量任务（如数据库导出）。不得被任何生产代码路径依赖。
- **tests 层**：测试代码。依赖 src/codesense_v1、data、registry。不得被任何生产代码 import。

### 新增代码约束

- **新增 MCP 工具**：在 `src/codesense_v1/tools/` 下新建模块，使用 `@tool` 装饰器注册；在 `tools/__init__.py` 中添加 `from . import new_tool  # noqa: F401` 以触发注册。
- **新增数据查询**：在 `src/codesense_v1/data/` 下新增函数/类，并在 `data/__init__.py` 中导出。如需跨 data 子模块调用，优先在 data 层内完成聚合。
- **新增缓存操作**：在 `src/codesense_v1/cache/cache.py` 中新增 `read_*`/`write_*` 函数，保持「读失败返回 None、写失败传播 OSError」的约定。
- **新增异常类型**：在 `src/codesense_v1/errors.py` 中新增 `ToolError` 子类，明确其抛出场景（校验层/业务层/LLM层）。
- **依赖限制**：新增代码必须遵循层次约束。如需跨层引入新依赖，必须先更新本文档的拓扑层次声明，并经架构评审确认不会引入循环依赖。
- **Python 版本**：目标 Python 3.14，允许使用 `from __future__ import annotations`、`Final` 等新特性。
- **包管理**：使用 uv + `pyproject.toml`，第三方依赖仅限 `mcp`、`jsonschema`、`pytest`（及其异步插件）。新增依赖需在 `pyproject.toml` 中声明。
- **暂不开放插件/扩展点**：当前 registry 的 `@tool` 装饰器和 ToolSpec 机制仅供内部使用，不对外暴露为稳定 API。新增模块如需注册自定义处理器应通过现有 tools 层模式实现。（待人工补充：未来若需支持第三方工具注册，需定义正式的插件接口协议）

---

## 关键流程描述

### 流程1：MCP 服务器启动与工具注册
**场景**：客户端启动 CodeSense MCP 服务，完成 stdio 握手后，`tools/list` 请求获取所有可用工具元数据。
**调用链**：server → registry → tools
**关键步骤**：
1. `main()` 初始化 `.codesenseignore` 模板后调用 `asyncio.run(run_stdio())` 进入异步主循环。
2. `build_server()` 构造 `mcp.server.Server` 实例，通过装饰器将 `@server.list_tools()` 绑定到 `registry.list_tools()`。
3. `import tools` 触发 `tools/__init__.py` 中所有子模块导入（`project_map`、`explore_module` 等），每个子模块顶部的 `@tool(...)` 装饰器将 `ToolSpec`（名称、描述、输入模式、处理函数）注册到 `_REGISTRY` 字典。
4. 客户端发送 `tools/list` → server 回调 `registry.list_tools()` → 遍历 `_REGISTRY` 返回 `Tool` 对象列表。
5. 后续 `tools/call` → server 解析参数后调用 `registry.dispatch(name, arguments)` → `jsonschema` 校验参数 → 执行对应的 async handler → 返回 `CallToolResult`。

### 流程2：project_map 懒初始化与分段生成
**场景**：用户首次查询项目架构，缓存未就绪，触发 LLM Agent 协作式的分段生成流程。
**调用链**：tools/project_map → data → summarizer → cache
**关键步骤**：
1. `project_map()` 通过 `resolve_project_root()` 定位项目根目录，验证 `.codegraph/codegraph.db` 存在。
2. 打开 `CodeGraphDB`，调用 `list_modules(db)`、`module_dependencies(db)`、`directory_tree(db)`、`collect_identity_sources()` 等 data 层函数，收集模块列表、依赖边、目录树、项目身份数据。
3. 计算 7 个段落的哈希值（`compute_identity_hash`、`compute_structure_hash`、`compute_architecture_hash`、`compute_dependencies_hash` 等），与 `cache.is_segment_valid()` 逐一比对。
4. 程序可自动生成的段落（`02_structure`、`07_dependencies`）直接由 `render_structure_segment()` / `render_dependencies_segment()` 生成并 `cache.write_segment()` 写入。
5. 需要 LLM 判断的段落（`01_identity`、`03_modules`、`04_constraints`、`05_flows`、`06_concepts`）通过 `summarizer.get_*_prompt()` 获取分析提示词，组合成生成步骤返回给 Agent。
6. Agent 逐段生成内容后调用 `save_project_map_segment()` 或 `submit_project_map()` 写回缓存。全部就绪后 `project_map()` 调用 `cache.render_project_map()` 拼接所有 segment 为最终 `project_map.md`。

### 流程3：探索模块架构（explore_module + save_module_summary）
**场景**：用户查询某模块的内部结构，缓存未命中时触发 LLM Agent 生成模块摘要并保存。
**调用链**：tools/explore_module → cache → data/db → summarizer → cache
**关键步骤**：
1. `explore_module(module_name)` 先从 `cache.read_modules_index()` 获取模块索引，验证模块名存在（区分 L1 模块和 L2 辅助目录）。
2. 若为 L2 辅助目录，直接返回类别和文件数等简要信息。
3. 若为 L1 模块：打开 `CodeGraphDB`，调用 `summarizer._compute_module_hash(entry, db)` 计算当前模块哈希，与 `cache.read_module()` + `cache.read_module_hashes()` 比对。缓存有效则直接返回 Markdown。
4. 缓存未命中 → 调用 `summarizer.get_module_prompt()` 生成分析提示词（含目录结构、依赖关系、公共 API 等数据），嵌入生成步骤返回给 Agent。
5. Agent 阅读源码生成模块摘要后，调用 `save_module_summary(module_name, summary)` → `summarizer.save_module_summary()` 重新计算模块哈希并 `cache.write_module()` 写入 `.codesense/modules/{key}/`。
6. Agent 重新调用 `explore_module`，此时缓存命中，返回完整模块文档。

### 流程4：模块划分提交与项目地图渲染（submit_project_map）
**场景**：Agent 完成 `03_modules` 的模块划分后，提交管道分隔格式的模块列表，系统自动推导文件归属、计算分层并渲染完整 `project_map.md`。
**调用链**：tools/submit_project_map → summarizer → data → cache
**关键步骤**：
1. Agent 调用 `submit_project_map(response=<模块名|职责|目录1,目录2>)`，进入 `summarizer.submit_project_map()`。
2. 打开 `CodeGraphDB`，获取 `list_modules`、`module_dependencies`、`directory_dependencies`、`directory_symbols` 等数据。
3. `_parse_modules_text()` 解析管道分隔文本，校验目录有效性（精确匹配或模糊匹配），去重、归属冲突处理。
4. `_expand_module_files()` 将模块目录映射展开为完整的文件列表。如有模块重命名，`_migrate_renamed_module_caches()` 迁移旧缓存。
5. `cache.write_modules_index()` 将模块索引（名称、描述、目录、文件）持久化到 `modules_index.json`。
6. 自动生成 `03_modules` 段落（`_render_basic_architecture_segment()` + 拓扑分层）和 `07_dependencies` 段落（`render_dependencies_segment()` + 循环检测），写入 segment 缓存。
7. `cache.render_project_map()` 按 `01→02→03→04→05→06→07` 顺序拼接所有 segment，写入 `project_map.md` 并返回。

### 流程5：子模块文档生成（explore_submodule + save_submodule_summary）
**场景**：用户深入了解模块内某个文件的职责和接口，缓存未命中时触发子模块级文档生成。
**调用链**：tools/explore_submodule → cache → data/db → summarizer → cache
**关键步骤**：
1. `explore_submodule(module_name, file_path)` 验证模块名和文件路径，读取 `modules_index` 和模块哈希判断缓存有效性。
2. 缓存有效 → 直接返回 `cache.read_submodule()` 内容。
3. 缓存未命中 → 打开 `CodeGraphDB`，调用 `summarizer.get_submodule_prompt()` 生成分析提示词（含文件符号列表、docstring、依赖关系等），返回给 Agent。
4. Agent 分析源码后调用 `save_submodule_summary(module_name, file_path, summary)` → `summarizer.save_submodule_summary()` 计算子模块哈希并通过 `cache.write_submodule()` + `cache.write_submodule_hash()` 写入 `.codesense/modules/{module_key}/{file_key}.md`。
5. Agent 重新调用 `explore_submodule`，缓存命中返回子模块文档。

---

## 概念索引

| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |
|-----------------|---------|---------|------|
| 项目架构概览 | tools | `project_map` | 返回缓存的项目级架构 Markdown，包含模块列表、依赖关系、概念索引 |
| 模块详情查询 | tools | `explore_module` | 返回单个模块的接口、文件职责、上下游依赖；与 project_map 不同——前者看全局，后者看模块内部 |
| 子模块/文件详情 | tools | `explore_submodule` | 返回单个文件级子模块文档；与 explore_module 不同——粒度更细，面向文件而非目录 |
| 架构段落保存 | tools | `save_project_map_segment` | Agent 生成 project_map 缺失段落后调用此工具写入缓存；与 summarizer 中同名函数不同——此为 MCP 工具入口 |
| 模块划分提交 | tools | `submit_project_map` | Agent 生成的模块列表通过此工具解析并持久化到 modules_index.json |
| 缓存校验 | cache | `is_cache_valid`, `is_segment_valid` | 对比当前 DB hash 与缓存中的 hash，判断缓存是否过期；is_segment_valid 针对单段落，is_cache_valid 针对整体 |
| 缓存失效 | cache | `invalidate`, `invalidate_segments` | 清除整个 .codesense 缓存目录或指定段落；invalidate 全量删除，invalidate_segments 删除 project_map_segments 子目录 |
| DB 哈希指纹 | cache | `db_hash` | 对 codegraph.db 文件计算 SHA-256 摘要，作为缓存有效性的基准 |
| 缓存渲染 | cache | `render_project_map` | 将 01~07 各段落按固定顺序拼接为完整 project_map.md |
| 依赖关系分析 | data | `module_dependencies`, `directory_dependencies` | 从 CodeGraph 提取模块/目录间 import 边；module_dependencies 按模块聚合，directory_dependencies 按目录聚合 |
| 架构特征计算 | data | `ArchitectureFeatures`, `compute_centrality`, `topological_layers`, `find_cycles` | 图分析套件：中心度（扇入/扇出）、拓扑分层（0 层=基础设施）、循环依赖检测 |
| 目录分类 | data | `TopLevelDir`, `classify_top_dirs`, `auxiliary_category` | 将顶层目录分为代码目录与辅助目录（如 docs、test、script）；辅助目录不参与模块划分 |
| 项目身份识别 | data | `IdentitySource`, `collect_identity_sources` | 从 README、pyproject.toml 等文件提取项目名、描述、技术栈线索 |
| 工具注册 | registry | `tool`, `ToolSpec`, `list_tools`, `dispatch` | @tool 装饰器注册 MCP 工具；ToolSpec 封装名称/描述/参数 schema/handler；dispatch 根据工具名路由调用 |
| 参数校验 | registry, errors | `ValidationError`, `dispatch` | registry.dispatch 用 jsonschema 校验参数，失败抛 ValidationError；与 InvalidArgumentError 不同——前者是 schema 级，后者是语义级 |
| 业务错误处理 | errors | `ToolError`, `InvalidArgumentError`, `LLMError` | 异常层级：ToolError 基类 → ValidationError/InvalidArgumentError/LLMError；LLMError 是 LLM 调用失败，InvalidArgumentError 是语义非法参数 |
| 服务器启动 | server | `build_server`, `main`, `run_stdio` | build_server 构建 MCP Server 实例；main/run_stdio 启动 stdio 传输层 |
| 架构摘要生成 | summarizer | `get_project_map_prompt`, `get_module_prompt`, `get_submodule_prompt` | 协调 Data Layer 与 Cache，为 LLM 生成分析提示词；get_project_map_prompt 用于模块划分，get_module_prompt 用于单模块摘要 |
| 段落渲染 | summarizer | `render_structure_segment`, `render_dependencies_segment` | 纯程序化生成 Markdown 段落（目录树、依赖关系），无需 LLM 参与 |
| 文档字符串提取 | data | `extract_file_docstring`, `extract_symbol_docstrings` | 从源码文件提取模块/类/函数的文档字符串，用于增强 LLM 提示词 |

---

## 上下游详表

| 模块 | 上游（依赖于我） | 下游（我依赖） |
|------|----------------|--------------|
| cache | summarizer、tools | 无 |
| data | summarizer、tools | 无 |
| errors | registry、summarizer、tools | 无 |
| registry | server、tools | errors |
| server | 无 | registry |
| summarizer | tools | cache、data、errors |
| tools | 无 | cache、data、errors、registry、summarizer |

> 无循环依赖。