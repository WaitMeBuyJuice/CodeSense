---
repo: CodeSense_V1
generated_at: 2026-06-29
---

# CodeSense_V1 系统架构

## 系统层次划分

CodeSense_V1 采用 4 层单向无环架构（上→下依赖，严禁反向）：

| 层 | 模块 | 职责 | 关键文件 |
|----|------|------|---------|
| L1 入口 | `server` | 构造 mcp Server 实例；绑定 stdio transport；把 `list_tools`/`call_tool` 回调委派给 registry；启动期创建 `.codesenseignore` 模板 | `server/server.py` |
| L2 注册分发 | `registry` | `@tool` 装饰器（import 时注册到全局 `_REGISTRY`）；`list_tools()` 输出工具元数据；`dispatch()` 做 jsonschema 校验 + 调 handler + 捕获 ToolError 转 MCP 错误响应 | `registry/registry.py` |
| L3 工具 | `tools` | 8 个 MCP 工具实现（`@tool` 注册）；参数校验 + 委派 summarizer/data/cache + 缓存引导；纯业务，不含协议传输 | `tools/*.py` |
| 协调/基础设施 | `summarizer` / `data` / `cache` / `errors` | summarizer 协调 data+cache 产出 prompt 与渲染；data 只读查询 CodeGraph DB；cache 读写 `.codesense/`；errors 异常体系 | 各模块目录 |

依赖方向（来自 `workspace.json` cross_module_hints，已与源码核对）：

```
server ──► registry ──► errors
   │        ▲
   │        │ @tool 注册
   └──► tools ──► data
          │  └──► summarizer ──► data
          │  │        │  └──► cache
          │  │        └──► cache
          │  └──► cache
          └──► errors
```

- `cache`、`errors` 为叶子（不依赖任何内部模块）。
- `data` 仅依赖标准库 + `pathspec`，几乎不依赖内部模块（errors 同层基础设施）。
- `summarizer` 依赖 `data` + `cache` + `errors`，是协调枢纽。
- `tools` 依赖 `data` + `summarizer` + `cache` + `errors` + `registry`（装饰器）。
- `server` 依赖 `registry`（回调）+ `tools`（import 触发注册，noqa F401）。
- **严禁反向依赖**：registry 不能 import tools；data/cache/errors 不能 import summarizer/tools。

## 模块边界规则

- **新增 MCP 工具**：新建 `tools/<name>.py`（内联 `@tool` + input_schema）→ 在 `tools/__init__.py` 加 import 触发注册 → schema 内联在工具文件，不集中存放。
- **工具函数签名约定**：`@tool(name, description, input_schema)` 装饰；handler 同步或 async 均可，返回 `str`（registry 包装为 `TextContent`）；handler 原样返回不包装，便于单测直接调用。
- **参数校验集中在 registry**：`jsonschema.Draft202012Validator` 在 dispatch 中统一校验，工具函数体不重复校验；`_translate_jsonschema_error` 把 required/type/additionalProperties 错误翻成中文。
- **错误处理约定**：业务/校验错误抛 `ToolError` 子类 → registry 兜底转 `isError=true` 的 `CallToolResult`；未知异常兜底转 `内部错误：<ExcType>: <e>`，进程不崩溃。工具内**业务校验失败**（schema 通过但语义非法，如空字符串、模块不存在）抛 `InvalidArgumentError`；**LLM 相关**（实为宿主 Agent 调用，CodeSense 自身不抛 LLMError）保留 `LLMError` 类型。
- **工具错误返回 Markdown 而非异常**：project_map / explore_module 等"引导型"工具在缓存未就绪/DB 缺失/模块不存在时，返回包含错误描述或生成步骤的 Markdown 字符串（不抛异常），保证被动语义不被破坏。
- **缓存读写约定**：所有 `read_*` 返回 `None`（视为 miss）；`write_*` 传播 `OSError`；`invalidate` 静默忽略缺失。tools 层不直写 `.codesense/`，一律经 cache 模块。
- **项目根解析**：统一经 `tools/_project_root.py:resolve_project_root()` 三级 fallback（env → MCP roots/list → CWD 向上找 `.codegraph/codegraph.db`），不在各工具重复实现。
- **summarizer 不直接调 LLM**：summarizer 只产出 prompt 文本 + 解析 Agent 返回 + 渲染 Markdown；LLM 调用由宿主 Agent 完成。这是与 Week3 设计文档的关键差异（Week3 文档已过时）。

## 核心数据流

### project_map 工具（项目架构概览）

```
Agent 调 project_map(_nonce)
  → tools/project_map.py:project_map                       ← L3 入口
    → resolve_project_root (env/MCP roots/CWD)
    → 检查 .codegraph/codegraph.db 存在
    → CodeGraphDB 一次打开，收集 modules/edges/files/tree/identity_sources
    → data.hashes: compute_identity_hash / compute_structure_hash
                   / compute_architecture_hash / compute_dependencies_hash
    → 02_structure / 04_dependencies 缺失 → summarizer.render_*_segment 程序渲染
                                          → cache.write_segment
    → 01_identity / 03_modules 缺失 → 返回引导 Markdown
        （让 Agent 调 get_identity_segment_prompt → save_project_map_segment
            或 get_modules_segment_prompt → submit_project_map）
    → 全段就绪 → cache.render_project_map 拼接 4 段返回
```

### submit_project_map 工具（Agent 回写模块划分）

```
Agent 调 submit_project_map(response="模块名|职责|目录")
  → tools/submit_project_map.py → summarizer.submit_project_map
    → _parse_modules_text（目录 fuzzy 校正/去重/冲突丢弃/警告）
    → _expand_module_files（展开目录→文件，父子目录排除，单文件模块）
    → _migrate_renamed_module_caches（hash 一致复用旧 .md）
    → cache.write_modules_index + 写 03_modules/04_dependencies 段
    → cache.render_project_map
```

### explore_module 工具（模块深度理解）

```
Agent 调 explore_module(module_name)
  → tools/explore_module.py:explore_module                  ← L3 入口
    → 读 modules_index（缺失→引导先 project_map）
    → L2 辅助目录检查 / 找 L1 模块 entry（找不到→列可用模块）
    → _compute_module_hash + 读 modules/<safe_key>.md 缓存
    → 命中返回；未命中→引导（get_module_prompt → save_module_summary）
```

### tools/call 协议层（registry 分发）

```
Agent ──tools/call{name,args}──► server._call_tool
  → registry.dispatch(name, args)
    → jsonschema.Draft202012Validator 校验（失败→_translate_jsonschema_error→isError=true）
    → spec.handler(**args)（同步/async）
    → 捕获 ToolError → isError=true 的 CallToolResult
    → 捕获 Exception → "内部错误：<ExcType>" isError=true
    → 正常 → CallToolResult(content=[TextContent], isError=false)
```

## 系统架构约束

- [跨模块禁忌] tools 层禁止直写 `.codesense/` 文件，必须经 cache 模块 → 保证缓存键/失效/meta 一致性
- [跨模块禁忌] registry 禁止 import tools → 注册机制依赖 tools 被 server import 触发，反向依赖会成环
- [数据流方向] project_map 的 4 段必须按 `01→02→03→04` 顺序拼接（`cache._SEGMENT_IDS`），任一段缺失 render_project_map 返回 None
- [缓存失效] 02/04 段基于源数据 hash 自动失效（compute_structure_hash/compute_dependencies_hash）；01/03 段基于各自源 hash；模块摘要基于 per-module content hash（_compute_module_hash = sha1(sorted files + symbol fingerprints)）
- [失效开关] `CODESENSE_CACHE_AUTO_EXPIRE=false` 时所有缓存"存在即有效"，不比对 hash（用于离线/调试）
- [性能红线] `directory_symbols` 单目录符号上限 `max_per_dir=50`，防 LLM prompt token 超限
- [安全] stdout 严格只出 JSON-RPC 帧；stderr 保留但当前不写日志（stdio 下 stdout 不可污染）
- [单实例] 一个 MCP Server 实例只服务一个项目（`CODESENSE_PROJECT_ROOT` 单值），不支持多项目切换
- [MCP SDK 陷阱] `@server.call_tool` 必须加 `validate_input=False`（SDK 默认校验会拒绝自定义 schema）；`list_tools` 回调返回 `list[Tool]`；`mcp` 版本锁定 1.27.2

## 外部接口规范

CodeSense 对外暴露的 MCP 接口（8 个工具，无 resources）：

| 工具 | 参数 | 触发场景 |
|------|------|---------|
| `project_map` | `_nonce?: string` | 理解项目整体结构/架构/模块分布 |
| `explore_module` | `module_name: string`（project_map 中的模块名） | 深入理解单个模块的接口/结构/依赖 |
| `get_module_prompt` | `module_name: string` | explore_module 缺失时取模块摘要提示词（通常委派子 Agent） |
| `get_identity_segment_prompt` | （无） | project_map 缺 01_identity 段时取提示词 |
| `get_modules_segment_prompt` | （无） | project_map 缺 03_modules 段时取模块划分提示词 |
| `submit_project_map` | `response: string`（`模块名\|职责\|目录` 每行一个） | 提交 Agent 生成的模块划分，写缓存 |
| `save_project_map_segment` | `segment_id: "01_identity"\|"03_modules"`, `content: string` | 保存 Agent 生成的 project_map 段 |
| `save_module_summary` | `module_name: string`, `summary: string` | 保存 Agent 生成的模块摘要 |

> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/overview.md`、`doc/Week3/project_overview_for_qa.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录；Week2/3 设计文档部分已过时，以实际源码为准）
