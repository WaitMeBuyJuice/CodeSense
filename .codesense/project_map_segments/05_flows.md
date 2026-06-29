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