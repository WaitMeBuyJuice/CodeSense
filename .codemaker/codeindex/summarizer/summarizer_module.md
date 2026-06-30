---
entity_names:
  constants:
    - name: _CACHE_AUTO_EXPIRE_ENV
      value: "CODESENSE_CACHE_AUTO_EXPIRE"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _EXT_TO_LANG
      value: "{'.py':'python','.ts':'typescript','.tsx':'typescriptreact','.js':'javascript','.jsx':'javascriptreact','.go':'go','.rs':'rust','.erl':'erlang','.hrl':'erlang','.rb':'ruby','.sh':'shell','.bash':'bash'}"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _GENERIC_SYMBOL_NAMES
      value: "frozenset({'run','execute','process','handle','do','call','invoke','start','stop','init','setup','teardown','main','update','create','delete','get','set','load','save','build','parse','validate','check','test'})"
      source: src/codesense_v1/summarizer/summarizer.py
    - name: _ENTRY_LAYER_HINTS
      value: "frozenset({'tool','tools','server','cli','cmd','api','main','bin','app','handler','endpoint'})"
      source: src/codesense_v1/summarizer/summarizer.py
retrieval_hints:
  - "正向疑问句：单模块摘要提示词怎么构建？get_module_prompt 查 modules_index → DB 取符号/公开 API/外部依赖/docstrings → _build_module_prompt"
  - "正向疑问句：模块摘要怎么落盘和判失效？save_module_summary 写 modules/<safe_key>.md + per-module hash（_compute_module_hash）"
  - "正向疑问句：_compute_module_hash 的输入是什么？sorted 文件列表 + sorted 符号指纹（file:name:kind:sig）的 sha1"
  - "正向疑问句：通用符号名（run/execute 等）无 docstring 时 prompt 怎么提示？_is_generic_name 命中则加「⚠️ 无 docstring 且名称通用，建议 read_file 确认」"
  - "⚠️ 反向排除：若找缓存文件读写细节（write_module/safe_key 实现），不在这里，在 cache 模块"
  - "⚠️ 反向排除：若找 LLM 调用代码，不在这里，summarizer 只产出 prompt 文本，LLM 调用由 tools 层 Agent 完成"
  - "架构归属句：模块摘要的 prompt 构建/解析/hash 计算逻辑必须放 summarizer.py，不可在 tools 层实现"
  - "架构归属句：docstring 注入由 summarizer 协调（_docstrings_enabled 判定 + extract_file_docstring/extract_symbol_docstrings 提取），data.docstrings 只提供提取原语"
  - "本模块也叫 summarizer 协调层（architectural_role=摘要协调层）"
architectural_role: "摘要协调层"
---

## 对外接口

| 函数 | 用途 | 被哪个 tool 调用 |
|------|------|-----------------|
| `get_module_prompt(project_root, module_name)` | 产出单模块摘要提示词文本（查 modules_index → DB 取符号/公开 API/外部依赖/docstrings → `_build_module_prompt`），返回 str 交外部 Agent | `get_module_prompt_tool` |
| `save_module_summary(project_root, module_name, summary)` | 把 Agent 生成的摘要写入 `modules/<safe_key>.md` + 更新 per-module hash（`_compute_module_hash`） | `save_module_summary_tool` |
| `is_auto_expire_enabled()` | 读 `CODESENSE_CACHE_AUTO_EXPIRE` env（默认 true），控制缓存自动失效 | tools/cache 层判定 |

## 跨模块依赖

### 外部依赖（summarizer → 下游）

| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|----------|----------|-----------|
| data | DB 查询、目录依赖聚合、跨目录公开 API、外部依赖、符号迭代 | `CodeGraphDB` / `list_modules` / `module_dependencies` / `directory_dependencies` / `cross_dir_public_api` / `external_dependencies_by_dir` / `db.iter_nodes` | extracted |
| data.docstrings | 文件/符号 docstring 提取（注入 prompt） | `extract_file_docstring` / `extract_symbol_docstrings` / `is_enabled` | extracted |
| data.ref_docs | 参考文档段注入 prompt | `ref_docs_prompt_section` | extracted |
| cache | 读 modules_index 查模块、写 module 摘要 + hash、safe_key、db_hash | `read_modules_index` / `write_module` / `safe_key` / `db_hash` | extracted |
| errors | modules_index 缺失/模块名不存在抛异常 | `InvalidArgumentError` | extracted |

### 反向调用方（tools → summarizer）

| 调用方 | 调用场景 | 关键符号 |
|--------|----------|----------|
| `get_module_prompt_tool` | Agent 请求单模块提示词 → 调 `get_module_prompt` | `get_module_prompt` |
| `save_module_summary_tool` | Agent 回传模块摘要 → 调 `save_module_summary` 落盘 | `save_module_summary` |

## 典型调用链

1. `get_module_prompt` ← 本模块入口 → `cache.read_modules_index` ← 跨模块:cache（查模块名→文件映射，trim+大小写不敏感）→ ← 跨模块:data（list_modules/module_dependencies/directory_dependencies/db.iter_nodes/cross_dir_public_api/external_dependencies_by_dir）→ ← 跨模块:data.docstrings（extract_file_docstring/extract_symbol_docstrings，_docstrings_enabled 判定）→ `_build_module_prompt`（拼提示词文本）
2. `save_module_summary` ← 本模块入口 → `cache.read_modules_index` ← 跨模块:cache（校验模块存在）→ `_compute_module_hash`（算 per-module hash）→ `cache.write_module` ← 跨模块:cache（写 modules/<safe_key>.md + hash）

## 实现约束清单

### 必须定义的常量/阈值

| 常量 | 值 | 用途 |
|------|----|----|
| `_CACHE_AUTO_EXPIRE_ENV` | `"CODESENSE_CACHE_AUTO_EXPIRE"` | 缓存自动失效开关 env（默认 true，设 false 则始终用旧缓存） |
| `_EXT_TO_LANG` | dict（.py→python / .ts→typescript / .tsx→typescriptreact / .js→javascript / .jsx→javascriptreact / .go→go / .rs→rust / .erl/.hrl→erlang / .rb→ruby / .sh→shell / .bash→bash） | 文件扩展名→语言映射，docstring 提取按语言选解析器 |
| `_GENERIC_SYMBOL_NAMES` | frozenset（run/execute/process/handle/do/call/invoke/start/stop/init/setup/teardown/main/update/create/delete/get/set/load/save/build/parse/validate/check/test） | 通用符号名集合，无 docstring 时 prompt 加 ⚠️ 提示 |
| `_ENTRY_LAYER_HINTS` | frozenset（tool/tools/server/cli/cmd/api/main/bin/app/handler/endpoint） | 入口层目录名片段，无公开 API 时提示「对外接口由外部协议定义」 |

### 必须实现的函数

- `get_module_prompt(project_root, module_name) -> str`（async）
- `save_module_summary(project_root, module_name, summary) -> None`
- `_compute_module_hash(entry, db) -> str`
- `_build_module_prompt(entry, dir_deps, file_symbols, *, public_symbols=None, external_deps=None, file_docstrings=None, symbol_docstrings=None, ref_docs_section="") -> str`
- `is_auto_expire_enabled() -> bool`（`__init__.py` 导出为 `is_auto_expire_enabled`，源码私有名 `_is_auto_expire_enabled`）
- 辅助：`_lang_from_path` / `_is_generic_name` / `_looks_like_entry_layer`

### 设计决策

| 决策 | 说明 |
|------|------|
| `_compute_module_hash` 输入 | sorted 文件列表 + sorted 符号指纹（`file:name:kind:sig`）拼接后 sha1。文件增删或任一符号签名变化 → hash 变 → 触发重生成。**不含 docstring 内容**（docstring 变不改 hash，避免频繁失效） |
| 模块名查找规则 | `get_module_prompt` / `save_module_summary` 在 modules_index 中按 `name.strip().lower()` 比对，大小写/空格不敏感；找不到则抛 `InvalidArgumentError` 并列出可用模块名 |
| modules_index 缺失处理 | index 为 None → 抛 `InvalidArgumentError("参数错误：尚未生成模块划分，请先调用 project_map 生成模块划分")` |
| docstring 注入策略 | `_docstrings_enabled()` 为真时：每个文件取 `extract_file_docstring`（文件级）+ `extract_symbol_docstrings`（符号级，按 node 列表）；无符号文件也补文件 docstring。注入 prompt 的 `[文件注释]` / `[docstring]` 标注 |
| 通用符号名警示 | `_is_generic_name` 判定（base 在 `_GENERIC_SYMBOL_NAMES` 或以 `on_`/`do_`/`handle_` 开头）且无 docstring → prompt 加「⚠️ 无 docstring 且名称通用，建议 read_file 确认实现语义」 |
| 入口层公开 API 兜底 | `public_symbols` 为空时：`_looks_like_entry_layer` 命中（目录名含 `_ENTRY_LAYER_HINTS` 片段）→ 提示「对外接口由外部协议（MCP/CLI/HTTP/RPC）定义，不在图推导范围」；否则提示「纯内部实现」 |
| 数据可信度声明 | `_build_module_prompt` 末尾固定加 `_DATA_TRUST_NOTICE`：docstring 反映写作时设计意图可能偏差、签名不显副作用、图推导不覆盖外部调用方、⚠️ 符号建议 read_file 核实 |
| `_build_module_prompt` 补真实符号 | Week5 改动：旧版只传文件列表致 LLM 幻觉接口；新版先查 `db.iter_nodes(kinds=("function","class","method"))` 取该模块实际符号（含签名）拼入 prompt，并加「仅列出下方实际存在的符号，不要编造」语义 |
| hash 不含 docstring | `_compute_module_hash` 只算文件+符号指纹，docstring 变更不触发失效（设计取舍：docstring 频繁改但语义不变，避免过度失效） |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week3/design/summarizer.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

- **Week3 设计**（已过时，以代码为准）：原设计 `module_summary` 直接调 `llm.call_llm`，入参为 `module_path`（目录路径），校验 `__init__.py` 存在。**实际代码已演进**：入参改 `module_name`（LLM 给的模块名），校验改为查 modules_index，LLM 调用移至 tools 层 Agent。
- **Week5 前置改动**（与代码一致）：
  - `explore_module` 入参 `module_path` → `module_name`：校验从「目录存在 + `__init__.py`」改为「modules_index 中按名查找（trim + 大小写不敏感）」，找不到列出可用模块名。
  - `_build_module_prompt` 补真实符号：旧版只传文件列表，LLM 猜测接口（幻觉）；新版先查 `db.iter_nodes()` 取该模块实际符号（含签名）拼入 prompt，并加提示「仅列出下方实际存在的符号，不要编造」。
  - `safe_key` 变更：`module_key(path)` → `safe_key(name)`（sha1[:12]），文件名不可读但 modules_index 反查。
- **Week3 设计数据流**（已演进）：原 `module_summary` 流程含 `cache.is_cache_valid` → `cache.read_module` 命中返回 → 否则 `llm.call_llm` → `cache.write_module`。**实际代码**：缓存命中判定与 LLM 调用移至 tools 层，summarizer 只提供 `get_module_prompt`（产提示词）+ `save_module_summary`（落盘）。
