# Week 3 概要设计 — Overview

> 基于 `doc/Week3/requirement.md`、`doc/stack.md`、`doc/Week2/design/overview.md`。
> Week 2 已有的 L1~L4 层保持不变，本文档仅覆盖 Week 3 新增模块的架构扩展。

---

## 1. 整体架构（扩展后）

```
                    ┌──────────────────────────────────────┐
                    │      CodeMaker Agent (Host)          │
                    └──────────────┬───────────────────────┘
                                   │ spawn stdio
                                   ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                  CodeSense_V1 Server Process                    │
 │                                                                 │
 │  ┌──────────────────────────────────────────────────────────┐   │
 │  │ L1  入口层  server.py                                     │   │
 │  │     - list_tools / call_tool（Week 2）                   │   │
 │  │     - list_resources / read_resource（Week 3 新增）       │   │
 │  └──────────────────┬────────────────────┬──────────────────┘   │
 │                     │ call_tool           │ read_resource        │
 │                     ▼                     ▼                     │
 │  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
 │  │ L2  注册/分发层       │  │ L5  Resource 层（Week 3 新增）   │  │
 │  │ registry.py          │  │ resources/project_map.py         │  │
 │  │ (Week 2，不变)        │  │  - read() → Markdown str        │  │
 │  └──────────┬───────────┘  └──────────────┬───────────────────┘  │
 │             │ dispatch                     │ generate             │
 │             ▼                             ▼                     │
 │  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
 │  │ L3  工具层            │  │ L6  Summarizer 层（Week 3 新增） │  │
 │  │ tools/add.py          │  │ summarizer.py                    │  │
 │  │ tools/explore_module  │  │  - project_map_summary(...)      │  │
 │  │   .py（Week 3 新增）  │  │  - module_summary(...)           │  │
 │  └──────────────────────┘  └──────────────┬───────────────────┘  │
 │                                           │                      │
 │              ┌────────────────────────────┤                      │
 │              ▼                            ▼                      │
 │  ┌────────────────────────┐  ┌──────────────────────────────┐    │
 │  │ L4  基础设施层（已有）  │  │ L7  新增基础设施层            │    │
 │  │ schemas.py / errors.py │  │ llm.py   — LLM API 调用封装  │    │
 │  │ data/（db/files/       │  │ cache.py — .codesense/ 读写   │    │
 │  │   modules/aggregate）  │  └──────────────────────────────┘    │
 │  └────────────────────────┘                                      │
 └─────────────────────────────────────────────────────────────────┘
                    │
 ┌──────────────────▼───────────────────────────────────────────────┐
 │   .codegraph/codegraph.db（CodeGraph 生成，只读）                 │
 │   .codesense/（CodeSense 缓存，Week 3 生成）                      │
 └──────────────────────────────────────────────────────────────────┘
```

---

## 2. 新增模块列表与职责

| 层   | 模块                       | 文件                                            | 职责                                                                 | 不负责                        |
|------|----------------------------|-------------------------------------------------|----------------------------------------------------------------------|-------------------------------|
| L5   | `resources/project_map`    | `src/codesense_v1/resources/project_map.py`     | MCP Resource 的读取实现；触发 Lazy 缓存检查；调用 summarizer 生成内容 | LLM 调用细节、缓存读写细节    |
| L3   | `tools/explore_module`     | `src/codesense_v1/tools/explore_module.py`      | MCP Tool 实现；接收 module_path 参数；校验模块边界；调用 summarizer  | LLM 调用细节、缓存读写细节    |
| L6   | `summarizer`               | `src/codesense_v1/summarizer.py`                | 将 Data Layer 的结构数据拼装成 Markdown prompt 并调用 LLM；返回 Markdown 摘要 | 缓存读写、MCP 协议             |
| L7   | `llm`                      | `src/codesense_v1/llm.py`                       | 封装 OpenAI 兼容 API 调用；从环境变量读配置；抛 `LLMError`           | prompt 内容、缓存               |
| L7   | `cache`                    | `src/codesense_v1/cache.py`                     | `.codesense/` 目录的读写；`meta.json` 管理；DB hash 计算；缓存失效判断 | LLM 调用、结构数据提取         |

> `schemas.py` 新增 `EXPLORE_MODULE_INPUT_SCHEMA` 常量（属于 L4，原有文件扩展）。
> `errors.py` 新增 `LLMError` 异常类（属于 L4，原有文件扩展）。
> `server.py` 新增 Resource 回调绑定（属于 L1，原有文件扩展）。

---

## 3. 模块间依赖关系

### 3.1 依赖方向（上→下，单向，无环）

```
server
  ├──► registry ──► errors / schemas / data/*（Week 2，不变）
  │       └──► tools/explore_module ──► summarizer ──► llm ──► errors
  │                                               └──► cache ──► errors
  │                                               └──► data/*
  └──► resources/project_map ──► summarizer
                              └──► cache
```

规则：
- `server` 依赖 `resources/project_map` 仅为绑定 Resource 回调（import）。
- `resources/project_map` 和 `tools/explore_module` 均依赖 `summarizer`、`cache`。
- `summarizer` 依赖 `llm`、`cache`（仅读）、`data/*`。
- `llm`、`cache` 为叶子，仅依赖 `errors` 和标准库/第三方。
- 严禁反向依赖（`llm` / `cache` 不能 import `summarizer` 或 `tools`）。

### 3.2 接口边界（公开 API 草稿，详细设计中确定）

**`cache` 对外接口**
```python
def db_hash(db_path: Path) -> str: ...
def is_cache_valid(codesense_dir: Path, current_hash: str) -> bool: ...
def read_project_map(codesense_dir: Path) -> str | None: ...
def write_project_map(codesense_dir: Path, content: str, db_hash: str) -> None: ...
def read_module(codesense_dir: Path, module_key: str) -> str | None: ...
def write_module(codesense_dir: Path, module_key: str, module_path: str, summary: str) -> None: ...
def invalidate(codesense_dir: Path) -> None: ...
```

**`llm` 对外接口**
```python
async def call_llm(prompt: str) -> str: ...   # raises LLMError on failure
```

**`summarizer` 对外接口**
```python
async def project_map_summary(db: CodeGraphDB, codesense_dir: Path) -> str: ...
async def module_summary(db: CodeGraphDB, codesense_dir: Path, module_path: str) -> str: ...
```

**`resources/project_map` 对外接口**
```python
async def read(project_root: Path) -> str: ...  # raises ToolError subclass
```

**`tools/explore_module` 工具签名**
```python
@tool(name="explore_module", ...)
async def explore_module(module_path: str) -> str: ...   # raises InvalidArgumentError / LLMError
```

---

## 4. 数据流向

### 4.1 `project_map` 读取（缓存命中）

```
Agent ──read_resource(codesense://project_map)──► server
                                                    │ read_resource 回调
                                                    ▼
                                          resources/project_map.read(project_root)
                                                    │ cache.is_cache_valid()  → True
                                                    │ cache.read_project_map() → Markdown
                                                    ▼
Agent ◄──ReadResourceResult(contents=[text/markdown])──
```

### 4.2 `project_map` 读取（缓存失效）

```
... resources/project_map.read(project_root)
        │ cache.is_cache_valid() → False
        │ cache.invalidate()
        ▼
     summarizer.project_map_summary(db, codesense_dir)
        │ data.list_modules() + data.module_dependencies()...
        │ 拼 Markdown prompt
        │ llm.call_llm(prompt) → Markdown 摘要
        │ cache.write_project_map(codesense_dir, summary, hash)
        ▼
     返回 Markdown 摘要
```

### 4.3 `explore_module` 调用

```
Agent ──call_tool("explore_module", {"module_path": "src/auth"})──► server
                                                                       │ dispatch
                                                                       ▼
                                                            tools/explore_module(module_path)
                                                                       │ 校验 __init__.py 存在
                                                                       │ cache.is_cache_valid() ?
                                                                       │  命中 → cache.read_module()
                                                                       │  未命中 → summarizer.module_summary()
                                                                       ▼
Agent ◄──CallToolResult(content=[Markdown], isError=false)──
```

---

## 5. 关键技术决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | `project_map` 用 MCP Resource 而非 Tool | Resource 在 AI 连接时被动注入，无需 AI 主动调用；符合"不需要主动性就能获得架构认知"的设计目标 |
| D2 | 缓存粒度为 project 级（单一 DB hash） | 简单可靠；DB 文件整体变化时全量重生，避免部分失效导致 project_map 与 module 摘要不一致 |
| D3 | summarizer 独立于 tools/resources | 可被两个功能复用；便于单测（不需要 MCP 环境）；LLM prompt 迭代不影响 Tool/Resource 层 |
| D4 | `llm.py` 读环境变量配置 | 避免 API Key 硬编码进仓库；便于不同机器/环境切换 |
| D5 | 模块边界 = `__init__.py` 存在 | Python 项目约定；简单且无歧义；与 Data Layer 的 `package_id` 概念一致 |
| D6 | explore_module 参数为目录路径 | 对 AI 最直观（能从文件路径直接推导）；与 Data Layer 的文件路径体系对齐 |
| D7 | 新增 `LLMError(ToolError)` | 统一错误处理链路；LLM 失败经 registry 转为 `isError=true`，不泄漏堆栈 |

---

## 6. 目录结构（落地预览）

```
src/codesense_v1/
├── __init__.py
├── server.py              ← L1，新增 Resource 回调
├── registry.py            ← L2，不变
├── schemas.py             ← L4，新增 EXPLORE_MODULE_INPUT_SCHEMA
├── errors.py              ← L4，新增 LLMError
├── llm.py                 ← L7（新增）
├── cache.py               ← L7（新增）
├── summarizer.py          ← L6（新增）
├── tools/
│   ├── __init__.py        ← 新增 explore_module 导入
│   ├── add.py
│   └── explore_module.py  ← L3（新增）
├── resources/
│   ├── __init__.py        ← 新增
│   └── project_map.py     ← L5（新增）
└── data/
    ├── db.py / files.py / modules.py / aggregate.py  ← 不变
```

---

## 7. 待确认事项

| # | 问题 | 决策 |
|---|------|------|
| Q1 | `project_root` 如何传入 MCP Server？ | 从环境变量 `CODESENSE_PROJECT_ROOT` 读取；MCP 配置（`codemaker_mcp_settings.json`）中设置 `env` 字段 |
| Q2 | `module_path` 相对于哪个根？ | 相对于 `project_root`，如 `src/auth` 解析为 `<project_root>/src/auth` |
| Q3 | `project_map` Resource 读取时 DB 不存在如何处理？ | 返回包含错误描述的 Markdown 内容（不使用 MCP 错误机制） |

**全部确认，进入详细设计阶段。**
