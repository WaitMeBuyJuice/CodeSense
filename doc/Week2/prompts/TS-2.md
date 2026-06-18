# TS-2: 实现 tests/test_add.py

## 任务背景

`src/codesense_v1/tools/add.py`（T-1）+ `src/codesense_v1/tools/__init__.py`（T-2）已完成。需要单元测试覆盖 `add` 工具的正常路径与异常路径，包括：

- 直接调用 `add` handler 函数
- 通过 `registry.dispatch("add", {...})` 间接调用

### 被测接口

```python
# codesense_v1.tools.add
@tool(name="add", description="计算两个数的和并返回字符串结果。", input_schema=ADD_INPUT_SCHEMA)
def add(a: float, b: float) -> str: ...
```

行为：
- NaN / Infinity 自检 → `raise InvalidArgumentError("参数错误：'<name>' 不能为 NaN")` 或 `"... 不能为 Infinity"`（按 a → b 顺序）
- 结果非有限 → `raise InvalidArgumentError("参数错误：结果溢出或非有限数")`
- 正常 → `return str(a + b)`

注册 schema：
```python
{
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "加数 a"},
        "b": {"type": "number", "description": "加数 b"},
    },
    "required": ["a", "b"],
    "additionalProperties": False,
}
```

`dispatch` 文案规约（参考 R-1）：
- 缺失必填 → `"参数错误：缺失必填参数 'b'"`
- 类型错 → `"参数错误：'a' 期望 number，收到 str"`
- 多余参数 → `"参数错误：不允许的多余参数 'c'"`

### pytest 配置

- `asyncio_mode = "auto"`、`testpaths = ["tests"]`、`pythonpath = ["src"]`

---

## 实现目标

为 `add` 工具编写完整单元测试，覆盖直接调用与经 dispatch 调用两种路径。

---

## 需要实现的文件

- `tests/test_add.py`

---

## 测试用例要求

### 模块顶部 import

```python
import math
import pytest
from codesense_v1 import tools  # noqa: F401 — 触发 add 注册
from codesense_v1 import registry
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.tools.add import add
```

**注意**：不要替换 `registry._REGISTRY`（与 TS-1 不同），本任务依赖真实注册的 `add` 工具供 `dispatch` 调用。

### 直接调用 handler

1. `add(3, 5) == "8"`
2. `add(-1, 1) == "0"`
3. `add(1.5, 2.5) == "4.0"`
4. `add(3, 5.0) == "8.0"`
5. `add(float('nan'), 1)` → `pytest.raises(InvalidArgumentError)`，捕获后断言 `exc.message == "参数错误：'a' 不能为 NaN"`
6. `add(1, float('nan'))` → 断言 `exc.message == "参数错误：'b' 不能为 NaN"`
7. `add(float('inf'), 1)` → `exc.message == "参数错误：'a' 不能为 Infinity"`
8. `add(1, float('-inf'))` → `exc.message == "参数错误：'b' 不能为 Infinity"`（`math.isinf(-inf)` 为 True）
9. 结果溢出：`add(1e308, 1e308)` → `exc.message == "参数错误：结果溢出或非有限数"`

### 经 registry.dispatch 调用（async 测试）

10. **正常路径**：`await registry.dispatch("add", {"a": 3, "b": 5})` → `isError is False`，`content[0].text == "8"`，`content[0].type == "text"`
11. `await registry.dispatch("add", {"a": 1.5, "b": 2.5})` → `content[0].text == "4.0"`，`isError is False`
12. **缺失 b**：`await registry.dispatch("add", {"a": 1})` → `isError is True`，`content[0].text == "参数错误：缺失必填参数 'b'"`
13. **类型非法**：`await registry.dispatch("add", {"a": "x", "b": 1})` → `isError is True`，`content[0].text == "参数错误：'a' 期望 number，收到 str"`
14. **多余参数**：`await registry.dispatch("add", {"a": 1, "b": 2, "c": 3})` → `isError is True`，`content[0].text == "参数错误：不允许的多余参数 'c'"`
15. **业务异常透传**（dispatch 路径下 NaN）：`await registry.dispatch("add", {"a": float('nan'), "b": 1})` → `isError is True`，`content[0].text == "参数错误：'a' 不能为 NaN"`

---

## 验收标准

- `uv run pytest tests/test_add.py -v` 全部通过
- `uv run mypy --strict tests/test_add.py` 零错误
- `uv run ruff check tests/test_add.py` 零警告
- 全部测试函数带完整类型注解（返回 `-> None`）

---

## 范围约束

- **仅** 创建 `tests/test_add.py`
- 严禁修改 `src/` 下任何文件、`pyproject.toml`、其他 `tests/*.py`
