"""MCP Tool: save_submodule_summary — write Agent-generated file sub-module doc to cache."""

from __future__ import annotations

from typing import Final

from codesense_v1 import summarizer
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_name": {
            "type": "string",
            "description": "project_map 中列出的模块名（精确名称）",
        },
        "file_path": {
            "type": "string",
            "description": "模块内某个文件的相对路径（如 src/codesense_v1/cache/cache.py）",
        },
        "summary": {
            "type": "string",
            "description": "子模块文档 Markdown 文本",
        },
    },
    "required": ["module_name", "file_path", "summary"],
    "additionalProperties": False,
}


@tool(
    name="save_submodule_summary",
    description=(
        "将子模块（文件级）文档写入缓存，后续 explore_submodule 调用将直接返回该内容。\n\n"
        "仅在 explore_submodule 返回生成步骤引导时使用，通常委派给子 Agent 执行。\n"
        "正常使用时无需主动调用本工具。\n\n"
        "module_name 必须是 project_map 返回的模块名之一。\n"
        "file_path 为该模块内文件的相对路径。\n"
        "保存成功后，主 Agent 重新调用 explore_submodule 即可获取子模块文档。"
    ),
    input_schema=_SCHEMA,
)
async def save_submodule_summary_tool(module_name: str, file_path: str, summary: str) -> str:
    module_name = module_name.strip()
    file_path = file_path.strip().replace("\\", "/")

    if not module_name:
        raise InvalidArgumentError("参数错误：module_name 不能为空")
    if not file_path:
        raise InvalidArgumentError("参数错误：file_path 不能为空")
    if not summary.strip():
        raise InvalidArgumentError("参数错误：summary 不能为空")

    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    try:
        summarizer.save_submodule_summary(project_root, module_name, file_path, summary)
        basename = file_path.split("/")[-1]
        basename_no_ext = basename.rsplit(".", 1)[0]
        from codesense_v1 import cache
        module_key = cache.safe_key(module_name)
        file_key = f"{module_key}_{basename_no_ext}"
        write_path = f".codesense/modules/{module_key}/{file_key}.md"
        return (
            f"已保存模块 '{module_name}' 中文件 '{file_path}' 的子模块文档"
            f"（{len(summary)} 字符）。\n"
            f"写入路径：`{write_path}`"
        )
    except FileNotFoundError:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )
