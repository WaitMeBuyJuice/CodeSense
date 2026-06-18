# 详细设计 - server 模块

> 路径：`src/codesense_v1/server.py`  
> 层级：L1 入口  
> 概要设计参考：`doc/design/overview.md` §1.2、§2、§4、§5 D6~D7

---

## 1. 模块功能说明

进程入口与协议桥接层。职责：

1. 创建官方 `mcp.server.Server` 实例。
2. 在创建实例**之前**先 `import codesense_v1.tools`，确保所有 `@tool` 注册完成。
3. 注册两个协议回调：`@server.list_tools()` 与 `@server.call_tool()`，把它们委派到 `registry.list_tools()` / `registry.dispatch()`。
4. 通过 `mcp.server.stdio.stdio_server()` 建立 stdio 传输并 `await server.run(...)`。
5. 提供 `python -m codesense_v1.server` 启动方式（`if __name__ == "__main__"`）。

**绝不**在本模块出现：业务逻辑、参数校验、错误文案构造、工具元数据组装。

---

## 2. 对外暴露的接口签名

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


def build_server() -> Server:
    """构造并返回已绑定回调的 mcp Server 实例。便于测试直接拿到 Server 注入 mock transport。"""


async def run_stdio() -> None:
    """启动 stdio 传输并阻塞运行，直到 stdin 关闭或收到关闭信号。"""


def main() -> None:
    """同步入口：asyncio.run(run_stdio())。供 `python -m codesense_v1.server` 调用。"""
```

类型注解要点：

- 回调函数签名严格匹配 mcp SDK 期望：
  - `list_tools() -> list[Tool]`
  - `call_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]`
- `SERVER_NAME` / `SERVER_VERSION` 显式声明类型，用于握手元数据。

---

## 3. 核心数据结构定义

无新增结构。复用：

- `mcp.server.Server`
- `mcp.types.Tool / TextContent / ImageContent / EmbeddedResource / CallToolResult`

---

## 4. 错误码与异常处理规范

### 4.1 协议回调内部

- `list_tools` 回调：直接返回 `registry.list_tools()`。`registry.list_tools` 不会抛异常；若极端情况下抛出，由 mcp SDK 转为 JSON-RPC 错误响应（非本模块构造）。
- `call_tool` 回调：`await registry.dispatch(name, arguments or {})`，取其 `.content` 返回。registry 保证不抛异常。

### 4.2 进程级

- `run_stdio` 在正常关闭（stdin EOF）时返回 None，`main` 退出码 0。
- 启动期异常（如端口/资源占用——stdio 场景几乎不会有）允许冒泡，进程返回非 0。
- **不**捕获 `KeyboardInterrupt`；交给 asyncio 默认行为，便于本地调试 Ctrl+C 退出。

### 4.3 stdout 污染防护

- 严禁在本模块使用 `print()`。
- 严禁在本模块配置 `logging` 输出到 stdout。
- 任何调试输出必须走 `sys.stderr`（MVP 阶段直接不输出）。

---

## 5. 关键算法 / 业务逻辑

### 5.1 build_server 伪代码

```text
def build_server() -> Server:
    server = Server(name=SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return registry.list_tools()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None):
        result = await registry.dispatch(name, arguments or {})
        # mcp SDK 期望返回 content 列表；isError 由 SDK 根据返回值/异常推断，
        # 这里若 isError=True 需通过抛出 SDK 提供的机制或直接返回带错误标记的 content。
        # 具体实现按当前 mcp SDK 版本 API 调整：
        #   - 若 SDK 接受 CallToolResult 直接返回，则 return result
        #   - 否则 return result.content（错误信息已包含在 TextContent 中）
        return result.content
    return server
```

> **实现注意**：mcp Python SDK 不同版本对 `call_tool` 回调的返回签名略有差异（早期返回 `list[TextContent | ...]`，较新版本接受 `CallToolResult`）。编码阶段以 `pip show mcp` 实际版本的类型提示为准；本设计保证 registry 层永远产出 `CallToolResult`，server 层做最薄适配。

### 5.2 run_stdio 伪代码

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

### 5.3 main 伪代码

```text
def main():
    asyncio.run(run_stdio())

if __name__ == "__main__":
    main()
```

---

## 6. 与其他模块的交互契约

```
server ──► codesense_v1.tools : import 触发副作用（注册工具），不调用任何符号
server ──► registry      : 调用 list_tools()、await dispatch(name, args)
server ──► mcp.server    : 创建 Server、stdio_server
server ──► mcp.types     : 类型引用
server ──► asyncio       : 事件循环
```

约束：

- **必须**先 `import codesense_v1.tools` 再 `build_server`，否则 `list_tools` 为空。
- **禁止** import `errors` / `schemas` / `tools.add`（保持入口纯净，依赖单向）。
- `build_server` 必须返回未运行的 Server 实例，使集成测试可注入自定义 transport。
- `pyproject.toml` **必须**声明命令行入口：
  ```toml
  [project.scripts]
  codesense = "codesense_v1.server:main"
  ```
  `uv sync` 后即可用 `codesense` 命令启动服务。CodeMaker 配置示例片段中应优先使用该命令；`python -m codesense_v1.server` 作为备用。
