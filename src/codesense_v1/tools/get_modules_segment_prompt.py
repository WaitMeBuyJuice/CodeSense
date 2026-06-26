"""MCP Tool: get_modules_segment_prompt — returns the LLM prompt for module division."""

from __future__ import annotations

from typing import Final

from codesense_v1 import summarizer
from codesense_v1.registry import tool
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="get_modules_segment_prompt",
    description=(
        "返回用于分析项目模块划分的提示词文本。\n\n"
        "仅在 project_map 返回「03_modules 需要生成」时使用，通常委派给子 Agent 执行。\n"
        "正常使用时无需主动调用本工具。\n\n"
        "获取提示词后，按提示词格式生成模块划分文本，"
        "再调用 submit_project_map 提交结果。"
    ),
    input_schema=_SCHEMA,
)
async def get_modules_segment_prompt_tool() -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()
    try:
        return await summarizer.get_project_map_prompt(project_root)
    except FileNotFoundError:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )
