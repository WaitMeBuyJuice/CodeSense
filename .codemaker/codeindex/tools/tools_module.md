---
entity_names:
  constants:
    - name: _CODESENSE_DIR
      value: ".codesense"
      source: src/codesense_v1/tools/explore_module.py
    - name: _EXPLORE_MODULE_INPUT_SCHEMA
      value: "object; properties: module_name(string, project_map 中列出的模块名精确名称); required: [module_name]; additionalProperties: false"
      source: src/codesense_v1/tools/explore_module.py
    - name: _SCHEMA (get_module_prompt)
      value: "object; properties: module_name(string, project_map 中列出的模块名精确名称); required: [module_name]; additionalProperties: false"
      source: src/codesense_v1/tools/get_module_prompt.py
    - name: _SCHEMA (save_module_summary)
      value: "object; properties: module_name(string), summary(string, 模块摘要 Markdown); required: [module_name, summary]; additionalProperties: false"
      source: src/codesense_v1/tools/save_module_summary.py
retrieval_hints:
  - "正向疑问句：explore_module 工具是怎么工作的？缓存命中和未命中分别返回什么？"
  - "正向疑问句：模块摘要生成工作流是什么？get_module_prompt → save_module_summary → 重新 explore_module"
  - "正向疑问句：explore_module 找不到模块名时返回什么？L2 辅助目录如何处理？"
  - "⚠️ 反向排除：若找 project_map / segment 段生成工具，在 tools_project_map.md，不在本文档"
  - "⚠️ 反向排除：若找模块摘要的 LLM 调用/prompt 构建/Markdown 渲染，不在这里，在 summarizer；tools 只做参数校验与委派"
  - "架构归属句：新增 MCP 工具必须新建 tools/<name>.py + 在 __init__.py 注册 import，schema 内联在各工具文件"
  - "本模块也叫模块摘要工作流（explore_module 缓存未命中引导 get_module_prompt → save_module_summary）"
architectural_role: "MCP 工具层"
---

## 对外接口

| 工具名 | 方向 | 关键参数 | 业务说明 | 入口符号 |
|--------|------|---------|---------|---------|
| `explore_module` | client→server | `module_name: string`（必填，project_map 中列出的模块名精确名称） | 返回模块深度理解。校验非空 → resolve_project_root → 检查 db → 读 modules_index（缺失引导先 project_map）→ L2 辅助目录检查 → 找 L1 模块 entry（找不到列可用模块）→ 计算 `_compute_module_hash` + 读缓存 → 命中返回，未命中返回引导 | `explore_module` |
| `get_module_prompt` | client→server | `module_name: string`（必填，project_map 中列出的模块名精确名称） | 返回生成指定模块摘要的分析提示词文本。校验非空后委派 `summarizer.get_module_prompt` | `get_module_prompt_tool` |
| `save_module_summary` | client→server | `module_name: string`（必填）, `summary: string`（必填，模块摘要 Markdown） | 将模块摘要写入缓存。校验 module_name/summary 非空后委派 `summarizer.save_module_summary`，后续 explore_module 直接返回该内容 | `save_module_summary_tool` |

## 跨模块依赖

**外部依赖（tools 调用方）**：

| 依赖模块 | 使用方式 |
|---------|---------|
| `data` | `explore_module` 用 `CodeGraphDB` 打开 DB 传给 `_compute_module_hash` |
| `summarizer` | `explore_module` 调 `is_auto_expire_enabled` + `_compute_module_hash`（从 `summarizer.summarizer` 导入）；`get_module_prompt` 调 `summarizer.get_module_prompt`；`save_module_summary` 调 `summarizer.save_module_summary` |
| `cache` | `explore_module` 调 `safe_key`/`read_modules_index`/`read_module`/`read_module_hashes` |
| `errors` | `explore_module`/`get_module_prompt`/`save_module_summary` 抛 `InvalidArgumentError`（module_name 空 / summary 空 / 模块不存在） |
| `registry` | 全部 3 工具用 `@tool` 装饰器注册 |
| `_project_root` | 全部 3 工具调 `resolve_project_root()` + `project_root_not_found_error()` |

**反向调用方**：

| 调用方 | 关系 |
|--------|------|
| `server` | `import codesense_v1.tools` 触发注册（`# noqa: F401`） |
| `registry` | `dispatch(name, arguments)` 按 name 调对应 handler |

## 典型调用链

1. **explore_module 缓存命中**：`tools/call{explore_module} → registry.dispatch → explore_module handler → 校验 module_name 非空 → resolve_project_root → 检查 db → cache.read_modules_index → L2 辅助目录检查（命中返回简略描述）→ 找 L1 entry → CodeGraphDB + _compute_module_hash → cache.read_module + read_module_hashes → hash 匹配 → 返回 cached_md`

2. **explore_module 缓存未命中引导生成**：`explore_module(module_cache_valid=false) → 返回引导（方式1委派子Agent / 方式2主Agent直接执行）→ get_module_prompt(module_name) → summarizer.get_module_prompt → Agent 生成 Markdown 摘要 → save_module_summary(module_name, summary) → summarizer.save_module_summary → 重新 explore_module → 命中返回`

3. **explore_module 模块不存在**：`explore_module(module_name) → read_modules_index → L2 检查未命中 → L1 查找未命中 → raise InvalidArgumentError（列出可用 L1 + L2 模块名）→ registry 转 isError=true`

## 实现约束清单

**必须定义的常量/枚举**：

| 常量 | 值 | 文件 |
|------|-----|------|
| `_CODESENSE_DIR` | `".codesense"` | explore_module.py |
| `_EXPLORE_MODULE_INPUT_SCHEMA` | object, `module_name: string` required, additionalProperties false | explore_module.py |
| `_SCHEMA` (get_module_prompt) | object, `module_name: string` required, additionalProperties false | get_module_prompt.py |
| `_SCHEMA` (save_module_summary) | object, `module_name: string` + `summary: string` required, additionalProperties false | save_module_summary.py |

**必须包含的协议字段（schema required）**：

| 工具 | required 字段 |
|------|--------------|
| `explore_module` | `["module_name"]` |
| `get_module_prompt` | `["module_name"]` |
| `save_module_summary` | `["module_name", "summary"]` |

**必须实现的函数**：

| 函数 | 职责 |
|------|------|
| `explore_module(module_name)` | 参数校验 + 项目根 + db 检查 + modules_index 读取 + L2 辅助目录检查 + L1 entry 查找 + hash 计算 + 缓存命中/未命中分支 |
| `get_module_prompt_tool(module_name)` | 校验非空 + 委派 `summarizer.get_module_prompt` |
| `save_module_summary_tool(module_name, summary)` | 校验非空 + 委派 `summarizer.save_module_summary` |

**设计决策**：

| 决策 | 说明 |
|------|------|
| tools 只委派不做业务 | 3 工具均只做参数校验 + 项目根定位 + 委派 summarizer/cache，业务逻辑在 summarizer |
| 错误返回 Markdown 而非异常 | 项目根未找到 / DB 不存在 / modules_index 缺失返回错误/引导 Markdown 字符串（不抛异常）；module_name 空 / 模块不存在抛 `InvalidArgumentError`（registry 转 isError） |
| module_name 精确匹配 + 大小写不敏感 | L1/L2 查找用 `str(...).strip().lower() == norm_name` 比对，trim + 大小写不敏感 |
| L2 辅助目录特殊处理 | 命中 L2 auxiliary_dirs 返回简略描述（类别 + 文件数 + 引导用 read_file/codegraph），不做深入模块结构分析 |
| auto_expire 双模式 | 开启则 `cached_md is not None and stored_hashes.get(mkey) == current_module_hash`（hash 比对）；关闭则 `cached_md is not None`（存在即有效） |
| modules_index 前置依赖 | explore_module 须先有 project_map 生成的 modules_index.json，缺失则引导先调 project_map |
| module_name 而非 module_path | Week5 改造：入参由 `module_path`（目录路径）改为 `module_name`（LLM 给的模块名），删除目录/`__init__.py` 校验，改为在 modules_index 中按名查找（语言无关） |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week3/design/tools_explore_module.md`、`doc/Week3/tasks/tools_explore_module.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

- **Week3 原设计（已过时）**：`explore_module(module_path: str)` 校验目录存在 + `__init__.py` 存在，调 `summarizer.module_summary`。错误场景含 `CODESENSE_PROJECT_ROOT` 未设置、路径不存在、非 Python 包、LLM 失败、DB 不存在。
- **Week5 改造（以实际源码为准）**：入参 `module_path` → `module_name`（LLM 给的模块名，如"缓存层"），删除目录/`__init__.py` 校验，改为在 `modules_index.json` 中按名查找（trim + 大小写不敏感）。背景：Week4 集成测试暴露 `__init__.py` 判断模块边界导致 TypeScript/Go 项目直接报错，改为语言无关的 LLM 推断方式。
- **缓存 key 规则变更**：`module_key(path)` → `safe_key(name)`（`sha1[:12]`，12 位十六进制），文件名不可读但可经 modules_index 反查。
- **modules_index 语义**：`project_map` 生成时写入；`explore_module` 读取查找模块名→文件映射；`write_modules_index` 写入时同步清空 `modules/` 子缓存（防旧 summary 与新模块名不一致）。
- **当前实现差异**：实际源码已演进为缓存命中/未命中双分支 + 引导生成工作流（get_module_prompt → save_module_summary → 重新 explore_module），非 Week3 文档的一次性 `summarizer.module_summary` 调用。
