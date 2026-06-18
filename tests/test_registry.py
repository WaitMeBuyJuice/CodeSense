from __future__ import annotations

import pytest
from mcp.types import CallToolResult, TextContent

from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import ToolSpec, dispatch, list_tools, tool
from codesense_v1.registry import registry as _registry_impl

# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

_SIMPLE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "a": {"type": "number"},
        "b": {"type": "number"},
    },
    "required": ["a", "b"],
    "additionalProperties": False,
}

_EMPTY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def first_text(result: CallToolResult) -> str:
    """取 content[0] 的 text，断言类型为 TextContent。"""
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


# ---------------------------------------------------------------------------
# 隔离 fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_registry_impl, "_REGISTRY", {})


# ---------------------------------------------------------------------------
# 装饰器
# ---------------------------------------------------------------------------


def test_tool_decorator_registers_spec() -> None:
    @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
    def handler() -> str:
        return "ok"

    spec = _registry_impl._REGISTRY["t"]
    assert isinstance(spec, ToolSpec)
    assert spec.name == "t"
    assert spec.description == "d"
    assert spec.input_schema is _EMPTY_SCHEMA
    assert spec.handler is handler


def test_tool_decorator_returns_original_function() -> None:
    @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
    def handler() -> str:
        return "original"

    assert handler() == "original"


def test_tool_decorator_duplicate_raises_runtime_error() -> None:
    @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
    def h1() -> str:
        return "h1"

    with pytest.raises(RuntimeError, match="tool 't' already registered"):

        @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
        def h2() -> str:
            return "h2"


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


def test_list_tools_returns_registered_tool() -> None:
    import mcp.types as mcp_types

    @tool(name="t", description="desc", input_schema=_EMPTY_SCHEMA)
    def handler() -> str:
        return "ok"

    tools = list_tools()
    assert len(tools) == 1
    t = tools[0]
    assert isinstance(t, mcp_types.Tool)
    assert t.name == "t"
    assert t.description == "desc"


# ---------------------------------------------------------------------------
# dispatch — 未知工具
# ---------------------------------------------------------------------------


async def test_dispatch_unknown_tool() -> None:
    result = await dispatch("nope", {})
    assert result.isError is True
    text = first_text(result)
    assert "未知工具" in text
    assert "'nope'" in text


# ---------------------------------------------------------------------------
# dispatch — schema 校验失败
# ---------------------------------------------------------------------------


async def test_dispatch_missing_required_field() -> None:
    @tool(name="t", description="d", input_schema=_SIMPLE_SCHEMA)
    def handler(a: float, b: float) -> str:
        return str(a + b)

    result = await dispatch("t", {"a": 1})
    assert result.isError is True
    assert first_text(result) == "参数错误：缺失必填参数 'b'"


async def test_dispatch_wrong_type() -> None:
    @tool(name="t", description="d", input_schema=_SIMPLE_SCHEMA)
    def handler(a: float, b: float) -> str:
        return str(a + b)

    result = await dispatch("t", {"a": "x", "b": 1})
    assert result.isError is True
    text = first_text(result)
    assert "参数错误" in text
    assert "'a'" in text
    assert "number" in text
    assert "str" in text


async def test_dispatch_extra_property() -> None:
    @tool(name="t", description="d", input_schema=_SIMPLE_SCHEMA)
    def handler(a: float, b: float) -> str:
        return str(a + b)

    result = await dispatch("t", {"a": 1, "b": 2, "c": 3})
    assert result.isError is True
    assert first_text(result) == "参数错误：不允许的多余参数 'c'"


# ---------------------------------------------------------------------------
# dispatch — 正常路径（同步 & 异步 handler）
# ---------------------------------------------------------------------------


async def test_dispatch_sync_handler() -> None:
    @tool(name="t", description="d", input_schema=_SIMPLE_SCHEMA)
    def handler(a: float, b: float) -> str:
        return str(a + b)

    result = await dispatch("t", {"a": 1, "b": 2})
    assert result.isError is False
    assert first_text(result) == "3"


async def test_dispatch_async_handler() -> None:
    @tool(name="t", description="d", input_schema=_SIMPLE_SCHEMA)
    async def handler(a: float, b: float) -> str:
        return str(a + b)

    result = await dispatch("t", {"a": 1.5, "b": 2.5})
    assert result.isError is False
    assert first_text(result) == "4.0"


# ---------------------------------------------------------------------------
# dispatch — 异常路径
# ---------------------------------------------------------------------------


async def test_dispatch_handler_raises_tool_error() -> None:
    @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
    def handler() -> str:
        raise InvalidArgumentError("参数错误：自定义文案")

    result = await dispatch("t", {})
    assert result.isError is True
    assert first_text(result) == "参数错误：自定义文案"


async def test_dispatch_handler_raises_unknown_exception() -> None:
    @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
    def handler() -> str:
        raise ZeroDivisionError("internal")

    result = await dispatch("t", {})
    assert result.isError is True
    text = first_text(result)
    assert text == "内部错误：ZeroDivisionError"
    assert "internal" not in text


# ---------------------------------------------------------------------------
# 不变量：任何路径 content 长度 >= 1
# ---------------------------------------------------------------------------


async def test_dispatch_invariant_content_not_empty_unknown() -> None:
    result = await dispatch("no_such_tool", {})
    assert isinstance(result, CallToolResult)
    assert len(result.content) >= 1


async def test_dispatch_invariant_content_not_empty_error() -> None:
    @tool(name="t", description="d", input_schema=_EMPTY_SCHEMA)
    def handler() -> str:
        raise RuntimeError("boom")

    result = await dispatch("t", {})
    assert isinstance(result, CallToolResult)
    assert len(result.content) >= 1
