from __future__ import annotations

import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

pytestmark = pytest.mark.asyncio(loop_scope="module")


def first_text(result: CallToolResult) -> str:
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


def _params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "codesense_v1.server"],
    )


# ---------------------------------------------------------------------------
# FR-2: initialize 握手
# ---------------------------------------------------------------------------


async def test_initialize() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            assert s is not None


# ---------------------------------------------------------------------------
# FR-3: tools/list
# ---------------------------------------------------------------------------


async def test_list_tools() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            response = await s.list_tools()
            tools = response.tools
            tool_names = {t.name for t in tools}
            assert "add" in tool_names
            assert "explore_module" in tool_names
            add_tool = next(t for t in tools if t.name == "add")
            schema = add_tool.inputSchema
            assert "a" in schema.get("required", [])
            assert "b" in schema.get("required", [])
            assert schema["properties"]["a"]["type"] == "number"
            assert schema["properties"]["b"]["type"] == "number"


# ---------------------------------------------------------------------------
# FR-4: tools/call 正常路径
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (3, 5, "8"),
        (-1, 1, "0"),
        (1.5, 2.5, "4.0"),
    ],
)
async def test_call_add_normal(a: float, b: float, expected: str) -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("add", {"a": a, "b": b})
            assert result.isError is False
            assert first_text(result) == expected


# ---------------------------------------------------------------------------
# FR-5: tools/call 异常路径
# ---------------------------------------------------------------------------


async def test_call_add_missing_arg() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("add", {"a": 1})
            assert result.isError is True
            text = first_text(result)
            assert "缺失必填参数" in text
            assert "'b'" in text


async def test_call_add_type_error() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("add", {"a": "x", "b": 1})
            assert result.isError is True
            text = first_text(result)
            assert "期望 number" in text


async def test_call_add_extra_arg() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("add", {"a": 1, "b": 2, "c": 3})
            assert result.isError is True
            text = first_text(result)
            assert "不允许的多余参数" in text
            assert "'c'" in text


# ---------------------------------------------------------------------------
# FR-1 + FR-5: 异常后进程仍存活
# ---------------------------------------------------------------------------


async def test_process_alive_after_errors() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            await s.call_tool("add", {"a": 1})
            await s.call_tool("add", {"a": "x", "b": 1})
            await s.call_tool("add", {"a": 1, "b": 2, "c": 3})

            result = await s.call_tool("add", {"a": 1, "b": 1})
            assert result.isError is False
            assert first_text(result) == "2"
