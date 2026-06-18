# Prompt — SCH-W3-1：新增 `EXPLORE_MODULE_INPUT_SCHEMA`

## 任务背景

Week 3 新增 `explore_module` MCP Tool，需要在 `schemas.py` 中集中存放其 JSON Schema 常量（与现有 `ADD_INPUT_SCHEMA` 模式一致）。

现有 `schemas.py` 内容：
```python
from typing import Final

ADD_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "加数 a"},
        "b": {"type": "number", "description": "加数 b"},
    },
    "required": ["a", "b"],
    "additionalProperties": False,
}
```

## 实现目标

在 `schemas.py` 末尾追加 `EXPLORE_MODULE_INPUT_SCHEMA` 常量。

## 接口契约

```python
EXPLORE_MODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_path": {
            "type": "string",
            "description": "相对于项目根目录的模块目录路径，如 'src/auth'",
        }
    },
    "required": ["module_path"],
    "additionalProperties": False,
}
```

## 需要修改的文件

- `src/codesense_v1/schemas.py`（仅追加，不修改现有代码）

## 测试文件

无需新增独立测试文件。验证方式：
- 运行 `uv run pytest -q` 确认全量测试通过

## 验收标准

1. `EXPLORE_MODULE_INPUT_SCHEMA` 为 `Final[dict[str, object]]`
2. `"module_path"` 在 `required` 列表中
3. `"additionalProperties": False` 存在
4. `uv run ruff check src/codesense_v1/schemas.py` 零警告
5. `uv run mypy --strict src/codesense_v1/schemas.py` 零错误
6. `uv run pytest -q` 全部通过

## 约束

- 严禁修改 `schemas.py` 中现有的任何代码
- 不得修改其他任何文件
