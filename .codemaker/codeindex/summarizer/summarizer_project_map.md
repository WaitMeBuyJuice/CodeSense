---
entity_names:
  constants:
    - name: _CODESENSE_DIR_NAME
      value: ".codesense"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _EXTERNAL_PREFIX
      value: "external::"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _DESC_MAX_LEN
      value: "60"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _NAME_MIN_LEN
      value: "2"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _NAME_MAX_LEN
      value: "20"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _FUZZY_CUTOFF
      value: "0.85"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _FALLBACK_MODULE_NAME
      value: "其他"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _FALLBACK_MODULE_DESC
      value: "未归类目录"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _INCLUDE_DIRS_ENV
      value: "CODESENSE_INCLUDE_DIRS"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _DEFAULT_INCLUDE_ROOTS
      value: "('src',)"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _HAS_EXTENSION_RE
      value: "re.compile(r'\\.[a-zA-Z0-9]+$')"
      source: src/codesense_v1/summarizer/summarizer.py
retrieval_hints:
  - "正向疑问句：project_map 的模块划分是怎么解析的？竖线文本「模块名|职责|目录」由 _parse_modules_text 处理"
  - "正向疑问句：02_structure 和 04_dependencies 段是纯程序渲染还是 LLM 生成？render_structure_segment / render_dependencies_segment 纯程序，无 Agent"
  - "正向疑问句：模块重命名后旧 .md 缓存怎么复用？_migrate_renamed_module_caches 按 _compute_module_hash 匹配 hash 一致的旧 key 迁移"
  - "⚠️ 反向排除：若找缓存文件读写细节（safe_key/db_hash/write_segment 实现），不在这里，在 cache 模块"
  - "⚠️ 反向排除：若找 LLM 调用代码，不在这里，summarizer 只产出 prompt 文本，LLM 调用由 tools 层 Agent 完成"
  - "架构归属句：新增 segment 渲染/解析逻辑必须放 summarizer.py，不可在 tools 层实现"
  - "架构归属句：01_identity/03_modules 段需 Agent 生成（get_identity_segment_prompt/get_architecture_segment_prompt 产提示词），02/04 段纯程序渲染"
  - "本模块也叫 summarizer 协调层（architectural_role=摘要协调层）"
architectural_role: "摘要协调层"
---

## 对外接口

| 函数 | 用途 | 被哪个 tool 调用 |
|------|------|-----------------|
| `get_project_map_prompt(project_root)` | 产出模块划分提示词文本（含目录符号/依赖/拓扑层/中心度/环/docstring），返回 str 交外部 Agent | `get_modules_segment_prompt_tool` |
| `submit_project_map(project_root, response)` | 解析竖线分隔文本 `模块名\|职责\|目录`，展开文件，迁移重命名缓存，写 modules_index + 03/04 段 + render_project_map | `submit_project_map_tool` |
| `render_structure_segment(project_root, top_dirs, tree_root, max_depth=3)` | 纯程序渲染 02_structure.md（深度 3 目录树 + 辅助目录标注） | `project_map` 工具 |
| `render_dependencies_segment(modules, edges, cycles, centrality=None)` | 纯程序渲染 04_dependencies.md（依赖图 + 上下游详表 + 循环警告） | `submit_project_map` 内部调用 |
| `get_identity_segment_prompt(sources, tech_hints)` | 产出 01_identity.md 提示词（仓库定位 + 技术栈表格） | `get_identity_segment_prompt_tool` |
| `get_architecture_segment_prompt(layers, modules, dir_deps, dir_syms)` | 产出 03_architecture.md 提示词（系统分层图 + 层次职责 + 模块列表） | tools 层（架构段生成） |
| `save_project_map_segment(project_root, segment_id, content, source_hash)` | 通用 segment 落盘（委托 cache.write_segment） | tools 层 segment 保存 |

## 跨模块依赖

### 外部依赖（summarizer → 下游）

| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|----------|----------|-----------|
| data | DB 查询、目录依赖/符号聚合、拓扑层/中心度/环、ref_docs 段、hash 计算 | `CodeGraphDB` / `list_modules` / `module_dependencies` / `directory_dependencies` / `directory_symbols` / `compute_centrality` / `topological_layers` / `find_cycles` / `external_dependencies_by_dir` / `ref_docs_prompt_section` / `compute_architecture_hash` / `compute_dependencies_hash` / `classify_top_dirs` / `auxiliary_category` / `DirectoryNode` / `TopLevelDir` | extracted |
| data.docstrings | 01/03 段提示词与 project_map prompt 注入文件 docstring | `extract_file_docstring` / `is_enabled` | extracted |
| cache | 写 modules_index、segment、render_project_map、读 module_hashes 迁移 | `write_modules_index` / `write_segment` / `is_segment_valid` / `render_project_map` / `read_module_hashes` / `write_module_hash` / `safe_key` / `db_hash` | extracted |
| errors | 解析失败/模块不存在抛异常 | `InvalidArgumentError` | extracted |

### 反向调用方（tools → summarizer）

| 调用方 | 调用场景 | 关键符号 |
|--------|----------|----------|
| `submit_project_map_tool` | Agent 回传模块划分文本 → 调 `submit_project_map` 解析落盘 | `submit_project_map` |
| `get_modules_segment_prompt_tool` | Agent 请求模块划分提示词 → 调 `get_project_map_prompt` | `get_project_map_prompt` |
| `get_identity_segment_prompt_tool` | Agent 请求 01 段提示词 → 调 `get_identity_segment_prompt` | `get_identity_segment_prompt` |
| `project_map` 工具 | 渲染 02 段 → 调 `render_structure_segment` | `render_structure_segment` |

## 典型调用链

1. `submit_project_map` ← 本模块入口 → `_parse_modules_text`（fuzzy 校正/去重/冲突丢弃）→ `_expand_module_files`（父子目录排除）→ `_migrate_renamed_module_caches` ← 跨模块:cache（读旧 hash）→ `cache.write_modules_index` ← 跨模块:cache → `_render_basic_architecture_segment`（03 段）→ `render_dependencies_segment`（04 段）→ `cache.render_project_map` ← 跨模块:cache
2. `get_project_map_prompt` ← 本模块入口 → ← 跨模块:data（list_modules/module_dependencies/directory_dependencies/directory_symbols/compute_centrality/topological_layers/find_cycles/external_dependencies_by_dir）→ `_build_project_map_prompt`（拼提示词文本）
3. `render_structure_segment` ← 本模块入口（纯程序，无跨模块 data/cache 调用，仅用入参 top_dirs/tree_root）

## 实现约束清单

### 必须定义的常量/阈值

| 常量 | 值 | 用途 |
|------|----|----|
| `_CODESENSE_DIR_NAME` | `".codesense"` | 缓存目录名 |
| `_EXTERNAL_PREFIX` | `"external::"` | 外部依赖前缀，渲染时过滤 |
| `_DESC_MAX_LEN` | `60` | 模块职责描述截断长度（修 LLM「add、add、list」幻觉） |
| `_NAME_MIN_LEN` | `2` | 模块名最小长度 |
| `_NAME_MAX_LEN` | `20` | 模块名最大长度 |
| `_FUZZY_CUTOFF` | `0.85` | 目录 fuzzy 匹配阈值（difflib.get_close_matches） |
| `_FALLBACK_MODULE_NAME` | `"其他"` | 兜底模块名 |
| `_FALLBACK_MODULE_DESC` | `"未归类目录"` | 兜底模块描述 |
| `_INCLUDE_DIRS_ENV` | `"CODESENSE_INCLUDE_DIRS"` | 用户配置 include roots 环境变量 |
| `_DEFAULT_INCLUDE_ROOTS` | `("src",)` | 默认 include roots |
| `_HAS_EXTENSION_RE` | `re.compile(r"\.[a-zA-Z0-9]+$")` | 检测根级文件名误判为目录 |

### 必须实现的函数

- `get_project_map_prompt(project_root) -> str`（async）
- `submit_project_map(project_root, response) -> str`（async）
- `_parse_modules_text(response, valid_dirs=None, warnings=None) -> list[dict]`
- `_expand_module_files(modules_json, all_file_paths) -> list[dict]`
- `_migrate_renamed_module_caches(codesense_dir, new_modules, db) -> None`
- `_build_project_map_prompt(...) -> str`
- `_render_basic_architecture_segment(modules, layers) -> str`（03 段基础渲染）
- `_render_project_map_markdown(modules, dir_deps, aux_dirs=None) -> str`
- `render_structure_segment(project_root, top_dirs, tree_root, max_depth=3) -> str`
- `render_dependencies_segment(modules, edges, cycles, centrality=None) -> str`
- `get_identity_segment_prompt(sources, tech_hints) -> str`
- `get_architecture_segment_prompt(layers, modules, dir_deps, dir_syms) -> str`
- `save_project_map_segment(project_root, segment_id, content, source_hash) -> None`
- 辅助：`_resolve_roots_and_aux` / `_filter_dir_deps` / `_leaf_dirs_from_files` / `_top_level_files_from_paths` / `_normalize_dir` / `_dedup_description` / `_is_under_roots` / `_classify_top_dirs`

### 设计决策

| 决策 | 说明 |
|------|------|
| 竖线文本 vs JSON 选型 | 选竖线分隔文本 `模块名\|职责\|目录`。理由：JSON 在大项目（~200 文件）下 LLM 频繁遗漏逗号致整体解析失败；竖线文本单行独立，单行坏了跳过不影响其他行，失败率大幅降低 |
| 父子目录排除规则 | `_expand_module_files` 中：模块 A 声明父目录 `src/core`，模块 B 声明子目录 `src/core/utils` → A 的 files 排除 B 子目录下文件，避免模块间文件重叠 |
| 单文件模块处理 | `_expand_module_files` 用 `_HAS_EXTENSION_RE` 判定条目是文件路径（有扩展名）还是目录；文件路径直接入 files 不展开目录；stored_dirs 为空（files 字段权威） |
| 模块重命名 hash 迁移 | `_migrate_renamed_module_caches`：对新模块算 `_compute_module_hash`，与旧 modules（不在新 index）的 hash 比对，1-to-1 匹配则 rename 旧 .md 到新 key + 更新 .hashes.json；hash 冲突（两新模块同 hash）标记哨兵值跳过；旧 key 留给 `_prune_stale_modules` 清理 |
| 目录 fuzzy 校正 | `_normalize_dir` 用 `difflib.get_close_matches(cutoff=_FUZZY_CUTOFF)` 校正 LLM 笔误目录名，命中则改写并记 warning |
| 目录冲突丢弃 | `_parse_modules_text` 用 `seen_dirs` 跟踪已占用目录，后到模块的重复目录丢弃并记 warning；无有效目录的整模块跳过 |
| 03/04 段生成时机 | `submit_project_map` 内：03 段用 `_render_basic_architecture_segment`（基础版，Agent 可后续增强）+ 04 段用 `render_dependencies_segment`（始终重生成，因模块名映射此时可用） |
| 02/04 段纯程序 | `render_structure_segment` / `render_dependencies_segment` 无 Agent 参与，纯数据渲染 |
| 01/03 段需 Agent | `get_identity_segment_prompt` / `get_architecture_segment_prompt` 只产提示词文本，实际内容由外部 Agent 生成后经 `save_project_map_segment` 落盘 |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week3/design/summarizer.md`、`doc/Week3/design/overview.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

- **Week3 设计**（已过时，以代码为准）：原设计 summarizer 直接调 `llm.call_llm`，单步 `project_map_summary` 生成 Markdown。**实际代码已演进**：summarizer 不调 LLM，改为两步（`get_project_map_prompt` 产提示词 + `submit_project_map` 解析），LLM 调用移至 tools 层 Agent。
- **Week5 前置改动**（与代码一致）：
  - `project_map_summary` 两步重构：第一步 LLM 输出竖线文本 → 解析为结构化模块列表；第二步代码模板渲染 Markdown（不再调 LLM）。
  - 竖线文本选型：JSON 在大项目下 LLM 频繁遗漏逗号，改竖线文本后单行独立、失败率降。
  - `_build_module_prompt` 补真实符号：旧版只传文件列表致 LLM 幻觉接口，新版先查 `db.iter_nodes()` 取实际符号拼入 prompt。
  - `safe_key` 变更：`module_key(path)` → `safe_key(name)`（sha1[:12]），文件名不可读但 modules_index 反查。
  - 缓存结构：新增 `modules_index.json`，`write_modules_index` 同步清空 `modules/` 子缓存防孤儿。
- **Week3 overview 架构定位**：summarizer 属 L6 协调层，独立于 tools/resources 便于复用与单测，LLM prompt 迭代不影响 Tool/Resource 层。
