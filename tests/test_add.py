from __future__ import annotations

import pytest
from mcp.types import CallToolResult, TextContent

from codesense_v1 import tools  # noqa: F401 — 触发 add 注册
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.tools.add import add

# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def first_text(result: CallToolResult) -> str:
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


# ---------------------------------------------------------------------------
# 直接调用 handler — 正常路径
# ---------------------------------------------------------------------------


def test_add_int_int() -> None:
    assert add(3, 5) == "8"


def test_add_negative() -> None:
    assert add(-1, 1) == "0"


def test_add_float_float() -> None:
    assert add(1.5, 2.5) == "4.0"


def test_add_int_float() -> None:
    assert add(3, 5.0) == "8.0"


# ---------------------------------------------------------------------------
# 直接调用 handler — NaN / Infinity 自检
# ---------------------------------------------------------------------------


def test_add_nan_a() -> None:
    with pytest.raises(InvalidArgumentError) as exc_info:
        add(float("nan"), 1)
    assert exc_info.value.message == "参数错误：'a' 不能为 NaN"


def test_add_nan_b() -> None:
    with pytest.raises(InvalidArgumentError) as exc_info:
        add(1, float("nan"))
    assert exc_info.value.message == "参数错误：'b' 不能为 NaN"


def test_add_inf_a() -> None:
    with pytest.raises(InvalidArgumentError) as exc_info:
        add(float("inf"), 1)
    assert exc_info.value.message == "参数错误：'a' 不能为 Infinity"


def test_add_neg_inf_b() -> None:
    with pytest.raises(InvalidArgumentError) as exc_info:
        add(1, float("-inf"))
    assert exc_info.value.message == "参数错误：'b' 不能为 Infinity"


def test_add_overflow() -> None:
    with pytest.raises(InvalidArgumentError) as exc_info:
        add(1e308, 1e308)
    assert "结果溢出" in exc_info.value.message


# ---------------------------------------------------------------------------
# 经 registry.dispatch 调用 — 正常路径
# ---------------------------------------------------------------------------


async def test_dispatch_add_normal() -> None:
    from codesense_v1.registry import dispatch

    result = await dispatch("add", {"a": 3, "b": 5})
    assert result.isError is False
    assert first_text(result) == "8"
    assert result.content[0].type == "text"


async def test_dispatch_add_float() -> None:
    from codesense_v1.registry import dispatch

    result = await dispatch("add", {"a": 1.5, "b": 2.5})
    assert result.isError is False
    assert first_text(result) == "4.0"


# ---------------------------------------------------------------------------
# 经 registry.dispatch 调用 — 校验失败
# ---------------------------------------------------------------------------


async def test_dispatch_add_missing_b() -> None:
    from codesense_v1.registry import dispatch

    result = await dispatch("add", {"a": 1})
    assert result.isError is True
    assert first_text(result) == "参数错误：缺失必填参数 'b'。请检查工具参数说明，补充必要参数后重新调用。"


async def test_dispatch_add_type_error() -> None:
    from codesense_v1.registry import dispatch

    result = await dispatch("add", {"a": "x", "b": 1})
    assert result.isError is True
    text = first_text(result)
    assert "期望 number" in text


async def test_dispatch_add_extra_arg() -> None:
    from codesense_v1.registry import dispatch

    result = await dispatch("add", {"a": 1, "b": 2, "c": 3})
    assert result.isError is True
    assert first_text(result) == "参数错误：不允许的多余参数 'c'，请移除该参数后重新调用。"


# ---------------------------------------------------------------------------
# 经 registry.dispatch 调用 — 业务异常透传
# ---------------------------------------------------------------------------


async def test_dispatch_add_nan_via_dispatch() -> None:
    from codesense_v1.registry import dispatch

    result = await dispatch("add", {"a": float("nan"), "b": 1})
    assert result.isError is True
    assert first_text(result) == "参数错误：'a' 不能为 NaN"
