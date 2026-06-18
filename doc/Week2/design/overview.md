# CodeSense_V1 概要设计 - Overview

> 基于 `doc/requirement.md` 与 `doc/stack.md`。MVP 范围：1 个 demo 工具 `add(a, b)`，stdio 传输，CodeMaker Agent 为目标客户端。

---

## 1. 整体架构

### 1.1 架构图（文本版）

```
                    ┌──────────────────────────────┐
                    │     CodeMaker Agent (Host)   │
                    │  (codemaker_mcp_settings)    │
                    └────────────┬─────────────────┘
                                 │ spawn stdio
                                 ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                CodeSense_V1 Server Process                  │
 │                                                             │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │ L1  入口层  src/codesense_v1/server.py                   │    │
 │  │     - 启动官方 mcp SDK Server                       │    │
 │  │     - 绑定 stdio transport                          │    │
 │  │     - 注入 registry 的 list_tools/call_tool 回调    │    │
 │  └────────────────────┬────────────────────────────────┘    │
 │                       │ 调用                                │
 │                       ▼                                     │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │ L2  注册/分发层  src/codesense_v1/registry.py            │    │
 │  │     - @tool 装饰器                                  │    │
 │  │     - ToolSpec 表（name → handler, schema, desc）   │    │
 │  │     - list_tools(): 输出工具元数据                  │    │
 │  │     - dispatch(name, args):                         │    │
 │  │         · jsonschema 校验参数                       │    │
 │  │         · 调用 handler                              │    │
 │  │         · 捕获 ToolError → MCP isError 响应         │    │
 │  └─────────┬───────────────────────────┬───────────────┘    │
 │            │ 装饰器注册                │ raise              │
 │            ▼                           ▼                    │
 │  ┌──────────────────────┐   ┌──────────────────────────┐    │
 │  │ L3 工具层            │   │ L4 基础设施层            │    │
 │  │ src/codesense_v1/tools/   │   │                          │    │
 │  │   add.py             │   │ schemas.py               │    │
 │  │   __init__.py        │   │   - ADD_INPUT_SCHEMA     │    │
 │  │ (import 时触发注册)  │   │ errors.py                │    │
 │  └──────────┬───────────┘   │   - ToolError            │    │
 │             │ 引用          │   - ValidationError      │    │
 │             └──────────────►│   - InvalidArgumentError │    │
 │                             └──────────────────────────┘    │
 └─────────────────────────────────────────────────────────────┘
```

### 1.2 进程模型

- 单进程、单线程异步（基于 mcp SDK 的 asyncio）。
- 由 CodeMaker 通过 stdio 拉起，生命周期跟随客户端。
- stdout 严格只出 JSON-RPC 帧；stderr 保留但当前不写入。

---

## 2. 模块列表与职责

| 层        | 模块         | 文件                                                         | 职责                                                                                                                                            | 不负责               |
| -------- | ---------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| L1 入口    | `server`   | `src/codesense_v1/server.py`                                    | 创建 mcp Server 实例；绑定 stdio transport；把 `list_tools` / `call_tool` 协议回调委派给 registry；进程启动/退出                                                     | 业务逻辑、参数校验、错误格式构造  |
| L2 注册/分发 | `registry` | `src/codesense_v1/registry.py`                                  | 维护 `ToolSpec` 表；提供 `@tool(name, description, input_schema)` 装饰器；`list_tools()` 输出元数据；`dispatch(name, arguments)` 做 schema 校验、调用、异常→MCP 错误响应转换 | 工具具体实现、错误类定义      |
| L3 工具    | `tools` 包  | `src/codesense_v1/tools/__init__.py`、`src/codesense_v1/tools/add.py` | 每个模块定义 1 个工具函数，用 `@tool` 装饰；纯业务逻辑；非法输入 raise `errors.*`；包 `__init__` 负责 import 全部工具模块以触发注册                                                    | 协议、传输、schema 校验执行 |
| L4 基础设施  | `schemas`  | `src/codesense_v1/schemas.py`                                   | 集中存放各工具的 JSON Schema 常量                                                                                                                       | 校验执行              |
| L4 基础设施  | `errors`   | `src/codesense_v1/errors.py`                                    | 定义工具领域异常类：`ToolError`（基类）、`ValidationError`、`InvalidArgumentError`                                                                            | 异常→响应的格式化         |

测试模块：

| 模块     | 文件                              | 职责                                                                                       |
| ------ | ------------------------------- | ---------------------------------------------------------------------------------------- |
| 工具单测   | `tests/test_add.py`             | 直接调用 `add` handler 及 `registry.dispatch` 验证正常/异常分支                                       |
| 协议集成测试 | `tests/test_mcp_integration.py` | 以子进程方式拉起 `server.py`，通过官方 mcp client 完成 `initialize` / `tools/list` / `tools/call` 端到端验证 |

---

## 3. 模块间依赖关系

### 3.1 依赖方向（上→下，单向，无环）

```
server  ──►  registry  ──►  errors
                 ▲              ▲
                 │              │
              tools/add  ───────┘
                 │
                 ▼
              schemas
```

规则：

- `server` 只依赖 `registry` 与 `tools`（仅为触发 import 完成注册）。
- `registry` 只依赖 `errors` 与第三方 `jsonschema`、`mcp` 类型。
- `tools/*` 依赖 `registry`（装饰器）、`schemas`（schema 常量）、`errors`（抛异常）。
- `schemas`、`errors` 为叶子，不依赖任何内部模块。
- 严禁反向依赖（registry 不能 import tools）。

### 3.2 接口边界

**`registry` 对外接口**

```python
def tool(name: str, description: str, input_schema: dict) -> Callable: ...
def list_tools() -> list[ToolSpec]: ...
async def dispatch(name: str, arguments: dict) -> CallToolResult: ...
```

**工具函数签名约定**

```python
@tool(name="add", description="...", input_schema=ADD_INPUT_SCHEMA)
def add(a: float, b: float) -> str:  # 同步即可；返回字符串作为 text content
    ...
```

**`errors` 对外接口**

```python
class ToolError(Exception): ...
class ValidationError(ToolError): ...      # schema 校验失败
class InvalidArgumentError(ToolError): ...  # 业务级非法参数（如 NaN/Inf）
```

---

## 4. 数据流向

### 4.1 `tools/list` 时序

```
Agent ──tools/list──► server ──list_tools()──► registry
                                                  │
                       ◄──[{name, description, inputSchema}]──┘
       ◄──JSON-RPC response──
```

### 4.2 `tools/call` 正常路径

```
Agent ──tools/call{name,args}──► server
                                   │ dispatch(name, args)
                                   ▼
                                registry
                                   │ jsonschema.validate(args, schema)
                                   │ 通过
                                   ▼
                                tools.add(a, b)  → "8"
                                   │
              ◄──CallToolResult(content=[text], isError=false)──
```

### 4.3 `tools/call` 异常路径

```
Agent ──tools/call{...}──► server ──dispatch──► registry
                                                   │
                                                   │ validate 失败
                                                   │ → raise ValidationError("缺失参数 'b'")
                                                   ▼
                                              统一捕获 (except ToolError as e)
                                                   │
              ◄──CallToolResult(content=[text(e.message)], isError=true)──
```

进程不崩溃；未知异常（非 ToolError）同样被兜底捕获，转为 `isError=true` 并附通用错误文案。

---

## 5. 关键技术决策与理由

| #   | 决策                          | 理由                                     | 备选与否决原因                                                   |
| --- | --------------------------- | -------------------------------------- | --------------------------------------------------------- |
| D1  | 分层架构（入口/注册/工具/基础设施）         | 后续添加工具只需新增 `tools/xxx.py`，零侵入；职责清晰可单测  | 单文件方案易膨胀；过度分层（service/dao 等）对 MVP 浪费                      |
| D2  | `@tool` 装饰器自动注册             | 工具元数据与实现共置，新增工具门槛最低                    | 手动注册易遗漏；包扫描隐式行为难调试                                        |
| D3  | jsonschema 中心化校验放在 registry | 所有工具一致行为；工具函数体只关注业务；便于统一错误转换           | SDK 自带校验能力不可控；工具自校验重复代码                                   |
| D4  | 错误用异常类 + registry 统一捕获      | 工具代码可读性最高（直接 raise）；错误响应格式集中维护         | Result 元组冗长；工具自构响应分散                                      |
| D5  | 选 `jsonschema` 库            | 主流、轻量、与 MCP 规范同源                       | pydantic 依赖偏重；手写校验覆盖 NaN/Infinity/additionalProperties 麻烦 |
| D6  | stdio + 单进程异步               | 需求 FR-2 明确；CodeMaker 默认拉起方式            | SSE/HTTP 需暴露端口，超出 MVP                                     |
| D7  | 仅 stderr 保留通道、当前不写日志        | 需求明确"无日志"；stdio 下 stdout 不可污染          | 写文件日志非 MVP 需要                                             |
| D8  | 集成测试用子进程 + 官方 mcp client    | 真实覆盖 stdio 握手与协议帧，符合 FR-2/FR-3/FR-4 验收 | 仅 mock 协议层覆盖度不够                                           |

---

## 6. 目录结构（落地预览）

```
CodeSense_V1/
├── pyproject.toml
├── doc/
│   ├── stack.md
│   ├── requirement.md
│   └── design/
│       └── overview.md         ← 本文件
├── src/
│   └── codesense_v1/
│       ├── __init__.py
│       ├── server.py           ← L1
│       ├── registry.py         ← L2
│       ├── schemas.py          ← L4
│       ├── errors.py           ← L4
│       └── tools/
│           ├── __init__.py     ← import add 触发注册
│           └── add.py          ← L3
└── tests/
    ├── test_add.py
    └── test_mcp_integration.py
```

---

## 7. 待确认事项（请逐条 review）

1. 分层架构 4 层（入口/注册/工具/基础设施）是否符合预期？ 用户回答：符合预期
2. 装饰器签名 `@tool(name, description, input_schema)` 是否接受？ 用户回答：接受
3. 工具函数返回 `str`（registry 包装为 text content）是否 OK？还是希望工具返回原生数值由 registry 转字符串？用户回答：前者
4. 错误异常类划分 `ToolError / ValidationError / InvalidArgumentError` 三个是否够用？用户回答：够用
5. 目录结构与文件命名是否需要调整？用户回答：不需要

**确认无误后，再进入详细设计/编码阶段。**
