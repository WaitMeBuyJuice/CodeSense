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
            tool_names = {t.name for t in response.tools}
            assert "project_map" in tool_names
            assert "explore_module" in tool_names
            assert "submit_project_map" in tool_names
            assert "save_module_summary" in tool_names


# ---------------------------------------------------------------------------
# FR-4: tools/call 正常路径（project_map 无环境变量时返回错误提示而非异常）
# ---------------------------------------------------------------------------


async def test_call_project_map_no_env() -> None:
    """project_map without env var returns an error description string (isError=False)."""
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("project_map", {})
            assert result.isError is False
            assert "project_map" in first_text(result) or "CODESENSE_PROJECT_ROOT" in first_text(result)


# ---------------------------------------------------------------------------
# FR-5: tools/call 异常路径（explore_module 参数校验）
# ---------------------------------------------------------------------------


async def test_call_explore_module_missing_arg() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("explore_module", {})
            assert result.isError is True
            text = first_text(result)
            assert "缺失必填参数" in text
            assert "'module_name'" in text


async def test_call_explore_module_type_error() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("explore_module", {"module_name": 123})
            assert result.isError is True
            text = first_text(result)
            assert "期望 string" in text


async def test_call_explore_module_extra_arg() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            result = await s.call_tool("explore_module", {"module_name": "缓存层", "extra": 1})
            assert result.isError is True
            text = first_text(result)
            assert "不允许的多余参数" in text
            assert "'extra'" in text


# ---------------------------------------------------------------------------
# FR-1 + FR-5: 异常后进程仍存活
# ---------------------------------------------------------------------------


async def test_process_alive_after_errors() -> None:
    async with stdio_client(_params()) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            await s.call_tool("explore_module", {})
            await s.call_tool("explore_module", {"module_name": 123})
            await s.call_tool("explore_module", {"module_name": "缓存层", "extra": 1})

            result = await s.call_tool("project_map", {})
            assert result.isError is False
