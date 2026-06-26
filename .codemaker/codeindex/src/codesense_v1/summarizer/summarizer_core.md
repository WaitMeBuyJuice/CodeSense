## entity_names.constants

| 常量名 | 位置 | 说明 |
|--------|------|------|
| `_CODESENSE_DIR_NAME` | summarizer.py:module-level | `".codesense"` — 缓存目录名称 |
| `_DEFAULT_INCLUDE_ROOTS` | summarizer.py:module-level | `("src",)` — 默认 L1 根目录元组 |
| `_EXTERNAL_PREFIX` | summarizer.py:module-level | `"[ext]"` — 外部依赖前缀标记 |
| `_DATA_TRUST_NOTICE` | `_build_module_prompt` 内部 | 数据可信度说明文本（静态分析局限、docstring 可能过期等） |

> 注：`_PROJECT_MAP_FORMAT` / `_MODULE_SUMMARY_FORMAT` 并非独立常量；项目架构格式说明与模块摘要格式说明分别嵌入在 `_build_project_map_prompt()` 和 `_build_module_prompt()` 函数体内，以 f-string + 硬编码 Markdown 模板形式存在。

## entity_names.functions

### 公开 API（4 个，被 tools 模块调用）

| 函数 | 签名 | 职责 |
|------|------|------|
| `get_project_map_prompt` | `async (project_root: Path) -> str` | 从 DB 提取所有目录、依赖、拓扑层、循环、docstring，调用 `_build_project_map_prompt` 组装 LLM prompt |
| `submit_project_map` | `async (project_root: Path, response: str) -> str` | 解析 pipe-delimited 文本 → 生成 modules_index JSON → 写入 project_map.md 缓存 |
| `get_module_prompt` | `async (project_root: Path, module_name: str) -> str` | 查找模块 entry → 提取该模块文件符号/公开 API/外部依赖/docstring → 调用 `_build_module_prompt` 组装 LLM prompt |
| `save_module_summary` | `(project_root: Path, module_name: str, summary: str) -> None` | 写入模块摘要缓存 + 更新 per-module hash |

### 内部函数（5 个，仅 summarizer 内部使用）

| 函数 | 职责 |
|------|------|
| `_compute_module_hash` | 计算模块内容 SHA1 哈希（files + symbols），用于缓存失效判断 |
| `_resolve_roots_and_aux` | 解析 L1 核心目录 / L2 辅助目录（优先级：`CODESENSE_INCLUDE_DIRS` → `src/` 默认 → 自动检测） |
| `_filter_dir_deps` | 过滤出两端均在 roots 下的目录依赖 |
| `_is_under_roots` | 判断目录是否在 roots 下（等于或嵌套） |
| `_build_project_map_prompt` | 组装模块划分 LLM prompt（目录 + 符号 + 依赖 + 拓扑 + 循环 + 参考文档 + 输出格式） |
| `_build_module_prompt` | 组装模块详细分析 LLM prompt（文件 + 符号 + 对外 API + 依赖 + 外部库 + `_DATA_TRUST_NOTICE`） |

## retrieval_hints

1. **找 LLM prompt 生成逻辑**：`_build_project_map_prompt` 和 `_build_module_prompt` 是最终拼装 prompt 字符串的函数，内含完整的 Markdown 模板。
2. **找缓存失效判断**：`_compute_module_hash` 计算模块级哈希（文件列表 + 符号指纹）；`cache.db_hash` 计算 DB 级哈希用于 project_map 全局失效。
3. **找目录过滤规则**：`_resolve_roots_and_aux` 控制哪些目录进入 L1（核心模块）vs L2（辅助目录），是模块划分范围的核心决策点。
4. **找 Agent 响应解析规则**：`submit_project_map` 内部调用 `_parse_modules_text`，期望格式为 `模块名|一句话职责|目录1,目录2`。
5. **找 docstring 提取启用条件**：`_docstrings_enabled()` 函数控制是否启用文件/docstring 提取（依赖外部包 `docstring_parser` / `tree_sitter` 等），不可用时自动跳过。

## 跨模块依赖

### summarizer → data（称为下游，实际为"被调用方"）

| summarizer 函数 | 调用的 data 层函数 |
|-----------------|-------------------|
| `get_project_map_prompt` | `list_modules`, `module_dependencies`, `directory_dependencies`, `directory_symbols`, `iter_files`, `compute_centrality`, `topological_layers`, `find_cycles`, `external_dependencies_by_dir`, `extract_file_docstring`, `ref_docs_prompt_section` |
| `submit_project_map` | `list_modules`, `module_dependencies`, `directory_dependencies`, `directory_symbols`, `iter_files` |
| `get_module_prompt` | `list_modules`, `module_dependencies`, `directory_dependencies`, `iter_nodes`, `cross_dir_public_api`, `external_dependencies_by_dir`, `extract_file_docstring`, `extract_symbol_docstrings`, `ref_docs_prompt_section` |
| `save_module_summary` | 间接通过 `_compute_module_hash` 使用 `iter_nodes` |
| `_compute_module_hash` | `db.iter_nodes(kinds=("function","class","method"))` |

### summarizer → cache（称为下游，实际为"被调用方"）

| summarizer 函数 | 调用的 cache 层函数 |
|-----------------|-------------------|
| `get_module_prompt` | `read_modules_index` |
| `submit_project_map` | `db_hash`, `write_modules_index`, `write_project_map` |
| `save_module_summary` | `db_hash`, `read_modules_index`, `write_module` |

## 典型调用链

### 1. project_map 生成流程

```
tools.project_map() → cache.is_cache_valid() → 未命中
  → 返回指令给 Agent → Agent 调用
  → tools.get_project_map_prompt_tool() → summarizer.get_project_map_prompt()
    → CodeGraphDB → list_modules / module_dependencies / directory_symbols / ...
    → _resolve_roots_and_aux → 过滤 roots
    → compute_centrality / topological_layers / find_cycles
    → _build_project_map_prompt → 返回 Markdown prompt
  → Agent 生成模块划分文本 → Agent 调用
  → tools.submit_project_map_tool() → summarizer.submit_project_map()
    → CodeGraphDB → 重新提取目录/文件数据
    → _parse_modules_text → 解析 pipe-delimited 文本
    → _migrate_renamed_module_caches
    → cache.write_modules_index + cache.write_project_map
    → _render_project_map_markdown → 返回 project_map.md
  → Agent 重新调用 tools.project_map() → 缓存命中 → 返回 project_map.md
```

### 2. module_summary 生成流程

```
tools.explore_module("数据层") → cache.read_modules_index → 有 index
  → cache.read_module → 缓存未命中
  → 返回指令给 Agent → Agent 调用
  → tools.get_module_prompt_tool("数据层") → summarizer.get_module_prompt("数据层")
    → cache.read_modules_index → 找到模块 entry
    → CodeGraphDB → iter_nodes / cross_dir_public_api / external_dependencies_by_dir
    → extract_file_docstring / extract_symbol_docstrings
    → _build_module_prompt → 返回 Markdown prompt
  → Agent 生成模块摘要 Markdown → Agent 调用
  → tools.save_module_summary_tool("数据层", summary) → summarizer.save_module_summary()
    → cache.read_modules_index → 找到 entry
    → _compute_module_hash → SHA1
    → cache.write_module → 写入摘要 + hash
  → Agent 重新调用 tools.explore_module("数据层") → 缓存命中 → 返回摘要
```

## 实现约束

### 必须实现的函数

| 函数 | 原因 |
|------|------|
| `get_project_map_prompt` | tools 层 `get_project_map_prompt_tool` 的唯一下游 |
| `get_module_prompt` | tools 层 `get_module_prompt_tool` 的唯一下游 |
| `submit_project_map` | tools 层 `submit_project_map_tool` 的唯一下游 |
| `save_module_summary` | tools 层 `save_module_summary_tool` 的唯一下游 |

### 内部必需函数

| 函数 | 原因 |
|------|------|
| `_compute_module_hash` | 被 `save_module_summary` 和 `explore_module` 用于缓存有效性校验 |
| `_resolve_roots_and_aux` | 决定哪些目录参与 L1 模块划分，直接影响 prompt 内容范围 |
| `_build_project_map_prompt` | 组装 project_map prompt，定义 Agent 看到的全部上下文数据 |
| `_build_module_prompt` | 组装 module prompt，定义 Agent 看到的全部上下文数据 |
| `_filter_dir_deps` | 过滤仅保留 roots 内的依赖关系 |
| `_is_under_roots` | 目录归属判断基础函数 |

### 关键设计决策

- **prompt 为完整 Markdown 字符串**：不依赖外部模板引擎，所有格式在 f-string 中硬编码。
- **两次 DB 打开**：`submit_project_map` 独立打开 DB 提取数据（非复用 `get_project_map_prompt` 结果），确保解析时数据与 Agent 看到的一致。
- **模块重命名迁移**：`_migrate_renamed_module_caches` 在 `submit_project_map` 中自动处理，保留旧模块缓存到新名称。
- **docstring 提取可选**：`_docstrings_enabled()` 检测依赖可用性，不可用时静默跳过，不阻塞 prompt 生成。
