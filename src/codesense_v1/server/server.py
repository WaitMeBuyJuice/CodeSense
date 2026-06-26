from __future__ import annotations
import json
import asyncio
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool

from codesense_v1 import registry
from codesense_v1 import tools as _tools  # noqa: F401 — 触发工具注册

SERVER_NAME: str = "CodeSense"
SERVER_VERSION: str = "0.1.0"
SERVER_INSTRUCTIONS: str = """\
CodeSense 用于帮助理解代码仓库的高层架构，包括项目组织方式、功能实现、模块作用职责、模块内部结构以及模块间协作关系。
优先使用CodeSense内工具，若信息不全可通过grep/read_file探索源码。

## 通用规则

- 不要猜：对于仓库特有的信息（模块职责、架构、依赖关系等），如果能够通过工具获得准确答案，\
应优先调用工具，不要根据命名或经验推断。

## 何时优先使用 CodeSense

当用户问题涉及以下意图时，**优先使用 CodeSense 工具**，而不是直接 grep 或读源码：

- 项目整体结构、架构、技术分层、模块组成
- "某功能在哪里"、"哪个模块负责 XX"
- "修改某处会影响哪些地方"
- "某模块怎么工作"、"它的对外接口是什么"
- "两个模块之间是什么关系"
- "为什么这里放在这个模块"
- 第一次接触新代码库时定向

## 工具调用顺序

1. **整体优先** → `project_map`（项目架构、模块分布、跨模块依赖）
2. **局部深入** → `explore_module`（单个模块的接口、内部结构、依赖关系）

## 与其他工具的分工

- 想问"谁调用了某函数" → 调用关系分析工具（例如 CodeGraph）
- 已知确切文件/符号 → grep / read_file
- 想理解"代码在系统里的位置和角色" → CodeSense

## 缓存未就绪时

如果某工具提示缓存未初始化，按照工具返回的引导完成初始化。\
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
    _init_codesenseignore()
    asyncio.run(run_stdio())


def _init_codesenseignore() -> None:
    """在 .codesense/ 下创建 .codesenseignore 模板（若不存在）。"""
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return
    target = Path(project_root_str) / ".codesense" / ".codesenseignore"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# CodeSense ignore — 排除知识文档分析时不需要的目录/文件\n"
        "# 语法同 .gitignore\n"
        "#\n"
        "# 注意：.gitignore 中的规则已自动应用，此文件用于补充 CodeSense 专属的排除规则\n"
        "#\n"
        "# 示例：\n"
        "# docs/\n"
        "# migrations/\n"
        "# **/*.generated.py\n"
        "# scripts/\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
