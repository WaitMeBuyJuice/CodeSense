"""MCP Tool: list_cached_modules — returns all cached module keys under .codesense/modules/."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool

_MODULES_DIR = "modules"

_LIST_CACHED_MODULES_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="list_cached_modules",
    description="返回当前 .codesense/modules/ 目录下所有已缓存的模块 key 列表（字符串数组）。",
    input_schema=_LIST_CACHED_MODULES_INPUT_SCHEMA,
)
async def list_cached_modules() -> str:
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        raise InvalidArgumentError("参数错误：环境变量 CODESENSE_PROJECT_ROOT 未设置")

    modules_dir = Path(project_root_str) / ".codesense" / _MODULES_DIR
    if not modules_dir.is_dir():
        return json.dumps([], ensure_ascii=False)

    keys = [f.stem for f in sorted(modules_dir.glob("*.md"))]
    return json.dumps(keys, ensure_ascii=False)
