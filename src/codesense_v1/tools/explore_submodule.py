"""MCP Tool: explore_submodule — returns cached file-level sub-module documentation."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from codesense_v1 import cache
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.summarizer import is_auto_expire_enabled
from codesense_v1.summarizer.summarizer import _compute_submodule_hash, _is_single_file_module
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_EXPLORE_SUBMODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
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
    },
    "required": ["module_name", "file_path"],
    "additionalProperties": False,
}


@tool(
    name="explore_submodule",
    description=(
        "返回指定模块内某个文件的深度理解，包括：\n"
        "- 文件概述（2-3 句话）\n"
        "- 对外接口（函数/类签名及说明）\n"
        "- 跨模块依赖（出向/入向）\n"
        "- 典型调用链\n\n"
        "适用场景：\n"
        "- 已通过 explore_module 了解模块整体，需要进一步了解某个文件的实现细节\n"
        "- 修改特定文件前，了解其接口契约和依赖关系\n\n"
        "参数说明：\n"
        "- module_name 必须是 project_map 返回的模块名之一（精确匹配）\n"
        "- file_path 为该模块内文件的相对路径（如 src/codesense_v1/cache/cache.py）\n\n"
        "若缓存未就绪，工具会返回生成步骤，引导完成后重新调用。\n"
        "单文件模块请直接使用 explore_module。"
    ),
    input_schema=_EXPLORE_SUBMODULE_INPUT_SCHEMA,
)
async def explore_submodule(module_name: str, file_path: str) -> str:
    module_name = module_name.strip()
    file_path = file_path.strip().replace("\\", "/")

    if not module_name:
        raise InvalidArgumentError(
            "参数错误：module_name 不能为空。"
        )
    if not file_path:
        raise InvalidArgumentError(
            "参数错误：file_path 不能为空。"
        )

    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / _CODESENSE_DIR
    db_path = project_root / ".codegraph" / "codegraph.db"

    # DB existence check
    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`，完成后重新调用 explore_submodule。"
        )

    # modules_index must exist
    index = cache.read_modules_index(codesense_dir)
    if index is None:
        return (
            "# 项目架构尚未生成\n\n"
            "请先调用 `project_map` 完成项目架构概览的生成流程，"
            "再调用 `explore_submodule`。"
        )

    # Find module entry
    raw_modules = index.get("modules")
    modules_list: list[dict[str, object]] = (
        [m for m in raw_modules if isinstance(m, dict)]
        if isinstance(raw_modules, list)
        else []
    )
    norm_name = module_name.strip().lower()
    entry: dict[str, object] | None = None
    for m in modules_list:
        if str(m.get("name", "")).strip().lower() == norm_name:
            entry = m
            break

    if entry is None:
        available = [str(m.get("name", "")) for m in modules_list]
        raise InvalidArgumentError(
            f"参数错误：模块 '{module_name}' 不存在。"
            f"可用模块：{', '.join(available)}。"
            f"请使用上述模块名之一重新调用 explore_submodule。"
        )

    # Single-file module check
    if _is_single_file_module(entry):
        name = str(entry.get("name", module_name))
        return (
            f"# 模块「{name}」是单文件模块\n\n"
            "该模块除 `__init__.py` 外只有一个（或零个）`.py` 文件，"
            "无需子模块文档。\n\n"
            f"请直接使用 `explore_module(module_name=\"{name}\")` 获取模块详情。"
        )

    # Validate file_path in module files
    files_raw = entry.get("files")
    module_files = [str(f).replace("\\", "/") for f in (files_raw if isinstance(files_raw, list) else [])]
    if file_path not in module_files:
        return (
            f"# 错误\n\n"
            f"文件 `{file_path}` 不在模块「{module_name}」的文件列表中。\n\n"
            f"该模块包含的文件：\n"
            + "\n".join(f"- `{f}`" for f in sorted(module_files))
        )

    # Compute current submodule hash
    with CodeGraphDB(project_root) as db:
        current_hash = _compute_submodule_hash(file_path, db)

    mkey = cache.safe_key(module_name)
    file_stem = file_path.split("/")[-1].replace(".", "_")
    file_key = cache.safe_key(file_stem)

    # Cache check
    cached_md = cache.read_submodule(codesense_dir, mkey, file_key)
    stored_hashes = cache.read_submodule_hashes(codesense_dir, mkey)
    if is_auto_expire_enabled():
        cache_valid = cached_md is not None and stored_hashes.get(file_key) == current_hash
    else:
        cache_valid = cached_md is not None

    if cache_valid:
        return cached_md  # type: ignore[return-value]

    # Cache miss → guide Agent through generation workflow
    name = str(entry.get("name", module_name))
    return (
        f"# 子模块「{file_path}」尚未生成文档，必须按照以下内容生成文档\n\n"
        "请选择以下任一方式生成该文件的子模块文档：\n\n"
        "## 方式 1：委派给子 Agent（推荐，避免污染主对话上下文）\n\n"
        "如果你的 Agent 框架支持子任务（如 `task` / `dispatch_subagent` / `Task` 工具），"
        "请创建一个子 Agent 并让它执行以下任务：\n\n"
        f"> 你是一个负责生成子模块文档的子 Agent。请按下列步骤完成任务：\n"
        f"> 1. 调用 `get_submodule_prompt(module_name=\"{name}\", file_path=\"{file_path}\")` 获取分析提示词\n"
        "> 2. 阅读提示词，生成该文件的 Markdown 文档，包含：\n"
        ">    - 文件概述\n"
        ">    - 对外接口（函数/类签名）\n"
        ">    - 跨模块依赖（出向/入向）\n"
        ">    - 典型调用链\n"
        f"> 3. 调用 `save_submodule_summary(module_name=\"{name}\", file_path=\"{file_path}\", summary=<生成的文档>)` 保存\n"
        "> 4. 完成后回复\"已完成\"\n\n"
        f"子 Agent 完成后，主 Agent 重新调用 `explore_submodule(module_name=\"{name}\", file_path=\"{file_path}\")` 即可获取最终文档。\n\n"
        "## 方式 2：主 Agent 直接执行（适用于无子 Agent 能力的场景）\n\n"
        f"1. 调用 `get_submodule_prompt(module_name=\"{name}\", file_path=\"{file_path}\")` 获取分析提示词\n"
        "2. 阅读提示词，生成该文件的 Markdown 文档（包含：文件概述、对外接口、跨模块依赖、典型调用链）\n"
        f"3. 调用 `save_submodule_summary(module_name=\"{name}\", file_path=\"{file_path}\", summary=<生成的文档>)` 保存\n"
        f"4. 重新调用 `explore_submodule(module_name=\"{name}\", file_path=\"{file_path}\")` 获取结果\n"
    )
