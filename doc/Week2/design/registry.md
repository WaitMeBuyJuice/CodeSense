# 详细设计 - registry 模块

> 路径：`src/codesense_v1/registry.py`  
> 层级：L2 注册/分发  
> 概要设计参考：`doc/design/overview.md` §2、§3.2、§4、§5 D2~D5

---

## 1. 模块功能说明

承担两件事：
1. **注册**：提供 `@tool` 装饰器，把每个工具的 (name, description, input_schema, handler) 收集到全局表 `_REGISTRY`。
2. **分发**：提供 `list_tools()` 与 `dispatch()` 两个对外函数，被 L1 入口层 `server` 直接对接到 mcp SDK 的协议回调。

`dispatch` 内部固定流程：**取 spec → jsonschema 校验参数 → 调用 handler → 结果包装为 `CallToolResult` → 异常统一转换**。

返回类型完全贴合官方 `mcp.types`（决策 D-extra），server 层无需二次转换。

---

## 2. 对外暴露的接口签名

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Awaitable, Callable, Final, Union

from mcp.types import Tool, TextContent, CallToolResult

ToolHandler = Callable[..., Union[str, Awaitable[str]]]
"""工具函数签名：接收 schema 中声明的关键字参数，返回字符串（同步或异步均可）。"""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: ToolHandler


def tool(
    name: str,
    description: str,
    input_schema: dict,
) -> Callable[[ToolHandler], ToolHandler]:
    """装饰器：将被装饰函数注册为 MCP 工具。

    重复注册同名工具抛出 RuntimeError（启动期错误，非运行期）。
    被装饰函数原样返回，不做包装，便于单元测试直接调用。
    """


def list_tools() -> list[Tool]:
    """返回所有已注册工具的 mcp.types.Tool 列表（用于响应 tools/list）。"""


async def dispatch(name: str, arguments: dict) -> CallToolResult:
    """调用名为 name 的工具，返回 mcp.types.CallToolResult。
    永不抛异常：所有错误转为 isError=True 的结果。
    """
```

类型注解要点：
- `ToolHandler` 用 `Callable[..., Union[str, Awaitable[str]]]`，允许同步或 `async def`。
- `dispatch` 自身为 `async`，便于 server 层直接 await，且兼容异步 handler。
- 返回类型严格使用 `mcp.types.Tool` / `CallToolResult`。

---

## 3. 核心数据结构定义

```python
_REGISTRY: Final[dict[str, ToolSpec]] = {}
```

- 模块级单例字典，键为工具名（唯一）。
- 进程启动时由各 `tools/*.py` 在 import 阶段填充；之后只读。
- 不提供清空接口（测试若需重置请用 monkeypatch 替换字典）。

`ToolSpec` 选择 `frozen=True` 的 dataclass，防止注册后被意外修改。

---

## 4. 错误码与异常处理规范

### 4.1 注册期（`@tool`）
- 同名重复注册 → `raise RuntimeError(f"tool '{name}' already registered")`。属于程序员错误，启动期暴露，不进入运行期。

### 4.2 分发期（`dispatch`）—— 永不向外抛异常

| 触发条件 | 处理 | 响应 |
|----------|------|------|
| `name` 不在 `_REGISTRY` | 不抛，直接构造错误响应 | `isError=True`，文案 `"未知工具：'<name>'"` |
| jsonschema 校验失败 | 内部 `raise ValidationError(...)`，本函数 except 转换 | `isError=True`，文案见下 |
| handler 内 `raise ToolError` / 其子类 | except 捕获 | `isError=True`，文案 = `e.message` |
| handler 内任意其他异常（含 TypeError、ZeroDivisionError、未知） | 兜底 except | `isError=True`，文案 `"内部错误：<exc_type 名字>"`；**不**泄漏堆栈与 repr |

### 4.3 jsonschema 错误文案规范

将 `jsonschema.ValidationError` 翻译为 `ValidationError`，按错误类型生成人类可读文案：

| jsonschema validator 类型 | 输出文案模板 |
|---------------------------|--------------|
| `required` | `参数错误：缺失必填参数 '<field>'` |
| `type` | `参数错误：'<field>' 期望 <expected>，收到 <actual>` |
| `additionalProperties` | `参数错误：不允许的多余参数 '<field>'` |
| 其他 | `参数错误：<jsonschema 原始 message>` |

`<field>` 通过 `error.absolute_path[-1]` 提取；`additionalProperties` 场景从 `error.message` 解析或从 `error.validator_value` 与 `instance` keys 差集推导。

### 4.4 不变量
- `dispatch` 任何路径返回的 `CallToolResult` 必满足 `len(result.content) >= 1`，至少 1 个 `TextContent`。
- 进程不因 dispatch 而退出（FR-1、FR-5 验收依赖此点）。

---

## 5. 关键算法 / 业务逻辑

### 5.1 装饰器实现要点
```text
def tool(name, description, input_schema):
    def deco(fn):
        if name in _REGISTRY:
            raise RuntimeError(...)
        _REGISTRY[name] = ToolSpec(name, description, input_schema, fn)
        return fn
    return deco
```

### 5.2 dispatch 主流程伪代码
```text
async def dispatch(name, arguments):
    spec = _REGISTRY.get(name)
    if spec is None:
        return _error(f"未知工具：'{name}'")

    try:
        _validate(arguments, spec.input_schema)   # 内部 raise ValidationError
    except ValidationError as e:
        return _error(e.message)

    try:
        result = spec.handler(**arguments)
        if inspect.isawaitable(result):
            result = await result
    except ToolError as e:
        return _error(e.message)
    except Exception as e:
        return _error(f"内部错误：{type(e).__name__}")

    return CallToolResult(
        content=[TextContent(type="text", text=str(result))],
        isError=False,
    )

def _error(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=msg)],
        isError=True,
    )
```

### 5.3 jsonschema 校验器选择
- 使用 `jsonschema.Draft202012Validator(schema)`，与 schemas 模块声明一致。
- 取第一个错误（`next(validator.iter_errors(instance), None)`）即可——错误响应只需一条清晰提示。

---

## 6. 与其他模块的交互契约

```
server   ──► registry  : await dispatch(name, args); list_tools()
tools/*  ──► registry  : @tool(...)
registry ──► errors    : except ToolError; raise ValidationError
registry ──► schemas   : 不直接 import；通过 ToolSpec.input_schema 间接持有
registry ──► mcp.types : 构造 Tool / TextContent / CallToolResult
registry ──► jsonschema: Draft202012Validator
```

约束：
- **严禁** `registry` import `tools/*`（保持依赖单向）。
- handler 必须返回 `str` 或 `Awaitable[str]`；返回其他类型由 `str(result)` 兜底转换，但不推荐工具依赖此行为。
- `dispatch` 必须是 `async`；handler 可同步可异步。
