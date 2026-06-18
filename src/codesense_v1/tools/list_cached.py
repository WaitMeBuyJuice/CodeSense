"""MCP Tool: list_cached — returns file names under .codesense/modules/."""

from __future__ import annotations

import json
import os
from pathlib import Path

from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.schemas import LIST_CACHED_INPUT_SCHEMA

_MODULES_DIR = "modules"


@tool(
    name="list_cached",
    description="返回当前 .codesense/modules/ 目录下的所有文件名列表（字符串数组）。",
    input_schema=LIST_CACHED_INPUT_SCHEMA,
)
async def list_cached() -> str:
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        raise InvalidArgumentError("参数错误：环境变量 CODESENSE_PROJECT_ROOT 未设置")

    modules_dir = Path(project_root_str) / ".codesense" / _MODULES_DIR
    if not modules_dir.is_dir():
        return json.dumps([], ensure_ascii=False)

    files = sorted([f.name for f in modules_dir.iterdir() if f.is_file()])
    return json.dumps(files, ensure_ascii=False)
