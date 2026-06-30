---
entity_names:
  constants:
    - name: _README_CANDIDATES
      value: "(\"README.md\",\"README.rst\",\"README.txt\",\"README\",\"readme.md\",\"readme.rst\",\"readme.txt\",\"Readme.md\",\"Readme.rst\")"
      source: src/codesense_v1/data/project_info.py
    - name: _CONFIG_CANDIDATES
      value: "((\"pyproject\",\"pyproject.toml\"),(\"package_json\",\"package.json\"),(\"cargo_toml\",\"Cargo.toml\"),(\"go_mod\",\"go.mod\"),(\"composer_json\",\"composer.json\"),(\"gemfile\",\"Gemfile\"))"
      source: src/codesense_v1/data/project_info.py
    - name: _DOCSTRING_ENV
      value: "\"CODESENSE_EXTRACT_DOCSTRINGS\""
      source: src/codesense_v1/data/docstrings.py
    - name: _MAX_LEN
      value: "200"
      source: src/codesense_v1/data/docstrings.py
    - name: _LOOKAHEAD
      value: "10"
      source: src/codesense_v1/data/docstrings.py
    - name: _LOOKBEHIND
      value: "20"
      source: src/codesense_v1/data/docstrings.py
    - name: _FILE_SCAN
      value: "30"
      source: src/codesense_v1/data/docstrings.py
    - name: _TRIPLE
      value: "(\"\\\"\\\"\\\"\", \"'''\")"
      source: src/codesense_v1/data/docstrings.py
    - name: _PYTHON_SKIP_RE
      value: "re.compile(r\"^(\\s*#.*|\\s*)$\")"
      source: src/codesense_v1/data/docstrings.py
    - name: _REF_DOCS_DIR_ENV
      value: "\"CODESENSE_REF_DOCS_DIR\""
      source: src/codesense_v1/data/ref_docs.py
    - name: _REF_DOCS_RECURSIVE_ENV
      value: "\"CODESENSE_REF_DOCS_RECURSIVE\""
      source: src/codesense_v1/data/ref_docs.py
    - name: _TEXT_EXTENSIONS
      value: "frozenset({\".md\",\".txt\",\".rst\",\".adoc\",\".markdown\"})"
      source: src/codesense_v1/data/ref_docs.py
    - name: _BINARY_EXTENSIONS
      value: "frozenset({\".docx\",\".pdf\"})"
      source: src/codesense_v1/data/ref_docs.py
    - name: _ALL_EXTENSIONS
      value: "_TEXT_EXTENSIONS | _BINARY_EXTENSIONS"
      source: src/codesense_v1/data/ref_docs.py
retrieval_hints:
  - "正向疑问句：怎么收集项目身份信息（README/配置文件/包文档字符串）？"
  - "正向疑问句：怎么从 pyproject.toml/package.json 提取技术栈提示？"
  - "正向疑问句：怎么提取多语言源文件的文档字符串？支持哪些语言？"
  - "正向疑问句：怎么给 LLM prompt 注入项目参考文档段落？"
  - "⚠️ 反向排除：若找架构拓扑分层或内容指纹 hash，不在本子文档，在 data_analysis.md"
  - "⚠️ 反向排除：若找文件级依赖边或目录聚合，不在本子文档，在 data_query.md"
  - "架构归属句：docstrings.py 是 data 层唯一做源文件 I/O 的模块，其余 data 子文件只读 SQLite；project_info/ref_docs 也读源文件与配置"
  - "架构归属句：文档字符串提取受环境变量 CODESENSE_EXTRACT_DOCSTRINGS 控制，设 false 全局关闭；参考文档受 CODESENSE_REF_DOCS_DIR 控制"
  - "本模块也叫 prompt 上下文构建数据源"
architectural_role: "CodeGraph 数据查询层"
---

# data_context — 项目身份信息 + 文档字符串 + 参考文档

覆盖：`project_info.py` / `docstrings.py` / `ref_docs.py`。三者均为 prompt 构建提供上下文数据：身份信息供 01_identity segment，文档字符串供 module segment，参考文档供所有 segment。

## 对外接口

| 函数/类 | 用途 | 所在文件 |
|---|---|---|
| `IdentitySource` | frozen dataclass：`kind`/`path`/`content`（kind=readme/pyproject/package_json/cargo_toml/go_mod/docstring） | project_info.py |
| `collect_identity_sources(project_root, db)` | 按优先级收集全部身份源（README→配置→包文档字符串） | project_info.py |
| `read_readme(project_root)` | 找第一个可用 README → `IdentitySource` 或 None | project_info.py |
| `extract_tech_stack_hint(sources)` | 从配置源提取结构化技术栈 dict（language/python_requires/build_tool/linter/test_framework 等） | project_info.py |
| `extract_file_docstring(file_path, language)` | 文件级文档字符串 → str 或 None | docstrings.py |
| `extract_symbol_docstrings(file_path, language, nodes)` | `{node.id: docstring}`（单文件只读一次） | docstrings.py |
| `is_enabled`（导出为 `docstrings_enabled`） | 读 `CODESENSE_EXTRACT_DOCSTRINGS` env，非 "false" 即启用 | docstrings.py |
| `ref_docs_prompt_section(project_root)` | 参考文档 prompt 段落（无文档返回 ""） | ref_docs.py |
| `discover_ref_docs(project_root)` | 参考文档路径列表（`list[Path]`） | ref_docs.py |

## 跨模块依赖

外部依赖（data → 其他模块）：

| 依赖 | 用途 |
|---|---|
| `codesense_v1.data.db` | project_info 的 `read_package_docstrings`/`collect_identity_sources` 需 `CodeGraphDB` 遍历文件；docstrings 依赖 `NodeRow` |
| `codesense_v1.data.docstrings` | project_info 的 `read_package_docstrings` 调 `extract_file_docstring` |
| 标准库 `json`/`dataclasses`/`pathlib`/`os`/`re` | 配置解析、文件读取、env 控制 |

反向调用方：

| 调用方 | 调用的 data 函数 |
|---|---|
| `tools/project_map.py` | `collect_identity_sources` |
| `tools/save_project_map_segment.py` | `collect_identity_sources` |
| `tools/get_identity_segment_prompt.py` | `collect_identity_sources`/`extract_tech_stack_hint` |
| `summarizer/summarizer.py` | `IdentitySource`/`extract_file_docstring`/`extract_symbol_docstrings`/`ref_docs_prompt_section` |

## 典型调用链

1. `get_identity_segment_prompt tool → collect_identity_sources(project_root, db) → extract_tech_stack_hint(sources)`（收集身份源 + 提取技术栈，拼入 01_identity LLM prompt）。
2. `summarizer → extract_file_docstring(pr/fp, lang) + extract_symbol_docstrings(pr/fp, lang, nodes)`（module segment 渲染时取文件级与符号级文档字符串，喂给 LLM 减少幻觉）。
3. `summarizer → ref_docs_prompt_section(project_root) → discover_ref_docs(project_root)`（所有 segment prompt 末尾注入参考文档列表，指示 Agent 用 read_file 自行提炼）。

## 实现约束清单

| 类型 | 约束 |
|---|---|
| 设计决策 | `docstrings.py` 是 **data 层唯一做源文件 I/O 的模块**（读源码文件）；`project_info.py`/`ref_docs.py` 也读源文件与配置文件，但其余 data 子文件严格只读 SQLite。 |
| 设计决策 | 文档字符串提取 best-effort：所有公开函数遇不支持语言/缺文件/编码错/无文档字符串均返回 `None`/空 dict，调用方须优雅降级。 |
| 设计决策 | `is_enabled` 读 `CODESENSE_EXTRACT_DOCSTRINGS` env，默认 "true"，设 "false" 全局关闭提取（适用于源文件不可访问场景）。 |
| 设计决策 | 支持语言与约定：Python 三引号（声明后函数体内）/ TS-JS JSDoc `/** */` 或 `//` 行注释（声明前）/ Go `//` 行注释（声明前）/ Rust `///`（item）或 `//!`（module）/ Erlang `%%` / Ruby-Shell `#`。 |
| 设计决策 | `extract_symbol_docstrings` 单文件只读一次，多节点复用 lines；Python 文档字符串在 `def`/`class` 行后 `_LOOKAHEAD=10` 行内找三引号，注释型语言在 `start_line` 前 `_LOOKBEHIND=20` 行找注释块。 |
| 设计决策 | `collect_identity_sources` 优先级：README（最高，人写描述）→ 配置文件（pyproject/package.json/Cargo.toml/go.mod/composer.json/Gemfile）→ 顶层包文档字符串（兜底）。 |
| 设计决策 | `read_package_docstrings` 只取顶层或一层深的入口文件（`__init__.py`/`main.py`/`__main__.py`/`index.ts`/`index.js`/`main.go`，depth≤2）。 |
| 设计决策 | `extract_tech_stack_hint` best-effort：pyproject 解析 `requires-python`/`build-backend`/dev 依赖（识别 mypy/ruff/pytest）；package.json 解析 dependencies+devDependencies 识别 React/Vue/TypeScript；Cargo.toml→Rust；go.mod→Go。缺失键直接缺省。 |
| 设计决策 | `ref_docs_prompt_section` 无文档返回 `""`（调用方用 truthiness 跳过）；段落指示 Agent 用 `read_file` 读文档自行提炼，不内嵌原文；二进制（.docx/.pdf）只列路径加格式提示。 |
| 必须实现的函数 | `collect_identity_sources`/`extract_tech_stack_hint`/`read_readme`/`extract_file_docstring`/`extract_symbol_docstrings`/`is_enabled`/`ref_docs_prompt_section`/`discover_ref_docs`。 |
| 阈值/默认值 | docstrings：`_MAX_LEN=200`（每文档字符串首行最大字符）、`_LOOKAHEAD=10`、`_LOOKBEHIND=20`、`_FILE_SCAN=30`（文件级文档扫描最大行）。 |
| 阈值/默认值 | ref_docs：默认非递归扫描，`CODESENSE_REF_DOCS_RECURSIVE=true` 启用递归；只收集常规文件（跳 symlink/目录）。 |
| env 变量 | `CODESENSE_EXTRACT_DOCSTRINGS`（docstrings 开关）、`CODESENSE_REF_DOCS_DIR`（参考文档目录，绝对或项目相对路径）、`CODESENSE_REF_DOCS_RECURSIVE`（递归开关）。 |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/data.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

- `doc/Week2/design/data.md`：未覆盖 project_info/docstrings/ref_docs（Week2 设计仅含 db/files/modules/aggregate）。但确立的"data 层只读 SQLite 不写入、不依赖 registry/tools/server"原则在本子文档有例外：docstrings/project_info/ref_docs 为 prompt 上下文需读源文件与配置，属 data 层内合理的文件 I/O 旁路。
- `doc/Week5/week5_handoff.md`：Week5 前置改动中 `_build_module_prompt` 补充真实符号（先查 `db.iter_nodes()` 取模块实际符号拼入 prompt，加提示"仅列出下方实际存在的符号，不要编造"），依赖 `extract_symbol_docstrings` 提供文档字符串减少 LLM 幻觉。`ref_docs_prompt_section` 在 project_map 与 module segment prompt 末尾注入参考文档列表。
