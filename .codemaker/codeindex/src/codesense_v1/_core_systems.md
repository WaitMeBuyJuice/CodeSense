---
module_id: _global
architectural_role: "核心子系统详解"
---

## 1. 工具注册调度系统 (registry)

负责 MCP Tool 的声明式注册与统一调度。核心是 `_ToolRegistry` 全局单例：

- **@tool 装饰器**：接收 tool 名称、描述和 JSON Schema，将函数注册到 `_tools: dict`。
- **list_tools()**：遍历已注册 tool，生成 MCP `Tool` 对象列表，供 server 响应 `tools/list`。
- **dispatch(name, args)**：按名称查找 handler → jsonschema 校验 → 调用 handler → 捕获 `ToolError` 转为 MCP `isError` 响应。

6 个 tool 函数（在 tools 层）通过 `@tool` 装饰器自注册，server 层只调用 `list_tools` 和 `dispatch`。

## 2. 缓存系统 (cache + Lazy Cache 模式)

实现 **Lazy Cache with Agent-Driven Generation** 模式：

- **缓存文件**：`.codesense/project_map.md`（项目架构）、`.codesense/modules/modules_index.json`（模块索引）、`.codesense/modules/<name>.md`（每个模块的摘要）。
- **有效性校验**：`db_hash`（CodeGraph DB 的 SHA256）用于 project_map 缓存失效；`module_hashes`（各模块内容哈希）用于模块级缓存失效。
- **命中路径**：tools 层查询 cache → 命中直接返回缓存内容 → Agent 零等待。
- **未命中路径**：tools 返回结构化工作流指令 → Agent 调用 `get_*_prompt` → 生成内容 → `submit/save` 写入 cache。

## 3. 代码分析系统 (data)

封装对 CodeGraph SQLite 数据库（`.codegraph/codegraph.db`）的只读查询，在文件级依赖图之上提供语言无关的架构分析：

- **CodeGraphDB** (`db.py`)：SQLite 只读连接封装，定义 `FileRow`/`NodeRow`/`EdgeRow`。
- **文件级依赖** (`modules.py`)：将节点/边映射为 `Module`/`ModuleEdge`，提供 `module_dependencies`。
- **架构分析** (`architecture.py`)：Tarjan SCC 循环检测、拓扑排序 (topological_layers)、中心性分析 (fan-in/fan-out)、跨目录公开 API 提取 (cross_dir_public_api)。
- **目录级聚合** (`aggregate.py`)：文件级边聚合到目录级，提供 `directory_dependencies`、`directory_symbols`、`directory_tree`。
- **文档提取** (`docstrings.py`)：直接读取源文件提取 module docstring 和 symbol docstring。
- **参考文档** (`ref_docs.py`)：扫描项目参考文档目录。

## 4. LLM Prompt 系统 (summarizer)

位于 tools 和 data/cache 之间的桥梁，负责：

- **Prompt 构建**：从 data 层获取目录符号、依赖拓扑、循环依赖、docstring 等结构化数据 → 组装为 Markdown 格式的 LLM 分析 prompt。
- **目录解析**：`_resolve_roots_and_aux` 确定 L1 核心目录与 L2 辅助目录，过滤出根目录下的依赖关系。
- **解析与保存**：`submit_project_map` 解析 pipe-delimited 文本 → 写入 modules_index + project_map；`save_module_summary` 保存单模块摘要 → 更新 module_hash。
- **公开 API**：`get_project_map_prompt`、`submit_project_map`、`get_module_prompt`、`save_module_summary` 四个函数。

## 5. MCP 工具集 (tools)

CodeSense 对外暴露的 6 个 MCP Tool endpoint：

| Tool | 用途 | 缓存行为 |
|------|------|---------|
| `project_map` | 获取项目架构概览 | 命中直接返回，未命中返回生成指令 |
| `explore_module` | 获取指定模块摘要 | 命中返回 Markdown 摘要，未命中返回生成指令 |
| `get_project_map_prompt` | 返回项目模块划分的 LLM 分析 prompt | 无缓存（每次实时生成） |
| `get_module_prompt` | 返回指定模块的 LLM 分析 prompt | 无缓存（每次实时生成） |
| `submit_project_map` | 提交 Agent 生成的模块划分结果 | 写入 cache |
| `save_module_summary` | 保存 Agent 生成的模块摘要 | 写入 cache |

每个 tool 函数遵循统一模式：`环境变量检查 → 参数校验 → 缓存查询 → 命中返回 / 未命中委派 summarizer`。
