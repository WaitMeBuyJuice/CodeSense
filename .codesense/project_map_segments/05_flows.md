## 关键流程描述

### MCP 工具调用流程
**场景**：客户端通过 stdio 发送 ToolCall 请求
**调用链**：server → registry → tools → summarizer → data / cache
**关键步骤**：
1. `server.build_server()` 注册 `_list_tools` 和 `_call_tool` 回调
2. 客户端调用工具时，`registry.dispatch(name, arguments)` 进行 jsonschema 校验并路由到对应工具函数
3. 工具函数（如 `project_map`、`explore_module`）解析参数，调用 `summarizer` 的渲染/哈希函数
4. summarizer 读取 `cache` 查询缓存是否有效，无效则调用 `data` 模块重新分析
5. 结果以 `CallToolResult` 格式返回客户端

### 项目架构初始化流程（project_map）
**场景**：用户在未初始化的项目目录首次调用 `project_map`
**调用链**：project_map → data (CodeGraphDB) → summarizer（渲染）→ cache（读写）
**关键步骤**：
1. `resolve_project_root()` 定位项目根目录
2. `data.list_modules(db)` 从 CodeGraph 数据库提取模块和依赖边
3. `data.classify_top_dirs()` 分类顶级目录结构
4. 计算各段 hash，与 `cache.is_segment_valid()` 比对
5. summarizer 渲染 `02_structure`、`07_dependencies` 段 → cache.write_segment() 写入
6. 返回缺失段落引导，Agent 逐段生成后重新调用

### 模块探索流程（explore_module）
**场景**：用户指定模块名查询其架构理解
**调用链**：explore_module → cache → data → summarizer → cache
**关键步骤**：
1. 校验 `module_name` 非空，读取 `modules_index` 确认模块存在
2. 检查是否为 L2 辅助目录（直接返回分类信息）
3. 查找 L1 模块条目，计算模块 hash → 比对 `cache.read_module()`
4. 缓存命中 → 直接返回 Markdown 摘要
5. 缓存未命中 → 返回「子 Agent 生成流程」指导，Agent 调用 `get_module_prompt` → 分析 → `save_module_summary` → 重新调用 `explore_module`

### 缓存失效与自动过期
**场景**：代码变更后确保 Agent 不读取过期缓存
**调用链**：tools → summarizer → cache
**关键步骤**：
1. `is_auto_expire_enabled()` 判断是否启用自动过期
2. project_map/explore_module 计算各段内容 hash
3. `cache.is_segment_valid()` 比对存储 hash 与当前 hash，不一致则标记失效
4. 无效段触发重新生成流程