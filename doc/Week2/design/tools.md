# 详细设计 - tools 模块（含 add 工具）

> 路径：`src/codesense_v1/tools/__init__.py`、`src/codesense_v1/tools/add.py`  
> 层级：L3 工具  
> 概要设计参考：`doc/design/overview.md` §2、§3、§5 D1~D2

---

## 1. 模块功能说明

`tools` 是工具实现的"插件目录"：
- 每个 `.py` 文件实现 1 个工具，通过 `@tool` 装饰器自注册到 `registry`。
- `__init__.py` 集中 `import` 所有工具子模块，确保 `codesense_v1.tools` 一旦被导入，所有工具就绪。
- MVP 阶段只有 `add`。

设计原则：
- 工具体内只关心业务逻辑，**不**触碰 MCP 类型、JSON 协议、传输细节。
- 入参用关键字参数接收，与 schema `properties` 名称一一对应。
- 输出必须为 `str`（registry 包装为 `TextContent`）。

---

## 2. 对外暴露的接口签名

### 2.1 `tools/__init__.py`

```python
"""导入所有工具子模块以触发 @tool 注册。"""

from . import add  # noqa: F401

__all__: list[str] = []
```

无导出符号；副作用即注册。

### 2.2 `tools/add.py`

```python
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.schemas import ADD_INPUT_SCHEMA


@tool(
    name="add",
    description="计算两个数的和并返回字符串结果。",
    input_schema=ADD_INPUT_SCHEMA,
)
def add(a: float, b: float) -> str: ...
```

类型注解要点：
- 参数 `a: float`、`b: float`（Python `int` 是 `float` 兼容值；JSON `number` 涵盖二者）。
- 返回 `str`，registry 直接包装为 `TextContent.text`。
- 同步函数（无 IO，不需要 async）。

---

## 3. 核心数据结构定义

无独立结构。仅依赖：
- `ADD_INPUT_SCHEMA`（来自 schemas）
- `InvalidArgumentError`（来自 errors）
- `tool`（来自 registry）

---

## 4. 错误码与异常处理规范

`add` 内部只处理 schema 校验**之后**仍可能发生的语义错误。schema 已保证：
- 必填齐全
- 类型为 number
- 无多余参数

因此 `add` 仍需自查：

| 条件 | 抛出 | 文案 |
|------|------|------|
| `math.isnan(a)` 或 `math.isnan(b)` | `InvalidArgumentError` | `"参数错误：'a' 不能为 NaN"` / `"参数错误：'b' 不能为 NaN"`（取第一个不合法的参数报错） |
| `math.isinf(a)` 或 `math.isinf(b)` | `InvalidArgumentError` | `"参数错误：'a' 不能为 Infinity"` / `"参数错误：'b' 不能为 Infinity"` |
| 结果非有限（`a + b` 溢出为 inf 或 nan） | `InvalidArgumentError` | `"参数错误：结果溢出或非有限数"` |

工具内**不**捕获异常自包装为 `CallToolResult`，由 `registry` 统一处理。

> 注：JSON 规范本身不支持 NaN/Infinity，但若客户端通过非严格 JSON 注入（或未来扩展），上述自检仍有价值，符合 FR-5 "完整错误处理" 要求。

---

## 5. 关键算法 / 业务逻辑

```text
def add(a, b):
    for name, v in (("a", a), ("b", b)):
        if math.isnan(v):
            raise InvalidArgumentError(f"参数错误：'{name}' 不能为 NaN")
        if math.isinf(v):
            raise InvalidArgumentError(f"参数错误：'{name}' 不能为 Infinity")

    result = a + b
    if not math.isfinite(result):
        raise InvalidArgumentError("参数错误：结果溢出或非有限数")

    return str(result)
```

返回值格式约定（保留浮点的尾零，区分整数与浮点）：
- `add(3, 5)` → `"8"`（两个 int 相加，结果 int，输出 `"8"`）
- `add(1.5, 2.5)` → `"4.0"`（任一为浮点则结果为浮点，输出 `"4.0"`）
- `add(1.5, 1.0)` → `"2.5"`
- `add(3, 5.0)` → `"8.0"`

实现细节：直接 `return str(a + b)` 即可——Python 原生 `str(float)` 自带 `.0` 后缀，`str(int)` 不带。

---

## 6. 与其他模块的交互契约

```
tools/add  ──► registry  : @tool 装饰器注册
tools/add  ──► schemas   : 引用 ADD_INPUT_SCHEMA
tools/add  ──► errors    : raise InvalidArgumentError
tools/add  ──► mcp.types : 不直接引用
tools/__init__ ──► tools/add : import 触发注册
```

约束：
- 严禁 import `server`（避免循环）。
- 严禁 raise `ValidationError`（专属 registry 校验阶段）。
- 每个工具一个文件，文件名 == 工具名小写。
- 新增工具：1）在 schemas 增 schema 常量；2）新建 `tools/<name>.py`；3）`tools/__init__.py` 加一行 `from . import <name>`。
