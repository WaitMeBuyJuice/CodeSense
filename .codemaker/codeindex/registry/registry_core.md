---
entity_names:
  constants:
    - name: ToolHandler
      value: "类型别名 Callable[..., str | Awaitable[str]]：工具 handler 可同步返回 str 或返回 awaitable（async handler）"
      source: src/codesense_v1/registry/registry.py
    - name: _REGISTRY
      value: "Final[dict[str, ToolSpec]] 全局单例：进程级工具注册表，import 期由 @tool 填充，运行期只读"
      source: src/codesense_v1/registry/registry.py
    - name: ToolSpec
      value: "frozen dataclass：字段 name/description/input_schema/handler，单个工具的完整元数据+实现"
      source: src/codesense_v1/registry/registry.py
retrieval_hints:
  - "正向疑问句：@tool 装饰器怎么注册工具？重复注册会怎样？"
  - "正向疑问句：dispatch 怎么校验参数？校验失败返回什么？"
  - "正向疑问句：工具 handler 抛 ToolError 和抛普通 Exception 分别怎么处理？"
  - "正向疑问句：_translate_jsonschema_error 翻译哪几种校验错误？"
  - "⚠️ 反向排除句：本模块是 CodeSense_V1 的工具注册分发层，不是 CodeGraph 的工具系统（CodeGraph 是独立 MCP Server）"
  - "架构归属句：新增工具用 @tool 装饰器注册到 _REGISTRY，参数校验逻辑放 dispatch 不放工具函数体"
  - "架构归属句：jsonschema 校验集中在 registry.dispatch，工具函数体只关注业务逻辑直接 raise ToolError"
  - "本模块也叫 L2 注册分发层 / registry 层"
architectural_role: "工具注册与分发层"
---

## 对外接口
本模块对外是 **@tool / list_tools / dispatch 三件套**，供 server 层回调委派 + tools 层注册。

| 接口 | 方向 | 关键说明 | 入口符号 |
|------|------|---------|---------|
| `tool(name, description, input_schema)` 装饰器 | 对 tools 层 | import 时注册到 `_REGISTRY`，重复注册抛 RuntimeError，原样返回 fn | `tool` |
| `list_tools() -> list[Tool]` | 对 server 层 | 输出所有已注册工具的 `mcp.types.Tool`（响应 tools/list） | `list_tools` |
| `dispatch(name, arguments) -> CallToolResult` | 对 server 层 | async：校验→调用→异常转 isError，永不抛异常 | `dispatch` |
| `ToolSpec` dataclass | 对 tools 层 | 工具元数据容器（name/description/input_schema/handler） | `ToolSpec` |
| `ToolHandler` 类型别名 | 对 tools 层 | `Callable[..., str | Awaitable[str]]`，handler 签名约定 | `ToolHandler` |

## 跨模块依赖
### 外部依赖
| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|---------|---------|-----------|
| `errors` | dispatch 捕获 `ToolError` 转 isError | `from codesense_v1.errors import ToolError` | extracted |
| `jsonschema` | dispatch 用 `Draft202012Validator` 校验参数 | `Draft202012Validator` | extracted |
| `mcp.types` | 输出 Tool/CallToolResult/TextContent | `Tool`, `CallToolResult`, `TextContent` | extracted |

### 反向调用方
| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `server` | `_list_tools` 回调调 list_tools；`_call_tool` 回调调 dispatch | `list_tools`, `dispatch` |
| `tools` | import 时执行 `@tool` 装饰器填充 `_REGISTRY` | `tool` |
| `tests` | 单测直接调 dispatch 验证正常/异常分支 | `dispatch` |

## 典型调用链
1. **注册链（import 期）：** tools 模块 import → `@tool(name,...)` 装饰器执行 ← 本模块入口 → `_REGISTRY[name]=ToolSpec`
2. **tools/list 链：** server._list_tools → `list_tools` ← 本模块入口 → 遍历 `_REGISTRY` 输出 `mcp.types.Tool`
3. **tools/call 正常链：** server._call_tool → `dispatch` ← 本模块入口 → `Draft202012Validator` 校验 → `spec.handler(**arguments)` → CallToolResult(isError=False)
4. **tools/call 异常链：** dispatch → 校验失败 `_translate_jsonschema_error` → `_error` → CallToolResult(isError=True)；或 handler 抛 `ToolError` → `_error(e.message)`；或抛未知 Exception → `_error(f"内部错误：{type(e).__name__}: {e}")`

## 实现约束清单
### 必须定义的常量/枚举
| 标识符 | 值 | 所在文件 | 说明 |
|--------|-----|---------|------|
| `ToolHandler` | `Callable[..., str \| Awaitable[str]]` | registry.py | handler 签名约定，支持同步/async |
| `_REGISTRY` | `Final[dict[str, ToolSpec]]` | registry.py | 进程级全局注册表，import 期填充运行期只读 |
| `ToolSpec` | frozen dataclass | registry.py | 字段 name/description/input_schema/handler |

### 必须实现的函数
| 函数名 | 所在文件 | 说明 |
|--------|---------|------|
| `tool` | registry.py | 装饰器：注册 ToolSpec，重复抛 RuntimeError，原样返回 fn |
| `list_tools` | registry.py | 输出 list[Tool]，响应 tools/list |
| `dispatch` | registry.py | async：校验+调用+异常转 isError，永不抛 |
| `_translate_jsonschema_error` | registry.py | 翻译 required/type/additionalProperties 错误为中文参数错误提示 |
| `_error` | registry.py | 构造 isError=True 的 CallToolResult |

### 设计决策
| 决策点 | 选定方案 | 外选方案 | 选定理由 |
|--------|---------|---------|---------|
| 注册方式 | `@tool` 装饰器 import 时自动注册 | 手动注册/包扫描 | 元数据与实现共置，新增工具零侵入；手动易遗漏，包扫描难调试 |
| 重复注册 | 抛 RuntimeError（启动期错误） | 静默覆盖 | 启动期暴露冲突，避免运行期不可预期行为 |
| 参数校验位置 | jsonschema 中心化放 dispatch | SDK 自带校验/工具自校验 | 所有工具一致行为；工具函数体只关注业务；SDK 校验不可控，工具自校验重复 |
| 校验库 | `jsonschema` Draft202012Validator | pydantic/手写 | 主流轻量，与 MCP 规范同源；pydantic 依赖偏重，手写覆盖 NaN/Infinity/additionalProperties 麻烦 |
| 错误处理 | 异常类 + dispatch 统一捕获 | Result 元组/工具自构响应 | 工具代码可读性最高（直接 raise）；错误响应格式集中维护 |
| handler 兼容 | `inspect.isawaitable` 判断同步/async | 仅支持 async | 同步工具写法简单，async 工具也支持 |
| 装饰器返回 | 原样返回 fn 不包装 | 返回包装函数 | 便于单元测试直接调用原 handler |
| dispatch 异常兜底 | 永不抛，未知异常转 `内部错误：<ExcType>: <msg>` | 向上抛 | 进程不崩溃，所有错误转 isError 响应 |

## 附：内置文档摘要
> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/overview.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

**职责边界（overview.md §2）：** 维护 ToolSpec 表；提供 `@tool(name, description, input_schema)` 装饰器；`list_tools()` 输出元数据；`dispatch(name, arguments)` 做 schema 校验、调用、异常→MCP 错误响应转换。不负责工具具体实现、错误类定义。

**接口边界（overview.md §3.2）：**
```python
def tool(name: str, description: str, input_schema: dict) -> Callable: ...
def list_tools() -> list[ToolSpec]: ...
async def dispatch(name: str, arguments: dict) -> CallToolResult: ...
```
工具函数签名约定：`@tool(...)` 装饰，同步返回 str（registry 包装为 text content）。

**依赖规则（overview.md §3.1）：** registry 只依赖 errors + 第三方 jsonschema/mcp 类型；严禁反向依赖（registry 不能 import tools）；schemas/errors 为叶子不依赖任何内部模块。

**数据流（overview.md §4）：**
- tools/list：Agent → server → registry.list_tools → 返回 `[{name, description, inputSchema}]`
- tools/call 正常：Agent → server → registry.dispatch → jsonschema 校验通过 → tools handler → CallToolResult(isError=false)
- tools/call 异常：dispatch 校验失败/handler 抛 ToolError → 统一捕获 → CallToolResult(isError=true)。进程不崩溃；未知异常同样兜底转 isError 附通用文案。

**关键决策（overview.md §5）：**
- D2 `@tool` 装饰器自动注册：工具元数据与实现共置，新增工具门槛最低
- D3 jsonschema 中心化校验放 registry：所有工具一致行为，工具函数体只关注业务，便于统一错误转换
- D4 错误用异常类 + registry 统一捕获：工具代码可读性最高（直接 raise），错误响应格式集中维护
- D5 选 jsonschema 库：主流轻量与 MCP 规范同源

**MCP SDK 陷阱（week5_handoff.md §5.3）：**
- `@server.call_tool` 必须加 `validate_input=False`：SDK 默认校验会拒绝自定义 schema，必须关闭 → 因此参数校验下沉到 registry.dispatch 用 jsonschema 自行实现
- `@server.list_tools()` 装饰器无类型注解需 `# type: ignore`（SDK 未导出 decorator 类型）
- `mcp` 版本锁定 1.27.2

> 📄 注：overview.md 设计稿中 `list_tools() -> list[ToolSpec]`，实际代码已演进为 `list_tools() -> list[Tool]`（直接输出 mcp.types.Tool 供 server 回调返回），以源码为准。
