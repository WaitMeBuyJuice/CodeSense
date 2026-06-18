import math

from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.schemas import ADD_INPUT_SCHEMA


@tool(
    name="add",
    description="计算两个数的和并返回字符串结果。",
    input_schema=ADD_INPUT_SCHEMA,
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
