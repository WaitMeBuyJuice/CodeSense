"""MCP Tool: project_map — returns cached project-level architecture overview."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from codesense_v1 import cache
from codesense_v1.registry import tool

_CODESENSE_DIR = ".codesense"

_PROJECT_MAP_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="project_map",
    description=(
        "返回整个代码仓库的高层架构信息，包括：\n"
        "- 模块列表及每个模块的一句话职责\n"
        "- 模块之间的依赖关系\n"
        "- 辅助目录（测试代码、文档等）的简要说明\n\n"
        "当用户希望：\n"
        "- 理解项目整体结构或架构\n"
        "- 判断某个功能属于哪个模块\n"
        "- 评估一次修改可能影响哪些模块\n"
        "- 第一次浏览这个代码库\n\n"
        "优先使用本工具回答有关项目整体结构的问题，"
        "只有在需要了解模块内部细节时才调用 explore_module。\n\n"
        "不适用场景：\n"
        "- 查看模块内部接口、文件结构（使用 explore_module）\n"
        "- 查看具体类、函数或调用链（使用 CodeGraph 工具）\n"
        "- 查看源码文本（使用 grep/read_file）\n\n"
        "返回结果仅包含架构概览，不含源码细节。\n"
        "若缓存未就绪，工具会返回初始化步骤，引导完成后重新调用。\n\n"
        "示例：\n"
        "- 用户问「这个项目的整体架构是什么？」→ 调用 project_map\n"
        "- 用户问「登录功能在哪个模块？」→ 调用 project_map\n"
        "- 用户问「修改缓存逻辑会影响哪些地方？」→ 先 project_map 看依赖"
    ),
    input_schema=_PROJECT_MAP_INPUT_SCHEMA,
)
async def project_map() -> str:
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return (
            "# 错误\n\n"
            "环境变量 `CODESENSE_PROJECT_ROOT` 未设置。\n\n"
            "请在 MCP 配置（`codemaker_mcp_settings.json`）的 `env` 字段中添加该变量。"
        )

    project_root = Path(project_root_str)
    codesense_dir = project_root / _CODESENSE_DIR
    db_path = project_root / ".codegraph" / "codegraph.db"

    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`，完成后重新调用 project_map。"
        )

    current_hash = cache.db_hash(db_path)
    if cache.is_cache_valid(codesense_dir, current_hash):
        cached = cache.read_project_map(codesense_dir)
        if cached is not None:
            return cached

    return (
        "# 项目架构尚未生成或已过期，必须按照以下内容对缓存进行重建\n\n"
        "请选择以下任一方式生成项目架构概览：\n\n"
        "## 方式 1：委派给子 Agent（推荐，避免污染主对话上下文）\n\n"
        "如果你的 Agent 框架支持子任务（如 `task` / `dispatch_subagent` / `Task` 工具），"
        "请创建一个子 Agent 并让它执行以下任务：\n\n"
        "> 你是一个负责生成项目架构概览的子 Agent。请按下列步骤完成任务：\n"
        "> 1. 调用 `get_project_map_prompt` 获取分析提示词\n"
        "> 2. 阅读提示词后，按以下格式生成模块划分文本：\n"
        ">    - 每行一个模块：`模块名|一句话职责|目录`\n"
        ">    - 多目录用英文逗号分隔，例如 `核心层|封装核心逻辑|src/core,src/utils`\n"
        "> 3. 调用 `submit_project_map(response=<生成的文本>)` 提交结果\n"
        "> 4. 完成后回复\"已完成\"\n\n"
        "子 Agent 完成后，主 Agent 重新调用 `project_map` 即可获取最终架构概览。\n\n"
        "## 方式 2：主 Agent 直接执行（适用于无子 Agent 能力的场景）\n\n"
        "1. 调用 `get_project_map_prompt` 获取分析提示词\n"
        "2. 阅读提示词，按格式要求生成模块划分文本\n"
        "   - 每行一个模块，格式：`模块名|一句话职责|目录`\n"
        "   - 多个目录用英文逗号分隔\n"
        "3. 调用 `submit_project_map(response=<生成的文本>)` 提交结果\n"
        "4. 重新调用 `project_map` 获取架构概览\n"
    )
