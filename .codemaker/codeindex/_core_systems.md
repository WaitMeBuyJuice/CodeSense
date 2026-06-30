---
repo: CodeSense_V1
generated_at: 2026-06-29
---

# CodeSense_V1 核心子系统

## 子系统列表

CodeSense_V1 围绕两条核心工作流组织，每条工作流跨多个模块协作：

| 子系统 | 涉及模块 | 业务定位 |
|--------|---------|---------|
| 项目架构概览（project_map） | tools / summarizer / data / cache | 生成并缓存项目级架构 Markdown（仓库定位+技术栈+目录结构+模块列表+依赖关系） |
| 模块深度理解（explore_module） | tools / summarizer / data / cache | 生成并缓存单个模块的架构描述（职责+对外接口+内部文件+上下游依赖） |
| 工具注册与分发 | server / registry / errors | 接收 MCP tools/list 与 tools/call，校验参数，路由到 handler，统一错误转换 |
| CodeGraph 数据查询 | data | 只读查询 CodeGraph SQLite DB，提供文件/模块/依赖/架构分析/内容指纹 |
| 缓存管理 | cache | `.codesense/` 目录的读写与失效（segment 缓存 + 模块摘要缓存 + meta） |

## 关键流程描述

### 流程 1：project_map 段化生成（懒加载 + Agent 协作）

project_map 不是一次生成，而是按 4 段懒加载，程序段与 Agent 段分工：

1. **02_structure / 04_dependencies（程序段）**：project_map 工具每次调用都计算源 hash，缺失或 hash 不匹配时由 `summarizer.render_structure_segment` / `render_dependencies_segment` 纯程序渲染并写 `cache.write_segment`。无需 Agent 介入。
2. **01_identity / 03_modules（Agent 段）**：缺失时 project_map 返回引导 Markdown，指示 Agent：
   - 01_identity → 调 `get_identity_segment_prompt` 取提示词 → 生成内容 → `save_project_map_segment(segment_id="01_identity", content=...)`
   - 03_modules → 调 `get_modules_segment_prompt` 取提示词 → 按竖线格式生成模块划分 → `submit_project_map(response=...)`
3. **submit_project_map 内部**：`_parse_modules_text` 解析竖线文本（目录 fuzzy 校正 cutoff=0.85、去重、冲突丢弃、超长截断 DESC_MAX_LEN=60、模块名长度 2~20），`_expand_module_files` 展开目录到文件（父子目录排除避免重叠、单文件模块支持），`_migrate_renamed_module_caches` 按 content hash 复用重命名模块的旧 .md，最后写 modules_index + 03/04 段 + render。
4. 全段就绪后 `cache.render_project_map` 按 `01→02→03→04` 顺序拼接（`\n\n---\n\n` 分隔）写回 `project_map.md` 并返回。

> 设计决策：切换为竖线分隔文本而非 JSON，因大项目（~200 文件）下 LLM 频繁遗漏 JSON 逗号；竖线格式单行坏了跳过不影响其他行，失败率大幅降低。

### 流程 2：explore_module 模块摘要（per-module 缓存 + Agent 协作）

1. explore_module 接收 `module_name`（project_map 中列出的精确模块名，非目录路径）。
2. 读 `modules_index.json`（缺失→引导先 project_map）；先查 L2 辅助目录（tests/scripts 等返回简短说明）。
3. 在 L1 模块列表找 entry（trim + 大小写不敏感；找不到→抛 InvalidArgumentError 列出可用模块）。
4. `_compute_module_hash`（sha1 of sorted files + symbol fingerprints `file:name:kind:sig`）+ 读 `modules/<safe_key>.md` + 读 `.hashes.json`。
5. auto-expire 开启时比对 per-module hash；关闭时存在即有效。命中返回缓存。
6. 未命中返回引导：让 Agent（或子 Agent）调 `get_module_prompt(module_name)` 取提示词 → 生成 Markdown 摘要 → `save_module_summary(module_name, summary)` 保存 → 重新 explore_module。

> 设计决策：模块边界由 LLM 推断（Week5 改造，原 Week3 用 `__init__.py` 判断只支持 Python 包）；explore_module 入参由 `module_path` 改为 `module_name`，支持 TypeScript/Go 等非 Python 项目。

### 流程 3：缓存失效策略

- **DB 级失效**：`db_hash`（SHA-256 of codegraph.db）存于 `project_map.json` meta；`CODESENSE_CACHE_AUTO_EXPIRE=false` 时跳过 hash 比对。
- **Segment 级失效**：每段独立存 `.hash` 文件（compute_identity/structure/architecture/dependencies_hash），`is_segment_valid` 比对源 hash。
- **模块级失效**：per-module content hash 存 `modules/.hashes.json`，模块文件/符号签名变化即失效。
- **全量清空**：`cache.invalidate` 删 project_map.md / modules_index.json / meta / 整个 modules/ 目录；`invalidate_segments` 清 project_map_segments/。
- **增量清理**：`write_modules_index` 时 `_prune_stale_modules` 只删不再存在的模块 .md + .hashes 条目，保留存活模块缓存。

### 流程 4：工具注册与分发

- **注册**：`tools/__init__.py` import 全部 8 个工具模块 → 各模块 `@tool` 装饰器把 `ToolSpec(name, description, input_schema, handler)` 写入全局 `_REGISTRY` dict → 重复注册抛 RuntimeError（启动期错误）。server import tools（noqa F401）触发整链。
- **分发**：`registry.dispatch(name, arguments)` → 查 `_REGISTRY` → `jsonschema.Draft202012Validator` 校验（失败翻中文错误）→ `spec.handler(**args)`（支持同步/async，awaitable 自动 await）→ 捕获 `ToolError` → `isError=true`；捕获其他 Exception → `内部错误：<ExcType>: <e>`。**永不抛异常**，所有错误转为 CallToolResult。

## 已知设计取舍

| # | 取舍 | 理由 |
|---|------|------|
| T1 | 缓存粒度 = project 级 db_hash + per-module content hash | 简单可靠；模块级 hash 精细化失效，避免全量重生 |
| T2 | project_map 段化懒加载 | 01/03 需 LLM，分拆让程序段即时返回，Agent 段按需生成 |
| T3 | 模块边界由 LLM 推断（非 `__init__.py`） | 语言无关，支持 TypeScript/Go 等；Week5 为 codegraph-main 实验改造 |
| T4 | CodeSense 不直接调 LLM | LLM 调用交宿主 Agent（可委派子 Agent），CodeSense 只产 prompt + 解析 + 渲染 |
| T5 | `project_root` 单值（环境变量） | 一个 MCP Server 实例只服务一个项目；不支持多项目切换 |
| T6 | 引导型工具错误返回 Markdown 而非异常 | 保证被动/主动语义不被破坏，Agent 能读到生成步骤 |
| T7 | 竖线文本而非 JSON 提交模块划分 | 大项目下 LLM 频繁漏 JSON 逗号；竖线单行坏了跳过不影响其他行 |
| T8 | `_nonce` 参数绕过客户端重复调用检测 | 同会话多次调 project_map 需不同 nonce，否则被客户端拦截 |
