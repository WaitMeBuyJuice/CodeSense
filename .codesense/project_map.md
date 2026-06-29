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

项目采用严格三层架构，单向依赖：

```
入口层 (server / tools) → 中间层 (summarizer / registry) → 基础层 (data / cache / errors)
```

- 基础层（第0层）不依赖任何项目内模块
- 中间层（第1层）只能依赖基础层
- 入口层（第2层）可依赖中间层和基础层
- 严禁反向依赖（如 data 调用 summarizer）

### 访问禁忌

- **tools 禁止直接操作 `.codesense/` 目录**：所有缓存读写必须通过 cache 模块
- **tools 禁止直接调用 CodeGraphDB 查询**：所有数据查询必须通过 data 模块
- **cache 禁止导入 data 或 summarizer**：cache 是纯 I/O 层
- **data 禁止写入任何缓存文件**：data 只读文件系统 + CodeGraph DB，不产生副作用
- **server 禁止直接调用 data/cache**：server 只能通过 registry 分发到 tools

### 职责边界

| 模块 | 唯一职责 |
|------|---------|
| errors | 定义异常类型，无业务逻辑 |
| cache | `.codesense/` 目录下所有文件的 CRUD + 校验 + 失效 |
| data | 代码仓库静态分析（文件扫描、符号提取、目录依赖聚合、CodeGraph DB 查询） |
| registry | MCP 工具元数据注册 + jsonschema 参数校验 + 工具调用路由 |
| summarizer | 组合 data + cache 的输出，生成/渲染 Markdown 架构摘要 |
| server | MCP stdio 生命周期管理，启动/停止服务器 |
| tools | 每个文件一个 MCP 工具实现，解析参数后委托给 summarizer |

### 新增代码约束

- 新增 MCP 工具：在 `tools/` 下新建文件，实现 `async def xxx(args) -> list[TextContent]`，然后在 `registry/registry.py` 中注册
- 新增异常类型：继承 `errors.ToolError`，不得直接使用 `Exception`
- 缓存键命名：使用 `cache.module_key()` 和 `cache.safe_key()` 生成，不要手写路径
- 类型注解：所有公开函数必须有完整类型注解（mypy strict 模式）

---

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

---

## 概念索引

| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |
|-----------------|---------|---------|------|
| 项目架构概览 | tools | project_map | 返回整个仓库的高层架构信息 |
| 模块探索 | tools | explore_module | 深入查看单个模块的接口与依赖 |
| 子模块探索 | tools | explore_submodule | 查看模块内某个文件的细节 |
| 缓存失效 | cache | invalidate, invalidate_segments | 清除过期缓存数据 |
| 缓存校验 | cache | is_cache_valid, is_segment_valid | 比对 hash 判断缓存是否有效 |
| 缓存读取 | cache | read_project_map, read_module, read_segment | 从 .codesense/ 读取缓存 |
| 缓存写入 | cache | write_module, write_segment, write_project_map | 写入架构摘要到 .codesense/ |
| 模块划分提交 | summarizer | submit_project_map | Agent 提交模块划分结果，与 save_project_map_segment 不同：前者通过文本行提交全部模块，后者保存单个段落 |
| 段落保存 | summarizer | save_project_map_segment | 保存 project_map 的某个段落（如 01_identity），与 submit_project_map 不同 |
| 模块摘要保存 | summarizer | save_module_summary | 保存单个模块的完整架构摘要 |
| 提示词获取 | summarizer | get_project_map_prompt, get_module_prompt | 返回 LLM 分析提示词，供 Agent 生成摘要 |
| 工具注册 | registry | tool, deco, list_tools | 装饰器注册 MCP 工具 + 导出工具列表 |
| 工具分发 | registry | dispatch | jsonschema 校验 + 路由到具体工具函数 |
| 数据库查询 | data | CodeGraphDB | 封装 CodeGraph SQLite 数据库的查询接口 |
| 目录依赖 | data | directory_dependencies, directory_edges | 聚合同目录下文件级边为目录级依赖 |
| 架构特征 | data | ArchitectureFeatures, architecture_features | 提取项目的架构特征（循环依赖、层次等） |
| 文档字符串提取 | data | extract_file_docstring, extract_symbol_docstrings | 提取源码中的文件/符号文档注释 |
| 项目根定位 | tools | resolve_project_root | 通过环境变量/MCP根目录/CWD搜索定位项目根 |
| 服务器入口 | server | main, run_stdio | 启动 stdio MCP 服务器主循环 |
| 异常层级 | errors | ToolError, ValidationError, InvalidArgumentError, LLMError | 所有业务异常继承 ToolError，区分不同错误类型 |

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