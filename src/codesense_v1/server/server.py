from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Resource, Tool
from pydantic import AnyUrl

from codesense_v1 import registry
from codesense_v1 import tools as _tools  # noqa: F401 — 触发工具注册
from codesense_v1.resources import project_map as _pm

SERVER_NAME: str = "CodeSense"
SERVER_VERSION: str = "0.1.0"
SERVER_INSTRUCTIONS: str = """\
CodeSense provides architecture-level understanding built on top of CodeGraph \
(which indexes symbols and call relationships). Use CodeSense for the \
"what does this module do and how does it fit" questions; use CodeGraph for \
"who calls this function" questions.

Tools:
- project_map (Resource): Project-wide overview — module list, \
one-line descriptions, cross-module dependencies. Read this resource \
whenever you start on an unfamiliar codebase or need to locate \
which module owns a feature.
- explore_module (Tool): Module-level deep dive — public interface, internal files, \
dependency modules. Call this before modifying any module, or when you need to \
understand a module's boundaries and contracts.

When to use what:
- Starting a new task or unfamiliar with the codebase → read project_map resource first
- About to modify a module → call explore_module for that module first
- Need a specific symbol or call chain → use CodeGraph MCP tools \
(symbol lookup, callers, call chains)
- Need exact code text → use grep / read_file

Prefer high-to-low abstraction: project_map → explore_module → codegraph → grep/read_file. \
Avoid jumping straight to grep for architecture questions — but direct grep/read_file is \
fine when you already know the exact symbol or file.\
"""


def build_server() -> Server:
    """构造并返回已绑定回调的 mcp Server 实例。便于测试直接拿到 Server 注入 mock transport。"""
    server: Server = Server(
        name=SERVER_NAME, version=SERVER_VERSION, instructions=SERVER_INSTRUCTIONS
    )

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return registry.list_tools()

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, object]) -> CallToolResult:
        return await registry.dispatch(name, arguments)

    @server.list_resources()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_resources() -> list[Resource]:
        return [
            Resource(
                uri=AnyUrl(_pm.RESOURCE_URI),
                name=_pm.RESOURCE_NAME,
                description=_pm.RESOURCE_DESCRIPTION,
                mimeType=_pm.RESOURCE_MIME_TYPE,
            )
        ]

    @server.read_resource()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        content = await _pm.read_project_map()
        return [ReadResourceContents(content=content, mime_type=_pm.RESOURCE_MIME_TYPE)]

    return server


async def run_stdio() -> None:
    """启动 stdio 传输并阻塞运行，直到 stdin 关闭或收到关闭信号。"""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """同步入口：asyncio.run(run_stdio())。供 `codesense` 命令调用。"""
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
