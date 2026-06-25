"""MCP Tool: get_project_map_prompt — returns the LLM prompt for project-level module mapping."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from codesense_v1 import summarizer
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="get_project_map_prompt",
    description=(
        "返回用于分析项目模块划分的提示词文本。\n\n"
        "仅在 project_map 返回初始化步骤引导时使用，通常委派给子 Agent 执行。\n"
        "正常使用时无需主动调用本工具。\n\n"
        "获取提示词后，按提示词格式生成模块划分文本，"
        "再调用 submit_project_map 提交结果。"
    ),
    input_schema=_SCHEMA,
)
async def get_project_map_prompt_tool() -> str:
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        raise InvalidArgumentError("参数错误：环境变量 CODESENSE_PROJECT_ROOT 未设置")
    try:
        return await summarizer.get_project_map_prompt(Path(project_root_str))
    except FileNotFoundError:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root_str}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )
