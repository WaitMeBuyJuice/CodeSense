"""MCP Tool: submit_project_map — process Agent-generated module list and write cache."""

from __future__ import annotations

from typing import Final

from codesense_v1 import summarizer
from codesense_v1.errors import LLMError
from codesense_v1.registry import tool
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "response": {
            "type": "string",
            "description": (
                "模块划分结果，每行一个模块，竖线分隔三列：模块名|职责|目录。"
                "示例：缓存管理|管理缓存读写|src/codesense_v1/cache"
            ),
        }
    },
    "required": ["response"],
    "additionalProperties": False,
}


@tool(
    name="submit_project_map",
    description=(
        "接收模块划分文本，写入缓存并返回渲染后的项目架构 Markdown。\n\n"
        "仅在 project_map 返回初始化步骤引导时使用，通常委派给子 Agent 执行。\n"
        "正常使用时无需主动调用本工具。\n\n"
        "参数 response 格式：每行一个模块「模块名|一句话职责|目录」，多目录用英文逗号分隔。\n"
        "示例：\n"
        "  缓存管理|负责缓存读写与失效|src/cache\n"
        "  数据层|封装数据库查询|src/data,src/models\n\n"
        "提交成功后，主 Agent 重新调用 project_map 即可获取架构概览。"
    ),
    input_schema=_SCHEMA,
)
async def submit_project_map_tool(response: str) -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()
    try:
        return await summarizer.submit_project_map(project_root, response)
    except FileNotFoundError:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )
