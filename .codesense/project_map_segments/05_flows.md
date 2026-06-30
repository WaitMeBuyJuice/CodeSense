## 关键流程描述

### 流程1：MCP 工具调用（以 project_map 为例）
**场景**：Agent 调用 `project_map` 工具获取项目架构信息
**调用链**：`server._call_tool` → `tools.project_map` → `summarizer.get_project_map_prompt` → `cache.read_segment` / `cache.write_segment` → `data.CodeGraphDB`
**关键步骤**：
1. `server._call_tool` 收到 MCP 请求，查找 `registry` 中注册的工具并路由
2. `tools.project_map` 解析 project root，检查各 segment 是否命中缓存（`cache.is_segment_valid`）
3. 若段落缓存命中，直接返回；若 miss，调用 `summarizer.get_project_map_prompt` 生成 prompt 并内嵌返回给 Agent
4. Agent 推理完成后调用 `save_project_map_segment_tool`，写入 `cache.write_segment`
5. 所有段落就绪后，`cache.render_project_map` 拼接各段输出最终 Markdown

### 流程2：模块摘要生成（explore_module）
**场景**：Agent 调用 `explore_module` 查询某模块内部结构
**调用链**：`tools.explore_module` → `summarizer.get_module_prompt` → `cache.read_module` / `cache.is_cache_valid` → `data.CodeGraphDB` → `cache.write_module`
**关键步骤**：
1. `tools.explore_module` 读取 `cache.read_module` 判断是否命中模块概览缓存
2. 缓存有效（hash 匹配）则直接返回已存 Markdown
3. 缓存 miss 时，调用 `summarizer.get_module_prompt` 从 `data` 层查询模块文件与依赖，构造推理 prompt
4. Agent 调用 `save_module_summary_tool`，写入 `cache.write_module` 并更新 hash

### 流程3：子模块文档生成（explore_submodule）
**场景**：Agent 深入探索某文件级子模块
**调用链**：`tools.explore_submodule` → `summarizer.get_submodule_prompt` → `cache.read_submodule` / `cache.read_submodule_hashes` → `data.CodeGraphDB` → `cache.write_submodule`
**关键步骤**：
1. 根据 `(module_key, file_key)` 读取子模块缓存文档
2. 对比 `cache.read_submodule_hashes` 中的 hash 决定是否重新生成
3. miss 时由 `summarizer._build_submodule_prompt` 提取文件符号与调用链构造 prompt
4. Agent 完成推理后调 `save_submodule_summary_tool` → `cache.write_submodule`

### 流程4：缓存失效与重建
**场景**：DB 文件变更导致缓存过期，或用户主动触发 invalidate
**调用链**：`tools.project_map._seg_valid` → `cache.is_cache_valid` / `cache.is_segment_valid` → `cache.invalidate` / `cache.invalidate_segments`
**关键步骤**：
1. `_seg_valid` 计算当前 DB 的 SHA-256 hash（`cache.db_hash`），与存储 hash 比对
2. 不匹配时标记 segment 为无效，触发重新生成流程
3. `invalidate` 删除 `project_map.md`、`modules_index.json`、`project_map.json` 及整个 `modules/` 目录
4. `invalidate_segments` 单独清除 `project_map_segments/` 下所有段落文件

### 流程5：服务启动
**场景**：MCP 服务器初始化
**调用链**：`server.main` → `server.run_stdio` → `server.build_server` → `registry` 注册工具 → `mcp.run_stdio`
**关键步骤**：
1. `main` 入口调用 `build_server` 创建 MCP Server 实例
2. `build_server` 遍历所有 `tools` 模块，通过 `registry` 获取工具描述与 schema 并注册到 Server
3. `run_stdio` 启动 stdio 传输，等待 CodeMaker Agent 连接并分发工具调用