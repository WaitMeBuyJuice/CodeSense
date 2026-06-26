"""MCP Tool: save_project_map_segment — saves an Agent-generated project_map segment."""

from __future__ import annotations

from typing import Final

from codesense_v1 import cache
from codesense_v1.data import (
    classify_top_dirs,
    collect_identity_sources,
    compute_architecture_hash,
    compute_dependencies_hash,
    compute_identity_hash,
    compute_structure_hash,
    find_cycles,
    list_modules,
    module_dependencies,
)
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.files import directory_tree
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.summarizer import render_structure_segment
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_VALID_SEGMENT_IDS = ("01_identity", "03_modules")

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "segment_id": {
            "type": "string",
            "description": "段落 ID：01_identity 或 03_modules",
            "enum": list(_VALID_SEGMENT_IDS),
        },
        "content": {
            "type": "string",
            "description": "段落的 Markdown 内容",
        },
    },
    "required": ["segment_id", "content"],
    "additionalProperties": False,
}


@tool(
    name="save_project_map_segment",
    description=(
        "保存 Agent 生成的 project_map 段落内容到缓存。\n\n"
        "仅在 project_map 提示需要生成特定段落时使用。\n"
        "segment_id 必须是 project_map 返回的缺失段落之一。\n"
        "保存后，主 Agent 重新调用 project_map 获取完整概览。"
    ),
    input_schema=_SCHEMA,
)
async def save_project_map_segment_tool(segment_id: str, content: str) -> str:
    if segment_id not in _VALID_SEGMENT_IDS:
        raise InvalidArgumentError(
            f"无效的 segment_id: {segment_id!r}。"
            f"有效值为：{', '.join(_VALID_SEGMENT_IDS)}"
        )
    if not content.strip():
        raise InvalidArgumentError("content 不能为空")

    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / ".codesense"
    db_path = project_root / ".codegraph" / "codegraph.db"
    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )

    # Compute the current source hash for this segment
    with CodeGraphDB(project_root) as db:
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]
        if segment_id == "01_identity":
            sources = collect_identity_sources(project_root, db)
            source_hash = compute_identity_hash(sources)
        else:  # 03_modules
            modules_index = cache.read_modules_index(codesense_dir)
            saved_modules = (modules_index or {}).get("modules", [])
            module_dir_groups: list[list[str]] = [
                m.get("directories", []) for m in saved_modules
                if isinstance(m, dict)
            ]
            source_hash = compute_architecture_hash(module_dir_groups)

    cache.write_segment(codesense_dir, segment_id, content, source_hash)
    return f"段落 `{segment_id}` 已保存（{len(content)} 字符）。重新调用 `project_map` 获取完整概览。"
