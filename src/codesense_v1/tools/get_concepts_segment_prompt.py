"""MCP Tool: get_concepts_segment_prompt — returns LLM prompt for concept index."""

from __future__ import annotations

from typing import Final

from codesense_v1.registry import tool
from codesense_v1.summarizer import get_concepts_segment_prompt
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="get_concepts_segment_prompt",
    description=(
        "返回用于生成概念索引段（06_concepts）的 LLM 分析提示词。\n\n"
        "仅在 project_map 提示「06_concepts 需要生成」时调用。\n"
        "需要先完成 03_modules 的生成。\n"
        "获取提示词后，按格式生成内容，再调用 save_project_map_segment 保存。"
    ),
    input_schema=_SCHEMA,
)
async def get_concepts_segment_prompt_tool() -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    db_path = project_root / ".codegraph" / "codegraph.db"
    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )

    try:
        return await get_concepts_segment_prompt(project_root)
    except FileNotFoundError:
        return "# 错误\n\nCodeGraph 数据库不存在。请先运行 `codegraph init -i`。"
