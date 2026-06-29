---
entity_names:
  constants:
    - name: _CODESENSE_DIR
      value: ".codesense"
      source: src/codesense_v1/tools/project_map.py
    - name: _PROJECT_MAP_INPUT_SCHEMA
      value: "object; properties: _nonce(string, 非必填, 绕过客户端重复调用检测); additionalProperties: false"
      source: src/codesense_v1/tools/project_map.py
    - name: _VALID_SEGMENT_IDS
      value: '("01_identity", "03_modules")'
      source: src/codesense_v1/tools/save_project_map_segment.py
    - name: _SCHEMA (get_identity_segment_prompt)
      value: "object; properties: {}; additionalProperties: false（无参数工具）"
      source: src/codesense_v1/tools/get_identity_segment_prompt.py
    - name: _SCHEMA (get_modules_segment_prompt)
      value: "object; properties: {}; additionalProperties: false（无参数工具）"
      source: src/codesense_v1/tools/get_modules_segment_prompt.py
    - name: _SCHEMA (submit_project_map)
      value: "object; properties: response(string, 模块划分文本 每行 模块名|职责|目录); required: [response]; additionalProperties: false"
      source: src/codesense_v1/tools/submit_project_map.py
    - name: _SCHEMA (save_project_map_segment)
      value: "object; properties: segment_id(string, enum=[01_identity,03_modules]), content(string); required: [segment_id, content]; additionalProperties: false"
      source: src/codesense_v1/tools/save_project_map_segment.py
retrieval_hints:
  - "正向疑问句：project_map 工具是怎么工作的？4 段拼接逻辑是什么？"
  - "正向疑问句：01_identity / 03_modules 段缺失时 project_map 如何引导 Agent 生成？"
  - "正向疑问句：save_project_map_segment 的 segment_id 只能取哪些值？"
  - "⚠️ 反向排除：若找模块摘要渲染/解析/LLM 调用，不在这里，在 summarizer；tools 只做参数校验与委派"
  - "⚠️ 反向排除：若找 explore_module / get_module_prompt / save_module_summary，在 tools_module.md，不在本文档"
  - "架构归属句：新增 MCP 工具必须新建 tools/<name>.py + 在 __init__.py 注册 import，schema 内联在各工具文件"
  - "本模块也叫 project_map 段生成工作流（01_identity + 03_modules 需 Agent 生成，02/04 程序生成）"
architectural_role: "MCP 工具层"
---

## 对外接口

| 工具名 | 方向 | 关键参数 | 业务说明 | 入口符号 |
|--------|------|---------|---------|---------|
| `project_map` | client→server | `_nonce?: string`（非必填，绕过客户端重复调用检测） | 返回项目架构概览（4 段拼接）。02/04 缺失则程序渲染并缓存；01/03 缺失则返回引导让 Agent 调对应工具生成；全有则 `render_project_map` 拼接返回 | `project_map` |
| `get_identity_segment_prompt` | client→server | 无参数 | 返回生成 01_identity 段（仓库定位+技术栈）的 LLM 提示词。收集 identity sources + extract_tech_stack_hint 后委派 summarizer | `get_identity_segment_prompt_tool` |
| `get_modules_segment_prompt` | client→server | 无参数 | 返回生成 03_modules 段（模块划分）的 LLM 提示词。委派 `summarizer.get_project_map_prompt` | `get_modules_segment_prompt_tool` |
| `submit_project_map` | client→server | `response: string`（必填，每行 `模块名\|职责\|目录`，多目录逗号分隔） | 接收模块划分文本，委派 `summarizer.submit_project_map` 写缓存并返回渲染后的架构 Markdown | `submit_project_map_tool` |
| `save_project_map_segment` | client→server | `segment_id: string`（必填，enum 01_identity/03_modules）, `content: string`（必填） | 保存 Agent 生成的 project_map 段落到缓存。校验 segment_id ∈ `_VALID_SEGMENT_IDS` + content 非空，计算当前 source hash 后 `cache.write_segment` | `save_project_map_segment_tool` |

## 跨模块依赖

**外部依赖（tools 调用方）**：

| 依赖模块 | 使用方式 |
|---------|---------|
| `data` | `project_map` 调 `list_modules`/`module_dependencies`/`collect_identity_sources`/`compute_identity_hash`/`compute_structure_hash`/`compute_dependencies_hash`/`compute_architecture_hash`/`classify_top_dirs`/`directory_tree`/`find_cycles`/`topological_layers`/`compute_tree_max_depth`；`get_identity_segment_prompt` 调 `collect_identity_sources`/`extract_tech_stack_hint`；`save_project_map_segment` 调 `collect_identity_sources`/`compute_identity_hash`/`compute_architecture_hash`/`classify_top_dirs` 等 |
| `summarizer` | `project_map` 调 `render_structure_segment`/`render_dependencies_segment`/`is_auto_expire_enabled`；`get_identity_segment_prompt` 调 `get_identity_segment_prompt`；`get_modules_segment_prompt` 调 `get_project_map_prompt`；`submit_project_map` 调 `submit_project_map` |
| `cache` | `project_map` 调 `read_segment`/`write_segment`/`is_segment_valid`/`render_project_map`/`read_modules_index`；`save_project_map_segment` 调 `read_modules_index`/`write_segment` |
| `errors` | `save_project_map_segment` 抛 `InvalidArgumentError`（segment_id 非法 / content 空）；`submit_project_map` 抛 `LLMError`（经 summarizer 传播） |
| `registry` | 全部 5 工具用 `@tool` 装饰器注册 |
| `_project_root` | 全部 5 工具调 `resolve_project_root()` + `project_root_not_found_error()` |

**反向调用方**：

| 调用方 | 关系 |
|--------|------|
| `server` | `import codesense_v1.tools` 触发注册（`# noqa: F401`） |
| `registry` | `dispatch(name, arguments)` 按 name 调对应 handler |

## 典型调用链

1. **project_map 全段就绪**：`tools/call{project_map} → registry.dispatch → project_map handler → resolve_project_root → CodeGraphDB 查 modules/edges/files/tree/identity → compute 4 段 hash → _seg_valid 全通过 → cache.render_project_map → 返回拼接 Markdown`

2. **project_map 缺 03_modules 引导生成**：`project_map(need_03=true) → 返回引导 → get_modules_segment_prompt → summarizer.get_project_map_prompt → Agent 生成模块划分文本 → submit_project_map(response) → summarizer.submit_project_map → cache.write_modules_index（同步清空 modules/ 子缓存）→ 重新 project_map → 03 hash 重算 → render_project_map`

3. **project_map 缺 01_identity 引导生成**：`project_map(need_01=true) → 返回引导 → get_identity_segment_prompt → collect_identity_sources + extract_tech_stack_hint → summarizer.get_identity_segment_prompt → Agent 生成内容 → save_project_map_segment(segment_id="01_identity", content) → compute_identity_hash → cache.write_segment → 重新 project_map`

4. **02/04 程序自动生成（无 Agent）**：`project_map → _seg_valid(02_structure)=false → compute_tree_max_depth → render_structure_segment → cache.write_segment(02) → _seg_valid(04_dependencies)=false → render_dependencies_segment → cache.write_segment(04)`

## 实现约束清单

**必须定义的常量/枚举**：

| 常量 | 值 | 文件 |
|------|-----|------|
| `_CODESENSE_DIR` | `".codesense"` | project_map.py |
| `_VALID_SEGMENT_IDS` | `("01_identity", "03_modules")` | save_project_map_segment.py |
| `_PROJECT_MAP_INPUT_SCHEMA` | object, `_nonce?: string`, additionalProperties false | project_map.py |
| `_SCHEMA` (×4) | 见 frontmatter constants | 各工具文件 |

**必须包含的协议字段（schema required）**：

| 工具 | required 字段 |
|------|--------------|
| `project_map` | 无 required（`_nonce` 非必填） |
| `get_identity_segment_prompt` | 无 required（无参数） |
| `get_modules_segment_prompt` | 无 required（无参数） |
| `submit_project_map` | `["response"]` |
| `save_project_map_segment` | `["segment_id", "content"]` |

**必须实现的函数**：

| 函数 | 职责 |
|------|------|
| `project_map(_nonce=None)` | 4 段 hash 计算 + 02/04 程序渲染 + 01/03 引导 + 全有拼接 |
| `get_identity_segment_prompt_tool()` | 收集 sources + 委派 summarizer |
| `get_modules_segment_prompt_tool()` | 委派 `summarizer.get_project_map_prompt` |
| `submit_project_map_tool(response)` | 委派 `summarizer.submit_project_map` |
| `save_project_map_segment_tool(segment_id, content)` | 校验 + 计算 hash + `cache.write_segment` |
| `_seg_valid(codesense_dir, seg_id, current_hash, auto_expire)` | 据 auto_expire 决定用 `is_segment_valid`（带 hash 比对）还是 `read_segment`（存在即有效） |

**设计决策**：

| 决策 | 说明 |
|------|------|
| `_nonce` 绕过重复检测 | project_map 的 `_nonce` 参数仅为绕过客户端重复调用检测，无业务语义；schema 中 description 为空串 |
| tools 只委派不做业务 | 5 工具均只做参数校验 + 项目根定位 + 委派 summarizer/cache/data，业务逻辑在 summarizer |
| 错误返回 Markdown 而非异常 | 项目根未找到 / DB 不存在返回错误 Markdown 字符串（不抛异常）；参数非法抛 `InvalidArgumentError`（registry 转 isError） |
| 02/04 程序生成 01/03 需 Agent | 02_structure / 04_dependencies 纯程序渲染（`render_structure_segment`/`render_dependencies_segment`）并缓存；01_identity / 03_modules 需 Agent 调 prompt 工具生成后保存 |
| auto_expire 双模式 | `_seg_valid` 据 `is_auto_expire_enabled()` 切换：开启则 `is_segment_valid`（比对 hash，源变则失效）；关闭则 `read_segment is not None`（存在即有效） |
| 03 hash 依赖已保存模块目录 | `compute_architecture_hash(module_dir_groups)` 用 `read_modules_index` 中已保存的模块 directories 计算，故 03 须在 submit_project_map 写入 modules_index 后才能稳定 |

## 附：内置文档摘要

> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/tools.md`、`doc/Week2/design/overview.md`（原文已提炼，非完整转录）

- **L3 工具层定位**（overview.md §2）：每个 `.py` 文件实现 1 个工具，`@tool` 装饰器自注册，`__init__.py` import 触发注册。工具体内只关心业务逻辑，不触碰 MCP 类型/JSON 协议/传输细节；入参用关键字参数接收与 schema `properties` 名称一一对应；输出必须为 `str`（registry 包装为 `TextContent`）。
- **D1/D2 决策**（overview.md §5）：D1 分层架构（入口/注册/工具/基础设施）使新增工具零侵入；D2 `@tool` 装饰器自动注册使工具元数据与实现共置，新增门槛最低。
- **工具函数签名约定**（overview.md §3.2）：`@tool(name, description, input_schema)` + `def handler(...) -> str`。
- **新增工具步骤**（tools.md §6）：① 新建 `tools/<name>.py`（schema 内联）② `tools/__init__.py` 加 `from . import <name>  # noqa: F401`。
- **演进说明**：Week2 文档以 `add` demo 工具为例、Week3 文档用 `module_path` 参数，均已被 Week5+ 实际源码取代（`module_path`→`module_name`、segment 化 project_map、新增 5 个 segment 工具）。以实际源码为准。
