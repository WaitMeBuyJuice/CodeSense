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