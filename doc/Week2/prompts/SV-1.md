# SV-1: 实现 src/codesense_v1/server.py

## 任务背景

`server` 模块为 L1 入口层，进程入口与协议桥接层。职责：

1. 创建官方 `mcp.server.Server` 实例
2. 在创建实例**之前**先 `import codesense_v1.tools`，确保所有 `@tool` 注册完成
3. 注册两个协议回调：`@server.list_tools()` 与 `@server.call_tool()`，委派到 `registry.list_tools()` / `registry.dispatch()`
4. 通过 `mcp.server.stdio.stdio_server()` 建立 stdio 传输并 `await server.run(...)`
5. 提供 `python -m codesense_v1.server` 启动方式（`if __name__ == "__main__"`）
6. 提供 `codesense` 命令入口（`pyproject.toml` 已声明 `codesense = "codesense_v1.server:main"`）

**绝不**在本模块出现：业务逻辑、参数校验、错误文案构造、工具元数据组装。

### 已有依赖

- `codesense_v1.tools`（T-2 完成）：import 即触发 `add` 注册到 `registry._REGISTRY`
- `codesense_v1.registry`（R-1 完成）：
  - `list_tools() -> list[mcp.types.Tool]`，同步函数，不抛异常
  - `async dispatch(name: str, arguments: dict) -> mcp.types.CallToolResult`，永不抛异常，错误转 `isError=True`
- 第三方：`mcp.server.Server`、`mcp.server.stdio.stdio_server`、`mcp.types`（`Tool` / `TextContent` / `ImageContent` / `EmbeddedResource` / `CallToolResult`）

### 严禁

- 在本模块 `print()`
- 配置 `logging` 输出到 stdout
- import `codesense_v1.errors` / `codesense_v1.schemas` / `codesense_v1.tools.add`（保持入口纯净）

---

## 实现目标

提供 3 个公开函数：

- `build_server() -> Server`：构造已绑定回调的 Server 实例（便于测试注入 mock transport）
- `async run_stdio() -> None`：建立 stdio 传输并阻塞运行
- `main() -> None`：`asyncio.run(run_stdio())`，供命令行入口调用

---

## 需要实现的文件

- `src/codesense_v1/server.py`

---

## 接口契约

```python
from __future__ import annotations
import asyncio
from typing import Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, EmbeddedResource, ImageContent

from codesense_v1 import tools as _tools  # noqa: F401 — 触发工具注册
from codesense_v1 import registry


SERVER_NAME: str = "CodeSense"
SERVER_VERSION: str = "0.1.0"


def build_server() -> Server: ...


async def run_stdio() -> None: ...


def main() -> None: ...


if __name__ == "__main__":
    main()
```

### 类型注解要点

- 回调签名严格匹配 mcp SDK 期望：
  - `list_tools() -> list[Tool]`
  - `call_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]`
- `SERVER_NAME` / `SERVER_VERSION` 显式声明类型，用于握手元数据

---

## 行为契约

### build_server 伪代码

```text
def build_server() -> Server:
    server = Server(name=SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return registry.list_tools()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None):
        result = await registry.dispatch(name, arguments or {})
        # 按当前 mcp SDK 版本做最薄适配：
        #   - 若 SDK 接受 CallToolResult 直接返回，则 return result
        #   - 否则 return result.content
        return result.content
    return server
```

**实现注意**：mcp Python SDK 不同版本对 `call_tool` 回调返回签名略有差异（早期返回 `list[TextContent | ...]`，较新版本接受 `CallToolResult`）。以 `pip show mcp` 实际版本的类型提示为准；registry 层保证永远产出 `CallToolResult`，server 层做最薄适配。

### run_stdio 伪代码

```text
async def run_stdio():
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
```

### main 伪代码

```text
def main():
    asyncio.run(run_stdio())

if __name__ == "__main__":
    main()
```

### 错误处理

- `list_tools` 回调：直接返回 `registry.list_tools()`，registry 不会抛
- `call_tool` 回调：`await registry.dispatch(...)`；registry 保证不抛
- `run_stdio` 在 stdin EOF 时正常返回 None，`main` 退出码 0
- 启动期异常允许冒泡，进程返回非 0
- **不**捕获 `KeyboardInterrupt`，交给 asyncio 默认行为

### stdout 污染防护

- 严禁 `print()`
- 严禁 logging 输出到 stdout
- 调试输出走 `sys.stderr`（MVP 阶段不输出）

---

## 验收标准

- `from codesense_v1.server import build_server, run_stdio, main, SERVER_NAME, SERVER_VERSION` 成功
- `build_server()` 返回未运行的 `mcp.server.Server` 实例
- `uv run python -m codesense_v1.server` 启动后 2 秒不退出（手工或集成测试验证；本任务自行确认进程不立即崩溃，集成断言由 TS-3 完成）
- `uv run codesense` 等效启动
- 严禁 import `errors` / `schemas` / `tools.add`
- 全部公开符号带完整类型注解
- `uv run mypy --strict src/codesense_v1/server.py` 零错误
- `uv run ruff check src/codesense_v1/server.py` 零警告

---

## 范围约束

- **仅** 创建 `src/codesense_v1/server.py`
- 严禁修改其他源码或 `pyproject.toml`
- 严禁编写集成测试（属于 TS-3）
