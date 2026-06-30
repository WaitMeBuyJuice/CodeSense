from __future__ import annotations
import json
import asyncio
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, GetPromptResult, Prompt, PromptMessage, TextContent, Tool

from codesense_v1 import registry
from codesense_v1 import skills as _skills  # noqa: F401 — 触发 Skill 加载
from codesense_v1 import tools as _tools  # noqa: F401 — 触发工具注册

SERVER_NAME: str = "CodeSense"
SERVER_VERSION: str = "0.1.0"
SERVER_INSTRUCTIONS: str = """\
CodeSense 用于帮助理解代码仓库的高层架构：项目组织方式、功能实现、模块作用职责、模块内部结构以及模块间协作关系。

## 核心规则

- 不要猜：仓库特有信息（模块职责、架构、依赖）优先调工具，不要按命名经验推断。
- 已知确切文件/符号时，直接 grep / read_file，无需走完整工具调用层级的流程。
- 同会话多次调用project_map工具时，`_nonce` 传不同递增值（"1"、"2"……），以避免客户端的重复调用检测拦截。

## 何时优先使用 CodeSense

以下意图优先调 CodeSense，而非直接 grep 或读源码：

- 第一次接触新代码库
- 需要获取项目整体结构、技术分层、模块组成等信息
- "某功能在哪里"、"哪个模块负责 XX"
- "修改某处会影响哪些地方"
- "某模块怎么工作"、"它的对外接口是什么"
- "两个模块之间是什么关系"
- "为什么这里放在这个模块"

## 工具调用层级（由全局到细节）

1. **全局** → `project_map`（项目架构、模块分布、跨模块依赖）
2. **模块** → `explore_module`（模块职责、公开接口、内部文件、依赖关系）
3. **子模块** → `explore_submodule`（子模块内文件结构、关键符号、实现细节）
4. **符号/原文** → codegraph MCP（`codegraph_explore` 优先，单符号/文件用 `codegraph_node`，调用链用 `codegraph_callers`）/ 精确文本用`grep` + `read_file`

## 与其他工具的分工

- 谁调用了某函数 → `codegraph_callers`
- 已知确切文件/符号 → `codegraph_node` / grep / read_file
- 理解代码在系统中的位置和角色 → CodeSense

## 缓存未就绪时

工具返回体内嵌了初始化引导，按提示操作即可。
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

    @server.list_prompts()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_prompts() -> list[Prompt]:
        return [
            Prompt(name=s.name, description=s.description)
            for s in _skills.list_skills()
        ]

    @server.get_prompt()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
        skill = _skills.get_skill(name)
        if skill is None:
            raise ValueError(f"未知 Skill：'{name}'")
        return GetPromptResult(
            description=skill.description,
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=skill.body),
                )
            ],
        )

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
