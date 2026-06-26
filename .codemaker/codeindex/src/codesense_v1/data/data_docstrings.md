---
entity_names:
  constants:
    - name: "_DOCSTRING_ENV"
      value: "\"CODESENSE_EXTRACT_DOCSTRINGS\""
      source: "src/codesense_v1/data/docstrings.py"
    - name: "_MAX_LEN"
      value: "200"
      source: "src/codesense_v1/data/docstrings.py"
    - name: "_LOOKAHEAD"
      value: "10"
      source: "src/codesense_v1/data/docstrings.py"
    - name: "_LOOKBEHIND"
      value: "20"
      source: "src/codesense_v1/data/docstrings.py"
    - name: "_FILE_SCAN"
      value: "30"
      source: "src/codesense_v1/data/docstrings.py"
    - name: "_REF_DOCS_DIR_ENV"
      value: "\"CODESENSE_REF_DOCS_DIR\""
      source: "src/codesense_v1/data/ref_docs.py"
    - name: "_REF_DOCS_RECURSIVE_ENV"
      value: "\"CODESENSE_REF_DOCS_RECURSIVE\""
      source: "src/codesense_v1/data/ref_docs.py"
    - name: "_TEXT_EXTENSIONS"
      value: 'frozenset({".md", ".txt", ".rst", ".adoc", ".markdown"})'
      source: "src/codesense_v1/data/ref_docs.py"
    - name: "_BINARY_EXTENSIONS"
      value: 'frozenset({".docx", ".pdf"})'
      source: "src/codesense_v1/data/ref_docs.py"
retrieval_hints:
  - "如何从源文件提取 docstring？支持哪些语言？"
  - "如何禁用 docstring 提取？"
  - "docstring 截断长度是多少？为什么截断？"
  - "如何配置项目参考文档目录？"
  - "ref_docs_prompt_section 返回什么格式？"
  - "Python 和 TypeScript 的 docstring 提取方式有什么不同？"
architectural_role: "文档提取与参考文档发现，data 模块中唯一执行文件 I/O 的子模块组"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部函数调用。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：

| 模块 | 用途 | 关键符号 |
|------|------|---------|
| `data/db` | docstrings.py 引用 `NodeRow` 类型（获取 start_line 定位声明行） | `NodeRow` |

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `summarizer` | 提取 docstring 丰富模块摘要 | `extract_file_docstring`, `extract_symbol_docstrings`, `is_enabled` (as `docstrings_enabled`) |
| `summarizer` | 生成参考文档提示段 | `ref_docs_prompt_section` |

## 典型调用链

### 提取文件和符号的 docstring（docstrings.py）
```
summarizer
  → if docstrings_enabled():   ← 检查 CODESENSE_EXTRACT_DOCSTRINGS 环境变量
  → extract_file_docstring(file_path, language)
    → 读取文件前 _FILE_SCAN(30) 行
    → 按语言分发:
      Python   → _file_docstring_python: 跳过 shebang/encoding，找 triple-quote
      TS/JS    → _jsdoc_forward: 找 /** ... */ 块，fallback // 行注释
      Go       → _line_comment_forward(lines, "//")
      Rust     → _line_comment_forward(lines, "//!") or "//"
      Erlang   → _line_comment_forward(lines, "%%")
      Ruby/Shell → _line_comment_forward(lines, "#")
    → 返回第一行非空内容，截断至 _MAX_LEN(200)

  → extract_symbol_docstrings(file_path, language, nodes)
    → 读取文件一次（无论多少 node）
    → 对每个 node:
      Python   → _python_triple_quote: 声明行之后找 triple-quote
      TS/JS    → _jsdoc_backward: 声明行之前找 /** ... */，fallback // 行注释
      Go       → _line_comment_backward: 声明行之前连续 // 行
      Rust     → _line_comment_backward: 声明行之前 /// 或 //
      Erlang   → _line_comment_backward: 声明行之前 %%
      Ruby/Shell → _line_comment_backward: 声明行之前 #
    → 返回 {node_id: docstring_first_line}
```

### 发现项目参考文档（ref_docs.py）
```
summarizer
  → section = ref_docs_prompt_section(project_root)
    → discover_ref_docs(project_root)
      → 读取 CODESENSE_REF_DOCS_DIR 环境变量 → 定位目录
      → 读取 CODESENSE_REF_DOCS_RECURSIVE 环境变量 → 是否递归
      → 扫描匹配的后缀: .md/.txt/.rst/.adoc/.markdown/.docx/.pdf
      → 返回排序后的 Path 列表
    → 无文档 → 返回 ""
    → 有文档 → 生成 Markdown 提示段，指导 Agent 读取参考文档
```

## 支持的语言与提取策略

| 语言 | 文件级 docstring | 符号级 docstring | 提取方式 |
|------|-----------------|-----------------|---------|
| Python | 文件顶部的 triple-quote | 声明行之后第一个 triple-quote | 向下扫描（`_LOOKAHEAD=10` 行） |
| TypeScript/JS | 文件顶部 `/** ... */`，fallback `//` | 声明行之前的 `/** ... */`，fallback `//` | 向上扫描（`_LOOKBEHIND=20` 行） |
| Go | 文件顶部 `//` 行注释 | 声明行之前的连续 `//` 行 | 向上扫描 |
| Rust | 文件顶部 `//!`，fallback `//` | 声明行之前的 `///`，fallback `//` | 向上扫描 |
| Erlang | 文件顶部 `%%` 行注释 | 声明行之前的连续 `%%` 行 | 向上扫描 |
| Ruby/Shell | 文件顶部 `#` 行注释 | 声明行之前的连续 `#` 行 | 向上扫描 |

## 实现约束清单

### 必须定义的常量/枚举

| 标识符 | 值 | 所在文件 | 说明 |
|-------|----|---------|------|
| `_DOCSTRING_ENV` | `"CODESENSE_EXTRACT_DOCSTRINGS"` | `docstrings.py` | 环境变量名，设 `false` 禁用所有提取 |
| `_MAX_LEN` | `200` | `docstrings.py` | docstring 最大字符数（仅保留第一行），不可增大——控制 prompt 长度 |
| `_LOOKAHEAD` | `10` | `docstrings.py` | Python 声明后搜索行数 |
| `_LOOKBEHIND` | `20` | `docstrings.py` | 注释前置语言声明前搜索行数 |
| `_FILE_SCAN` | `30` | `docstrings.py` | 文件级 docstring 搜索行数上限 |
| `_REF_DOCS_DIR_ENV` | `"CODESENSE_REF_DOCS_DIR"` | `ref_docs.py` | 参考文档目录环境变量 |
| `_REF_DOCS_RECURSIVE_ENV` | `"CODESENSE_REF_DOCS_RECURSIVE"` | `ref_docs.py` | 是否递归扫描参考文档 |
| `_TEXT_EXTENSIONS` | `{".md",".txt",".rst",".adoc",".markdown"}` | `ref_docs.py` | 文本类参考文档扩展名 |
| `_BINARY_EXTENSIONS` | `{".docx",".pdf"}` | `ref_docs.py` | 二进制参考文档扩展名（仅返回路径） |

### docstring 提取契约

| 约束 | 说明 |
|------|------|
| 环境变量控制 | `CODESENSE_EXTRACT_DOCSTRINGS=false` 时 `is_enabled()` 返回 `False`，所有提取跳过 |
| 截断规则 | 仅返回第一行非空内容，截断至 `_MAX_LEN(200)` 字符 |
| 文件读取 | 每种语言每种场景最多读取文件一次（`extract_symbol_docstrings` 单文件只读一次） |
| 容错 | 文件不存在/编码错误 → 返回 `None` 或空 dict，绝不抛异常 |
| 单次读取 | `extract_symbol_docstrings` 接受 `list[NodeRow]`，所有节点共享一次文件读取 |

### 参考文档契约

| 约束 | 说明 |
|------|------|
| 目录不存在 | `discover_ref_docs` 返回空列表，`ref_docs_prompt_section` 返回 `""` |
| 非递归默认 | 仅扫描目录一级，设 `CODESENSE_REF_DOCS_RECURSIVE=true` 递归 |
| 二进制文档 | `.docx`/`.pdf` 仅返回路径并标注格式提示，不提取内容 |
| 路径解析 | 相对路径基于 `project_root` 解析为绝对路径 |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| docstring 截断 | 仅第一行 200 字符 | 全文截断 | 控制 prompt token 消耗，第一行通常是摘要 |
| 环境变量开关 | `CODESENSE_EXTRACT_DOCSTRINGS` | 函数参数 | 运行时无需改代码即可禁用 |
| 参考文档目录 | 环境变量配置 | 硬编码路径 | 每个项目参考文档位置不同 |
| Python vs TS 策略 | Python 向下扫描，TS 向上扫描 | 统一向上 | 遵循各语言 docstring 语法位置惯例 |
