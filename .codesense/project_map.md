## 仓库定位

CodeSense 是一个 MCP（Model Context Protocol）服务，帮助 AI Agent 快速理解代码仓库的高层架构：项目组织方式、模块职责、内部结构以及模块间协作关系。

它读取 CodeGraph 生成的代码知识图谱（`.codegraph/codegraph.db`），按"全局 → 模块 → 子模块"的层级，向 Agent 提供结构化的认知信息，并把生成的摘要缓存到 `.codesense/` 目录复用。目标用户为宿主 AI Agent（如 CodeMaker）及通过 MCP 协议接入的客户端。核心价值在于：不直接调用 LLM，而是把 Data Layer 抽取的结构数据拼装成 prompt 返回给宿主 Agent，由 Agent 生成自然语言摘要后通过 `save_*` / `submit_*` 工具写回缓存——这种"Agent 即 LLM"协作模式避免了 API Key 硬编码，并让 prompt 迭代与生成解耦。

## 技术栈

| 类别 | 内容 |
|------|------|
| 主语言 | Python（>=3.14） |
| 核心框架 | MCP（Model Context Protocol，stdio 服务） |
| 关键依赖 | mcp、jsonschema、openai>=2.41.1、json-repair>=0.30、pathspec>=0.12 |
| 构建工具 | hatchling（wheel 打包，packages=src/codesense_v1） |
| 类型检查 | mypy（strict，python_version=3.14） |
| Linter | ruff（line-length=100，规则 E/F/I/B/UP） |
| 测试框架 | pytest + pytest-asyncio（asyncio_mode=auto，testpaths=tests） |
| 包管理 | uv（推荐） |
| 入口 | `codesense = codesense_v1.server:main` |

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

## 模块划分

依据 `src/codesense_v1/` 顶层目录结构划分，对应架构图 L1-L7 分层。每个模块给出英文名 key、中文名、一句话职责、文件路径。

| 英文名 key | 中文名 | 职责 | 文件路径 |
|------------|--------|------|----------|
| server | 入口层（L1） | MCP stdio 服务入口，实现 list_tools / call_tool / list_prompts / get_prompt | src/codesense_v1/server/ |
| registry | 注册分发层（L2） | @tool 装饰器注册、JSON Schema 校验、工具派发 | src/codesense_v1/registry/ |
| tools | 工具层（L3） | project_map / explore_module / explore_submodule / save_* / submit_* 等 MCP 工具实现 | src/codesense_v1/tools/ |
| data | 数据层（L4） | 查询 CodeGraph SQLite（modules / architecture / docstrings / files 等） | src/codesense_v1/data/ |
| summarizer | 摘要层（L6） | 将 Data Layer 结构数据拼装为 Markdown prompt | src/codesense_v1/summarizer/ |
| cache | 基础设施层（L7） | .codesense/ 读写、DB hash 计算、缓存失效判断 | src/codesense_v1/cache/ |
| skills | 内置 Skills | 内置 Skill 文件（启动时写入 .claude/skills/，MCP Prompts 协议备用） | src/codesense_v1/skills/ |
| errors | 统一异常 | ToolError 异常体系 | src/codesense_v1/errors.py |

### 模块文件清单

- **server**: src/codesense_v1/server/
- **registry**: src/codesense_v1/registry/
- **tools**: src/codesense_v1/tools/__init__.py, _project_root.py, explore_module.py, explore_submodule.py, project_map.py, save_module_summary.py, save_project_map_segment.py, save_submodule_summary.py, submit_project_map.py
- **data**: src/codesense_v1/data/
- **summarizer**: src/codesense_v1/summarizer/
- **cache**: src/codesense_v1/cache/
- **skills**: src/codesense_v1/skills/
- **errors**: src/codesense_v1/errors.py

---

## 模块边界规则

### 层次约束
- 依赖单向流向：`server` → `registry` → `tools` → `summarizer` / `cache` / `data`
- `cache` 和 `data` 是第 0 层基础模块，不依赖任何上层模块
- `tools` 层是上层协调者，可以调用 `cache`、`data`、`registry`、`summarizer`，但反向禁止

### 访问禁忌
- `cache` 模块禁止调用 `data`、`summarizer`、`tools`、`registry`、`server`
- `data` 模块禁止调用 `cache`、`summarizer`、`tools`、`registry`、`server`
- `summarizer` 禁止调用 `tools`、`registry`、`server`
- `registry` 禁止调用 `tools`、`summarizer`

### 职责边界
- `cache` 层：只负责 `.codesense/` 目录下文件的读/写/校验/失效，不做任何业务逻辑
- `data` 层：只做 CodeGraph 数据库查询与目录依赖聚合，不写任何缓存文件
- `summarizer` 层：只负责生成 Prompt 和渲染 Markdown，不直接注册 MCP 工具
- `registry` 层：只负责工具元数据管理和参数校验，不执行工具逻辑
- `tools` 层：MCP 工具的唯一实现层，负责协调各层完成工具请求
- `server` 层：只负责 stdio 服务器启动与 MCP 协议桥接

### 新增代码约束
- 新增 MCP 工具必须在 `registry` 注册元数据，在 `tools` 层实现逻辑
- 缓存文件结构变更需同步更新 `cache.py` 中的常量与对应 `read_*/write_*` 函数
- 所有 `read_*` 函数须在任何异常时返回 `None`（静默 miss），`write_*` 函数可传播 `OSError`
- 禁止在 `cache` 层之外直接操作 `.codesense/` 目录

---

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