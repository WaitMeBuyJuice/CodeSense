## 仓库定位

CodeSense V1 是一款基于 MCP（Model Context Protocol）的代码智能分析服务，为 AI 编程助手提供代码库的结构化理解能力。

项目解决的核心问题：大型代码库中，AI 助手缺乏对项目架构、模块职责、符号关系的全局认知。CodeSense V1 通过代码索引、缓存管理和结构化摘要，将代码库的架构信息以 MCP 工具形式暴露给 LLM Agent。

目标用户为集成 MCP 客户端的 AI 编程工具（如 Cursor、VS Code Cline 等），核心价值在于让 AI 助手在回答代码问题时能快速定位模块边界、理解调用链和评估变更影响范围，无需每次都从零扫描整个代码库。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python 3.14+ |
| 核心框架 | MCP (mcp.server.stdio) |
| 关键依赖 | openai (LLM 调用), json-repair (JSON 修复), pathspec (文件忽略规则), jsonschema (工具参数校验) |
| 构建工具 | hatchling |
| 类型检查 | mypy (strict mode) |
| 代码检查 | ruff |
| 测试框架 | pytest + pytest-asyncio |

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

## 模块列表

| 模块名 | 职责 | 路径 | 架构层 |
|--------|------|------|--------|
| 错误定义 | 工具领域异常基类，所有业务/校验错误都继承 ToolError | `src/codesense_v1` | 第0层 |
| 缓存管理 | .codesense/ 目录缓存读写与失效管理，提供 segment 级和模块级缓存 | `src/codesense_v1/cache` | 第0层 |
| 数据层 | CodeGraph DB 封装：文件/符号/边的结构化存储，目录级依赖聚合与架构特征计算 | `src/codesense_v1/data` | 第0层 |
| 工具注册 | MCP 工具声明式注册与 JSON Schema 参数校验，工具路由分发 | `src/codesense_v1/registry` | 第1层 |
| 摘要协调 | 协调数据层与缓存层，生成项目映射/模块摘要的 Markdown 内容，纯函数式协调 | `src/codesense_v1/summarizer` | 第1层 |
| 服务入口 | MCP stdio 服务器启动与生命周期管理，工具列表/调用的 MCP 协议处理 | `src/codesense_v1/server` | 第2层（入口）|
| 工具实现 | MCP 工具具体实现，解析项目根路径，编排调用摘要协调/缓存管理/数据层 | `src/codesense_v1/tools` | 第2层（入口）|

### 架构层级
- **第0层（基础层）**：错误定义、缓存管理、数据层 — 被上层依赖，无内部出边，互不依赖
- **第1层（协调层）**：工具注册、摘要协调 — 依赖第0层，被第2层依赖
- **第2层（入口层）**：服务入口、工具实现 — 依赖第1层和第0层，不被其他模块依赖

---

## 模块边界规则

### 层次约束

项目遵循严格的单向依赖分层架构，共 3 层：

| 层次 | 模块 | 依赖方向 |
|------|------|----------|
| 第 0 层（基础层） | 错误定义、缓存管理、数据层 | 不依赖任何项目内模块（仅依赖标准库与第三方库） |
| 第 1 层（中间层） | 工具注册、摘要协调 | 仅依赖第 0 层 |
| 第 2 层（入口/编排层） | 服务入口、工具实现 | 依赖第 0 层和第 1 层；允许跨层组合调用 |

- **单向依赖**：上层可以依赖下层，下层绝不能反向依赖上层。
- **同层隔离**：同一层内的模块之间不应产生直接 import 依赖（当前已满足：工具注册与摘要协调互不依赖；服务入口与工具实现互不依赖）。
- **禁止倒挂**：缓存管理、数据层、错误定义不得引用工具注册、摘要协调、服务入口、工具实现中的任何符号。
- **无循环依赖**：当前依赖图中不存在循环依赖。

### 访问禁忌

| 禁止行为 | 原因 |
|----------|------|
| **工具实现层直接操作 `.codesense/` 目录** | `.codesense/` 目录的读写必须通过缓存管理模块；直接文件 I/O 会绕过缓存有效性校验（db_hash 比对），导致缓存污染 |
| **工具实现层直接实例化 `CodeGraphDB`** | 数据库访问必须通过数据层提供的函数（如 `list_modules`、`module_dependencies`）；直接操作 DB 会绕过数据层的只读保证和聚合逻辑 |
| **数据层写入文件或修改数据库** | 数据层是「纯读层」，`CodeGraphDB` 以只读模式打开 SQLite 连接（`mode=ro` URI）；任何写操作应属于缓存管理层 |
| **摘要协调层绕过缓存管理层直接写文件** | 摘要协调层的所有持久化操作必须通过缓存管理的 `write_*` 系列函数；当前已通过 `cache.write_modules_index`、`cache.write_module`、`cache.write_segment` 等接口贯彻 |
| **外部模块直接调用 `registry._REGISTRY` 或 `registry.dispatch`** | 工具注册表是内部实现细节；服务入口通过 `registry.list_tools()` 和 `registry.dispatch()` 访问，工具实现通过 `@tool` 装饰器注册，不应绕过这些公开接口 |
| **测试代码直接 import 服务入口或工具实现模块的内部符号** | 测试应通过 registry 的 `@tool` 装饰器注册的函数直接测试（装饰器原样返回被装饰函数），或通过 `build_server()` 注入 mock transport；不应耦合到 stdio 传输细节 |

### 职责边界

| 模块 | 唯一职责 | 不可越界行为 |
|------|----------|-------------|
| **错误定义** | 定义工具领域的异常层次（`ToolError` 及其子类） | 不处理任何业务逻辑、不导入项目内其他模块 |
| **缓存管理** | `.codesense/` 目录下所有缓存文件的读、写、失效判断与裁剪 | 不读取 CodeGraph 数据库、不执行任何图计算或 LLM 调用 |
| **数据层** | 对 CodeGraph SQLite 数据库的只读查询 + 目录级聚合 + 图结构计算（中心性、拓扑分层、循环检测、公共 API 推断） | 不写入任何文件、不修改数据库、不处理 LLM 交互、不感知 MCP 协议 |
| **工具注册** | MCP 工具装饰器注册 + JSON Schema 校验 + 调用分发（含异常转译） | 不包含任何工具的业务逻辑实现、不访问数据库或文件系统 |
| **服务入口** | 创建 MCP Server 实例、绑定 stdio 传输、启动事件循环 | 不包含任何工具业务逻辑、Schema 或缓存操作 |
| **摘要协调** | 协调数据层查询结果与缓存管理层，构建发送给 LLM 的分析提示词，并解析 LLM 返回结果存入缓存；负责项目映射 segment 的纯程序化渲染 | 不直接操作 `.codesense/` 文件（全部委托给缓存管理）；不处理 MCP 协议细节（由工具实现层和注册层处理） |
| **工具实现** | 每个模块文件封装单个 MCP 工具的完整调用流程：解析参数 → 调用摘要协调层/缓存层/数据层 → 格式化返回值 | 不包含新的业务算法（核心算法属于摘要协调层和数据层）；不绕过下层模块直接访问底层资源 |

### 新增代码约束

1. **新增 MCP 工具**：在 `tools/` 目录下新增文件，使用 `@tool` 装饰器注册；工具 handler 中仅做参数校验与结果格式化，核心逻辑委托给摘要协调层或数据层。
2. **新增数据查询**：在数据层（`data/`）中新增查询函数或聚合逻辑；所有数据库访问必须通过 `CodeGraphDB`（只读封装）进行，不得在其他层直接使用 `sqlite3`。
3. **新增缓存文件类型**：在缓存管理模块（`cache/cache.py`）中新增对应的 `read_*`/`write_*`/`invalidate_*` 函数对；其他模块不得自行拼接 `.codesense/` 路径或直接调用 `Path.write_text`/`Path.read_text` 操作缓存文件。
4. **新增异常类型**：在 `errors.py` 中继承 `ToolError` 定义；工具实现内部抛出时，registry 的 `dispatch` 会自动转译为 `isError=true` 的 MCP 响应。
5. **分层检查清单**：新增代码前确认：
   - 是否引入了违反单向依赖的 import？（上层模块 import 下层 → 允许；反之 → 禁止）
   - 是否绕过了中间层直接访问底层资源？（如 `tools/` 中直接 `open()` `.codesense/` 文件 → 违规）
   - 职责是否与该模块定义一致？（如数据层中写入任何文件 → 违规）
6. **测试约束**：测试只能依赖第 0 层（错误定义、缓存管理、数据层）和工具注册层；不应依赖服务入口的 stdio 传输细节。测试中如需模拟 MCP 交互，使用 `build_server()` 获取 Server 实例注入 mock transport。
7. **数据库 schema 变更**：当 CodeGraph SQLite schema 变更时，仅需修改 `data/db.py` 中的 `CodeGraphDB` 类（如其模块文档所述：「此模块是 CodeGraph 内部存储的单一边界」），其他模块不应感知 schema 变化。

---

## 关键流程描述

### 流程1：MCP 工具调用全链路——从客户端请求到工具执行
**场景**：Agent 客户端通过 stdio 发起 `tools/call` 请求，需要路由到正确的工具实现并返回结果
**调用链**：服务入口 → 工具注册 → 工具实现 → (可选) 数据层
**关键步骤**：
1. `server._call_tool(name, arguments)` 接收 MCP SDK 回调，转发给 `registry.dispatch(name, arguments)`
2. `registry.dispatch` 在 `_REGISTRY` 字典中查找 `ToolSpec`；未找到返回 "未知工具" 错误
3. `registry.dispatch` 用 `jsonschema.Draft202012Validator` 校验参数 Schema；不通过时调用 `_translate_jsonschema_error` 将 `ValidationError` 转为中文错误消息
4. 校验通过andler(**arguments)` 执行工具函数；若函数为协程则 `await`
5. 捕获 `ToolError` 子类（`ValidationError`/`InvalidArgumentError`/`LLMError`）转换为 `isError=True` 的 `CallToolResult`
6. 成功结果包装为 `CallToolResult(content=[TextContent(...)], isError=False)` 返回给 MCP SDK

### 流程2：项目架构初始化——从首次调用 project_map 到完整缓存就绪
**场景**：Agent 在未初始化的项目中首次调用 `project_map`，系统引导 Agent 逐步生成全部 7 个知识段落
**调用链**：工具实现 → 数据层 → 缓存管理 → 摘要协调 → 工具注册(保存) → 缓存管理
**关键步骤**：
1. `tools.project_map.project_map` 调用 `resolve_project_root` 定位项目根目录，检查 `.codegraph/codegraph.db` 是否存在
2. 打开 `CodeGraphDB`，通过 `list_modules` / `module_dependencies` / `directory_tree` / `collect_identity_sources` 等数据层函数采集原始数据
3. 对 7 个段落分别计算哈希（`compute_identity_hash` / `compute_structure_hash` / `compute_architecture_hash` / `compute_dependencies_hash` / calls_edges SHA256 / symbol_map SHA256）
4. 对纯程序段 (02_structure/07_dependencies) 直接调用 `summarizer.render_structure_segment` / `render_dependencies_segment`，通过 `cache.write_segment` 写入 `.codesense/project_map_segments/`
5. 对需要 LLM 的段落 (01_identity/03_modules/04_constraints/05_flows/06_concepts) 判断 `cache.is_segment_valid`，缺失则返回引导步骤列表
6. Agent 调用 `get_identity_segment_prompt` / `get_modules_segment_prompt` 等工具获取提示词 → 生成内容 → 调用 `save_project_map_segment_tool` 保存
7. `save_project_map_segment_tool` 根据 `segment_id` 重新计算数据哈希，调用 `cache.write_segment` 写入段落
8. 全部 7 段就绪后 `project_map` 调用 `cache.render_project_map` 拼接段落为完整 `project_map.md`

### 流程3：模块摘要生成——从缓存未命中到 Agent 生成并持久化
**场景**：用户通过 `explore_module` 查询某模块详情，该模块摘要尚未生成或缓存已过期
**调用链**：工具实现 → 缓存管理 → 数据层 → 摘要协调 → 工具注册(保存) → 缓存管理
**关键步骤**：
1. `tools.explore_module.explore_module` 调用 `resolve_project_root` → 检查 DB 存在 → 调用 `cache.read_modules_index` 读取模块索引
2. 在模块索引中查找 `module_name`：L2 辅助目录直接返回简要信息；L1 模块查 `_compute_module_hash(entry, db)` 获取当前内容哈希
3. `cache.read_module` + `cache.read_module_hashes` 检查缓存有效性；`is_auto_expire_enabled()` 决定是否按哈希过期
4. 缓存命中直接返回 Markdown；缓存未命中时返回生成引导（含子 Agent 提示词）
5. Agent 调用 `get_module_prompt_tool` → `summarizer.get_module_prompt` → 读取模块索引和 `CodeGraphDB` → 查询 `cross_dir_public_api`+`external_dependencies_by_dir`+文件/符号文档字符串 → `_build_module_prompt` 组装 LLM 提示词
6. Agent 生成 Markdown 摘要后调用 `save_module_summary_tool` → `summarizer.save_module_summary` → 打开 `CodeGraphDB` 计算 `_compute_module_hash` → `cache.write_module` 写入 `.codesense/modules/<key>.md` 并更新 `.hashes.json`
7. Agent 重新调用 `explore_module` → 缓存命中 → 返回模块摘要

### 流程4：模块划分提交——从 Agent 生成模块列表到项目地图渲染
**场景**：`project_map` 提示 `03_modules` 缺失 → Agent 获取提示词生成模块划分文本 → 调用 `submit_project_map` 提交 → 驱动多段缓存更新
**调用链**：工具实现 → 摘要协调 → 数据层 → 缓存管理
**关键步骤**：
1. `tools.submit_project_map.submit_project_map_tool` 调用 `summarizer.submit_project_map(project_root, response)`
2. `submit_project_map` 计算 `cache.db_hash` → 打开 `CodeGraphDB` → 采集 `list_modules`/`module_dependencies`/`directory_symbols` → `_resolve_roots_and_aux` 确定根目录和辅助目录
3. `_parse_modules_text` 解析 `模块名|职责|目录` 格式文本 → 模糊匹配目录名 (`_normalize_dir` + `difflib.get_close_matches`) → 去重冲突检测 → 输出 `modules_json`
4. `_expand_module_files` 将目录展开为具体文件列表 → 处理父子目录排除 → 区分目录模块和文件模块
5. `_migrate_renamed_module_caches` 通过模块哈希匹配重命名模块 → 复用已有 `.md` 缓存
6. `cache.write_modules_index` 写入 `modules_index.json` → 裁剪过期模块文件 (`_prune_stale_modules`)
7. 同步计算 `03_modules` 段落哈希 → 若缓存无效则调用 `_render_basic_architecture_segment` 生成 → `cache.write_segment`
8. 强制刷新 `07_dependencies` 段落 → `render_dependencies_segment` → `cache.write_segment`
9. `cache.render_project_map` 拼接全部 7 段为 `project_map.md`
10. 返回 "模块划分已保存（N 个模块）。请重新调用 project_map 获取完整架构概览。"

### 流程5：服务器启动与工具注册——从进程启动到就绪等待请求
**场景**：`codesense` 命令被执行，MCP stdio 服务器启动并注册所有工具
**调用链**：服务入口 → 工具注册 → 工具实现(模块导入触发)
**关键步骤**：
1. `server.main()` 调用 `_init_codesenseignore()` 在 `.codesense/` 下创建 `.codesenseignore` 模板 → 调用 `asyncio.run(run_stdio())`
2. `server.build_server()` 创建 `mcp.server.Server` 实例，注册 `_list_tools` 和 `_call_tool` 两个回调
3. `server.py` 顶部的 `from codesense_v1 import tools as _tools` 触发 `tools/__init__.py` 导入所有工具模块
4. 各工具模块（`project_map.py`/`explore_module.py`/`get_flows_segment_prompt.py` 等）的 `@registry.tool(...)` 装饰器在导入时执行，调用 `registry.tool` 将 `ToolSpec` 注册到 `_REGISTRY` 字典
5. 同名工具重复注册时 `registry.tool` 立即抛出 `RuntimeError`，阻止启动
6. `server.run_stdio()` 使用 `mcp.server.stdio.stdio_server()` 打开标准输入/输出流 → `server.run(read_stream, write_stream, ...)` 进入事件循环
7. MCP 客户端连接后发送 `tools/list` → `_list_tools` 调用 `registry.list_tools()` 遍历 `_REGISTRY` 返回所有已注册 `Tool` 对象

---

## 概念索引

| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |
|-----------------|---------|---------|------|
| 项目映射 | 工具实现 / 摘要协调 | project_map / get_project_map_prompt | 工具实现 是 MCP 入口，摘要协调 是核心逻辑 |
| 模块划分 | 摘要协调 | submit_project_map / _parse_modules_text | 将模块文本解析为结构化缓存 |
| 模块探索 | 工具实现 | explore_module / get_module_prompt | 查看模块内部结构、文件和符号 |
| 缓存失效 | 缓存管理 | invalidate / invalidate_segments / is_cache_valid | 对比 db_hash 判断缓存是否需要重建 |
| segment(段落) | 缓存管理 / 摘要协调 | read_segment / write_segment / save_project_map_segment | project_map 由多个 segment 组成，可独立缓存和重建 |
| prompt 生成 | 摘要协调 | get_identity_segment_prompt / get_module_prompt / get_project_map_prompt | 为 LLM 分析生成上下文 prompt |
| 工具注册 | 工具注册 | ToolSpec / tool(装饰器) / dispatch | 声明式 MCP 工具定义，参数 JSON Schema 自动校验 |
| MCP 工具调用 | 服务入口 / 工具实现 | _call_tool / build_server | 服务入口 接收 → 工具注册 分发 → 工具实现 执行 |
| 项目根路径 | 工具实现 | resolve_project_root | 通过 MCP roots / 环境变量 / CWD 搜索定位项目根 |
| 代码图数据库 | 数据层 | CodeGraphDB / NodeRow / EdgeRow | 文件/符号/边的结构化存储与查询 |
| 目录依赖 | 数据层 | directory_edges / directory_dependencies | 模块间 import 依赖关系聚合 |
| 架构特征 | 数据层 | ArchitectureFeatures / DirCentrality | 计算目录中心性和架构层级 |
| 缓存哈希 | 缓存管理 | db_hash / compute_structure_hash | 用于检测代码变更以触发缓存失效 |
| project_map vs save_project_map_segment | 工具实现 vs 缓存管理 | project_map / save_project_map_segment_tool | project_map 返回完整架构概览；save_project_map_segment 仅保存单个段落到缓存 |
| submit_project_map vs submit_project_map_tool | 摘要协调 vs 工具实现 | submit_project_map / submit_project_map_tool | 摘要协调 是核心逻辑；工具实现 是 MCP 包装入口 |
| 错误处理 | 错误定义 | ToolError / ValidationError / LLMError / InvalidArgumentError | 所有异常继承 ToolError 基类 |
| 架构摘要 | 摘要协调 | render_project_map_markdown / get_architecture_segment_prompt | 将模块数据渲染为 Markdown 架构文档 |

---

## 上下游详表

| 模块 | 上游（依赖于我） | 下游（我依赖） |
|------|----------------|--------------|
| 工具实现 | 无 | 工具注册、摘要协调、数据层、缓存管理、错误定义 |
| 工具注册 | 工具实现、服务入口 | 错误定义 |
| 摘要协调 | 工具实现 | 数据层、缓存管理、错误定义 |
| 数据层 | 工具实现、摘要协调 | 无 |
| 服务入口 | 无 | 工具注册 |
| 缓存管理 | 工具实现、摘要协调 | 无 |
| 错误定义 | 工具实现、工具注册、摘要协调 | 无 |

> 无循环依赖。