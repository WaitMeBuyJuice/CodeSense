"""MCP Tool: get_identity_segment_prompt — returns LLM prompt for 01_identity segment."""

from __future__ import annotations

from typing import Final

from codesense_v1.data import collect_identity_sources, extract_tech_stack_hint
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.registry import tool
from codesense_v1.summarizer import get_identity_segment_prompt
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="get_identity_segment_prompt",
    description=(
        "返回用于生成项目身份信息段（仓库定位 + 技术栈）的 LLM 分析提示词。\n\n"
        "仅在 project_map 提示「01_identity 需要生成」时调用。\n"
        "获取提示词后，按格式生成内容，再调用 save_project_map_segment 保存。"
    ),
    input_schema=_SCHEMA,
)
async def get_identity_segment_prompt_tool() -> str:
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

    with CodeGraphDB(project_root) as db:
        sources = collect_identity_sources(project_root, db)

    tech_hints = extract_tech_stack_hint(sources)
    return get_identity_segment_prompt(sources, tech_hints)
