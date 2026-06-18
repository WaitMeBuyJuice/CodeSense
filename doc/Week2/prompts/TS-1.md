# TS-1: 实现 tests/test_registry.py

## 任务背景

`src/codesense_v1/registry.py`（R-1 已完成）提供注册与分发能力。需要单独的单元测试覆盖：装饰器、`list_tools`、`dispatch` 各路径。

### 被测模块已实现的接口

```python
# codesense_v1.errors
class ToolError(Exception):
    def __init__(self, message: str) -> None: ...
    @property
    def message(self) -> str: ...
class ValidationError(ToolError): ...
class InvalidArgumentError(ToolError): ...

# codesense_v1.registry
ToolHandler = Callable[..., Union[str, Awaitable[str]]]

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: ToolHandler

_REGISTRY: Final[dict[str, ToolSpec]] = {}

def tool(name: str, description: str, input_schema: dict) -> Callable[[ToolHandler], ToolHandler]: ...
def list_tools() -> list[mcp.types.Tool]: ...
async def dispatch(name: str, arguments: dict) -> mcp.types.CallToolResult: ...
```

### 关键行为（被测）

- 重复注册同名工具 → `RuntimeError("tool '<name>' already registered")`
- `dispatch` 永不抛异常，任何错误转 `isError=True`
- 文案翻译表：

| jsonschema validator | 文案模板 |
|----------------------|----------|
| `required` | `参数错误：缺失必填参数 '<field>'` |
| `type` | `参数错误：'<field>' 期望 <expected>，收到 <actual>` |
| `additionalProperties` | `参数错误：不允许的多余参数 '<field>'` |

- 未知工具：`"未知工具：'<name>'"`
- handler 内 `raise ToolError`：文案 = `e.message`
- handler 内任意其他异常：文案 = `"内部错误：<exc_type 名字>"`
- 任何路径 `len(result.content) >= 1`

### pytest 配置（已声明）

- `asyncio_mode = "auto"`（无需 `@pytest.mark.asyncio` 装饰）
- `testpaths = ["tests"]`、`pythonpath = ["src"]`

---

## 实现目标

为 `registry` 编写完整单元测试，覆盖正常路径与全部异常路径，测试隔离不污染全局 `_REGISTRY`。

---

## 需要实现的文件

- `tests/test_registry.py`

---

## 测试用例要求

### 测试隔离

每个测试函数前用 fixture（或 `monkeypatch`）替换 `codesense_v1.registry._REGISTRY` 为新空 dict，避免相互污染。示例：

```python
import pytest
from codesense_v1 import registry

@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_REGISTRY", {})
```

### 用例列表（每条至少 1 个 test 函数）

1. **装饰器注册成功**：用 `@registry.tool(name="t", description="d", input_schema={"type":"object","properties":{},"additionalProperties":False})` 装饰一个函数，断言 `_REGISTRY["t"]` 是 `ToolSpec`，字段匹配，且装饰器返回原函数（可直接调用）

2. **装饰器重复注册抛 RuntimeError**：连续两次 `@tool(name="t", ...)`，第二次抛 `RuntimeError`，错误信息含 `"tool 't' already registered"`

3. **list_tools 返回正确结构**：注册 1 个工具后，`list_tools()` 返回 `list`，长度 1；元素是 `mcp.types.Tool`，`name/description/inputSchema` 与注册时一致

4. **dispatch 未知工具**：`await dispatch("nope", {})` → `isError=True`，`content[0].text` 含 `"未知工具"` 与 `"'nope'"`

5. **dispatch 校验失败 - 缺失必填**：注册 schema `{"type":"object","properties":{"a":{"type":"number"},"b":{"type":"number"}},"required":["a","b"],"additionalProperties":False}` 的工具；调用 `dispatch("t", {"a": 1})` → `isError=True`，文案 = `"参数错误：缺失必填参数 'b'"`

6. **dispatch 校验失败 - 类型错**：同上 schema；调用 `dispatch("t", {"a": "x", "b": 1})` → `isError=True`，文案匹配 `"参数错误：'a' 期望 number，收到 str"`

7. **dispatch 校验失败 - 多余参数**：同上 schema；调用 `dispatch("t", {"a": 1, "b": 2, "c": 3})` → `isError=True`，文案 = `"参数错误：不允许的多余参数 'c'"`

8. **dispatch 同步 handler 正常路径**：注册 `def h(a, b): return str(a + b)`，调用 `dispatch("t", {"a": 1, "b": 2})` → `isError=False`，`content[0].text == "3"`

9. **dispatch 异步 handler 正常路径**：注册 `async def h(a, b): return str(a + b)`，调用 `dispatch("t", {"a": 1.5, "b": 2.5})` → `isError=False`，`content[0].text == "4.0"`

10. **dispatch handler 抛 ToolError**：注册 `def h(): raise InvalidArgumentError("参数错误：自定义文案")`，schema 为 `{"type":"object","properties":{},"additionalProperties":False}`，调用 `dispatch("t", {})` → `isError=True`，`content[0].text == "参数错误：自定义文案"`

11. **dispatch handler 抛未知异常**：注册 `def h(): raise ZeroDivisionError("internal")`，调用 `dispatch("t", {})` → `isError=True`，`content[0].text == "内部错误：ZeroDivisionError"`，不含 `"internal"` 或堆栈

12. **不变量**：上述每个用例最终断言 `isinstance(result, mcp.types.CallToolResult)` 且 `len(result.content) >= 1`

---

## 验收标准

- `uv run pytest tests/test_registry.py -v` 全部通过
- `uv run mypy --strict tests/test_registry.py` 零错误
- `uv run ruff check tests/test_registry.py` 零警告
- 全部测试函数与 fixture 带完整类型注解

---

## 范围约束

- **仅** 创建 `tests/test_registry.py`
- 严禁修改 `src/` 下任何文件、`pyproject.toml`、其他 `tests/*.py`
- 严禁全局污染 `_REGISTRY`
