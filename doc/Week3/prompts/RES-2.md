# Prompt — RES-2：扩展 `server.py` 绑定 Resource 回调

## 任务背景

`project_map` 已作为 MCP Resource 实现（RES-1），现需在 `server.py` 的 `build_server()` 中绑定 `list_resources` 和 `read_resource` 回调，使 AI Agent 连接时能发现并读取该 Resource。

**前置条件**：`resources/project_map.py` 已实现（RES-1）。

## 实现目标

修改 `src/codesense_v1/server.py`，在 `build_server()` 中新增两个回调。不修改现有 Tool 相关逻辑。

## 现有 `server.py` 内容

```python
from __future__ import annotations
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool
from codesense_v1 import registry
from codesense_v1 import tools as _tools  # noqa: F401

SERVER_NAME: str = "CodeSense"
SERVER_VERSION: str = "0.1.0"

def build_server() -> Server:
    server: Server = Server(name=SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return registry.list_tools()

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, object]) -> CallToolResult:
        return await registry.dispatch(name, arguments)

    return server
```

## 需要新增的代码（在 `build_server()` 中）

```python
from mcp.types import AnyUrl, Resource, ReadResourceResult, TextResourceContents
from codesense_v1.resources import project_map as _pm

# 在 build_server() 内部，_call_tool 定义之后：

@server.list_resources()   # type: ignore[no-untyped-call, untyped-decorator]
async def _list_resources() -> list[Resource]:
    return [
        Resource(
            uri=AnyUrl(_pm.RESOURCE_URI),
            name=_pm.RESOURCE_NAME,
            description=_pm.RESOURCE_DESCRIPTION,
            mimeType=_pm.RESOURCE_MIME_TYPE,
        )
    ]

@server.read_resource()    # type: ignore[no-untyped-call, untyped-decorator]
async def _read_resource(uri: AnyUrl) -> ReadResourceResult:
    content = await _pm.read_project_map()
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri,
                mimeType=_pm.RESOURCE_MIME_TYPE,
                text=content,
            )
        ]
    )
```

> **注意**：`AnyUrl`、`Resource`、`ReadResourceResult`、`TextResourceContents` 的导入路径需根据实际安装的 `mcp==1.27.2` SDK 确认。若上述路径不对，从 `mcp.types` 中查找正确的类名。

## 需要修改的文件

- `src/codesense_v1/server.py`

## 测试验证

运行全量测试确认：
1. 现有 `tests/test_mcp_integration.py` 全部通过（Tool 功能不受影响）
2. `uv run ruff check src/codesense_v1/server.py` 零警告
3. `uv run mypy --strict src/codesense_v1/server.py` 零错误
4. `uv run pytest -q` 全部通过

## 验收标准

1. `build_server()` 返回的 server 注册了 `list_resources` 和 `read_resource` 回调
2. `list_resources` 返回包含 URI `codesense://project_map` 的列表
3. `read_resource` 回调调用 `_pm.read_project_map()` 并封装结果
4. 所有现有测试通过，无回归
5. `mypy --strict` 和 `ruff check` 零错误/警告

## 约束

- 只能修改 `src/codesense_v1/server.py`
- 不得修改其他任何文件
- 不得破坏现有 Tool 回调逻辑
