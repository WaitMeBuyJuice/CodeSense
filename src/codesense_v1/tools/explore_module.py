"""MCP Tool: explore_module — returns module-level architecture understanding."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from codesense_v1 import summarizer
from codesense_v1.errors import InvalidArgumentError, LLMError
from codesense_v1.registry import tool

_EXPLORE_MODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_name": {
            "type": "string",
            "description": "project_map 中列出的模块名（如 '缓存层'）",
        }
    },
    "required": ["module_name"],
    "additionalProperties": False,
}


@tool(
    name="explore_module",
    description=(
        "返回指定模块的架构理解：一句话描述、对外接口、内部文件、依赖模块。"
        "适用场景：需要了解某模块、探寻某模块的作用或策略、改动某模块前需先了解其结构和接口契约、"
        "理解模块间依赖关系。"
        "不适用场景：仅需定位模块位置（用 project_map_tool 即可）、"
        "已知确切文件路径或符号名（直接 grep/read_file）。"
        "参数：module_name 必须是 project_map_tool 返回的模块列表中的某一项（精确名称）。"
        "如果不知道有哪些模块，请先调用 project_map_tool 获取模块列表，"
        "再用确切的模块名调用本工具，不要猜测模块名称。"
        "返回结果由 LLM 生成，准确性依赖 project_map 阶段的模块划分。"
    ),
    input_schema=_EXPLORE_MODULE_INPUT_SCHEMA,
)
async def explore_module(module_name: str) -> str:
    """Raises: InvalidArgumentError, LLMError (→ ToolError chain, handled by registry)."""
    module_name = module_name.strip()
    if not module_name:
        raise InvalidArgumentError("参数错误：module_name 不能为空")

    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        raise InvalidArgumentError("参数错误：环境变量 CODESENSE_PROJECT_ROOT 未设置")

    project_root = Path(project_root_str)

    try:
        return await summarizer.module_summary(project_root, module_name)
    except FileNotFoundError:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            f"请先在该目录下运行 `codegraph init -i`，完成后重新调用 explore_module。"
        )
    except LLMError as exc:
        return (
            "# 错误\n\n"
            f"LLM 调用失败：{exc}\n\n"
            "请检查 `CODESENSE_LLM_API_KEY` 等环境变量配置。"
        )
