import math
from typing import Final

from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool

_ADD_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "加数 a"},
        "b": {"type": "number", "description": "加数 b"},
    },
    "required": ["a", "b"],
    "additionalProperties": False,
}


@tool(
    name="add",
    description="计算两个数的和并返回字符串结果。",
    input_schema=_ADD_INPUT_SCHEMA,
)
def add(a: float, b: float) -> str:
    for param_name, v in (("a", a), ("b", b)):
        if math.isnan(v):
            raise InvalidArgumentError(f"参数错误：'{param_name}' 不能为 NaN")
        if math.isinf(v):
            raise InvalidArgumentError(f"参数错误：'{param_name}' 不能为 Infinity")

    result = a + b
    if not math.isfinite(result):
        raise InvalidArgumentError("参数错误：结果溢出或非有限数")

    return str(result)
