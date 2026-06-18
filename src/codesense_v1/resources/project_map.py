"""MCP Resource: codesense://project_map."""

from __future__ import annotations

import os
from pathlib import Path

from codesense_v1 import summarizer
from codesense_v1.errors import LLMError

RESOURCE_URI: str = "codesense://project_map"
RESOURCE_NAME: str = "Project Architecture Map"
RESOURCE_DESCRIPTION: str = (
    "项目整体架构概览（模块列表、一句话描述、跨模块依赖关系）。"
    "适用场景：初次接触代码库时定向、定位某个功能属于哪个模块、判断改动会影响哪些模块。"
    "不适用场景：需要了解模块内部结构或接口细节（改用 explore_module）。"
)
RESOURCE_MIME_TYPE: str = "text/markdown"


async def read_project_map() -> str:
    """Return project map content as Markdown.

    Reads ``CODESENSE_PROJECT_ROOT`` from environment.
    On any error, returns a Markdown string describing the error — never raises.
    """
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return (
            "# 错误\n\n"
            "环境变量 `CODESENSE_PROJECT_ROOT` 未设置。"
            "请在 MCP 配置（`codemaker_mcp_settings.json`）的 `env` 字段中添加该变量。"
        )

    project_root = Path(project_root_str)
    try:
        return await summarizer.project_map_summary(project_root)
    except FileNotFoundError as exc:
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在：{exc}\n\n"
            "请先在目标项目中运行 `codegraph init -i`。"
        )
    except LLMError as exc:
        return (
            "# 错误\n\n"
            f"LLM 调用失败：{exc}\n\n"
            "请检查 `CODESENSE_LLM_API_KEY` 等环境变量配置。"
        )
    except Exception as exc:  # noqa: BLE001
        return f"# 错误\n\n内部错误：{type(exc).__name__}: {exc}"
