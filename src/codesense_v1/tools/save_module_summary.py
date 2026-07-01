"""MCP Tool: save_module_summary — write Agent-generated module summary to cache."""

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
        "summary": {
            "type": "string",
            "description": "模块摘要 Markdown 文本",
        },
        "subgroups": {
            "type": "array",
            "description": (
                "子模块划分（可选）。每项含 name（子模块名，格式 <标识>，不含模块名前缀，如 storage、api）、"
                "description（职责说明）、files（文件路径列表）三个字段。"
                "仅当本次自行划分了子模块时传入；已有划分无需重复传入。"
                "详见 SERVER_INSTRUCTIONS 的 subgroups 约束。"
            ),
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "files": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "description", "files"],
            },
        },
    },
    "required": ["module_name", "summary"],
    "additionalProperties": False,
}


@tool(
    name="save_module_summary",
    description=(
        "将模块摘要写入缓存，后续 explore_module 调用将直接返回该内容。\n\n"
        "仅在 explore_module 返回生成步骤引导时使用，通常委派给子 Agent 执行。\n"
        "正常使用时无需主动调用本工具。\n\n"
        "module_name 必须是 project_map 返回的模块名之一。\n"
        "如果本次自行划分了子模块，可通过 subgroups 参数传入划分结果（已有划分无需重复传入）。\n"
        "保存成功后，主 Agent 重新调用 explore_module 即可获取模块摘要。"
    ),
    input_schema=_SCHEMA,
)
async def save_module_summary_tool(module_name: str, summary: str, subgroups: list | None = None) -> str:
    module_name = module_name.strip()
    if not module_name:
        raise InvalidArgumentError("参数错误：module_name 不能为空")
    if not summary.strip():
        raise InvalidArgumentError("参数错误：summary 不能为空")
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()
    try:
        summarizer.save_module_summary(project_root, module_name, summary, subgroups=subgroups)
        return f"已保存模块 '{module_name}' 的摘要（{len(summary)} 字符）。"
    except FileNotFoundError:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )
