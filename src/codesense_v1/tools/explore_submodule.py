"""MCP Tool: explore_submodule — returns cached file-level sub-module documentation."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from codesense_v1 import cache, summarizer
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.summarizer import is_auto_expire_enabled
from codesense_v1.summarizer.summarizer import _compute_submodule_hash
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
            "description": "（文件模式）模块内某个文件的相对路径（如 src/codesense_v1/cache/cache.py）。与 subgroup_name 二选一。",
        },
        "subgroup_name": {
            "type": "string",
            "description": "（有 subgroups 时使用）子模块名，如 data_storage。与 file_path 二选一，优先级高于 file_path。",
        },
        "verify_only": {
            "type": "boolean",
            "description": "true 时命中缓存仅返回轻量确认信号（<100 字符），用于保存后的验证步骤；默认 false 返回完整文档",
        },
    },
    "required": ["module_name"],
    "additionalProperties": False,
}


@tool(
    name="explore_submodule",
    description=(
        "返回指定模块内某个子模块的深度理解，包括：\n"
        "- 子模块概述（业务职责）\n"
        "- 对外能力（该子模块对外提供什么能力）\n"
        "- 跨模块依赖（上游/下游模块）\n"
        "- 典型调用链\n\n"
        "适用场景：\n"
        "- 已通过 explore_module 了解模块整体，需要深入某个子模块实现细节\n"
        "- 修改特定子模块前，了解其能力边界和依赖关系\n\n"
        "参数说明：\n"
        "- module_name 必须是 project_map 返回的模块名之一\n"
        "- subgroup_name（优先）：从 explore_module 返回的「子模块列表」中取（如 data_storage）\n"
        "- file_path（备用）：若模块尚未定义 subgroups，可用文件相对路径（以项目根目录为基准，与 explore_module 返回的文件路径格式一致）\n\n"
        "传 `verify_only=true` 可获得轻量验证信号（缓存命中时 <100 字符），用于 cache miss 后的保存→验证流程。\n"
        "若缓存未就绪，工具会返回生成步骤，引导完成后重新调用。"
    ),
    input_schema=_EXPLORE_SUBMODULE_INPUT_SCHEMA,
)
async def explore_submodule(
    module_name: str,
    file_path: str = "",
    subgroup_name: str | None = None,
    verify_only: bool = False,
) -> str:
    module_name = module_name.strip()
    file_path = file_path.strip().replace("\\", "/")

    if not module_name:
        raise InvalidArgumentError(
            "参数错误：module_name 不能为空。"
        )
    if subgroup_name is None and not file_path:
        raise InvalidArgumentError(
            "参数错误：file_path 和 subgroup_name 至少提供一个。"
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

    name = str(entry.get("name", module_name))
    mkey = cache.safe_key(module_name)

    if subgroup_name is not None:
        subgroup_name = subgroup_name.replace("/", "_").replace("\\", "_").replace("..", "__")
        # Subgroup mode
        subgroups_raw = entry.get("subgroups") or []
        sg_entry: dict | None = None
        for sg in subgroups_raw:
            if str(sg.get("name", "")) == subgroup_name:
                sg_entry = sg
                break
        if sg_entry is None:
            available_sgs = [str(sg.get("name", "")) for sg in subgroups_raw]
            return (
                f"# 错误\n\n"
                f"子模块 `{subgroup_name}` 不存在于模块「{module_name}」。\n\n"
                f"可用子模块：\n"
                + "\n".join(f"- `{s}`" for s in sorted(available_sgs))
            )

        subgroup_files = [str(f).replace("\\", "/") for f in (sg_entry.get("files") or [])]
        file_key = (
            subgroup_name
            if subgroup_name.startswith(mkey + "_")
            else f"{mkey}_{subgroup_name}"
        )

        with CodeGraphDB(project_root) as db:
            current_hash = _compute_submodule_hash(subgroup_files, db)

        cached_md = cache.read_submodule(codesense_dir, mkey, file_key)
        stored_hashes = cache.read_submodule_hashes(codesense_dir, mkey)
        if is_auto_expire_enabled(project_root):
            cache_valid = cached_md is not None and stored_hashes.get(file_key) == current_hash
        else:
            cache_valid = cached_md is not None

        if cache_valid:
            if verify_only:
                target = subgroup_name or file_path
                return f"✅ 缓存命中：{module_name} / {target}（{len(cached_md)} 字符）"
            return cached_md  # type: ignore[return-value]

        # Cache miss → fetch prompt and embed it inline
        try:
            prompt_text = await summarizer.get_submodule_prompt(
                project_root, name, file_path or (subgroup_files[0] if subgroup_files else ""),
                subgroup_name=subgroup_name,
            )
        except Exception as exc:
            prompt_text = f"（提示词获取失败：{exc}）"

        return (
            f"# 子模块「{subgroup_name}」尚未生成文档，必须按照以下步骤生成文档，自行判断使用哪种方式\n\n"
            "## 方式 1：委派给子 Agent\n\n"
            "如果你的 Agent 框架支持子任务（如 `task` / `dispatch_subagent` / `Task` 工具），"
            "请创建一个子 Agent 并让它执行以下任务：\n\n"
            f"> 你是一个负责生成子模块文档的子 Agent。请按下列步骤完成任务：\n"
            f"> 1. 阅读下方「分析提示词」，生成该子模块的 Markdown 文档，包含：\n"
            ">    - 子模块概述\n"
            ">    - 对外能力\n"
            ">    - 跨模块依赖\n"
            ">    - 典型调用链\n"
            f"> 2. 调用 `save_submodule_summary(module_name=\"{name}\", subgroup_name=\"{subgroup_name}\", summary=<生成的文档>)` 保存\n"
            "> 3. 完成后回复\"已完成\"\n\n"
            f"子 Agent 完成后，主 Agent 调用 `explore_submodule(module_name=\"{name}\", subgroup_name=\"{subgroup_name}\", verify_only=True)` 确认缓存命中，再正常重调获取最终文档。\n\n"
            "## 方式 2：主 Agent 直接执行（适用于无子 Agent 能力的场景）\n\n"
            "1. 阅读下方「分析提示词」，生成该子模块的 Markdown 文档（包含：子模块概述、对外能力、跨模块依赖、典型调用链）\n"
            f"2. 调用 `save_submodule_summary(module_name=\"{name}\", subgroup_name=\"{subgroup_name}\", summary=<生成的文档>)` 保存\n"
            f"3. 调用 `explore_submodule(module_name=\"{name}\", subgroup_name=\"{subgroup_name}\", verify_only=True)` 确认缓存命中\n"
            f"4. 重新调用 `explore_submodule(module_name=\"{name}\", subgroup_name=\"{subgroup_name}\")` 获取结果\n\n"
            "---\n\n"
            "## 分析提示词\n\n"
            f"{prompt_text}\n"
        )

    # File mode (backward compatible)
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

    basename = file_path.split("/")[-1]
    basename_no_ext = basename.rsplit(".", 1)[0]
    file_key = f"{mkey}_{basename_no_ext}"

    # Cache check
    cached_md = cache.read_submodule(codesense_dir, mkey, file_key)
    stored_hashes = cache.read_submodule_hashes(codesense_dir, mkey)
    if is_auto_expire_enabled(project_root):
        cache_valid = cached_md is not None and stored_hashes.get(file_key) == current_hash
    else:
        cache_valid = cached_md is not None

    if cache_valid:
        if verify_only:
            target = subgroup_name or file_path
            return f"✅ 缓存命中：{module_name} / {target}（{len(cached_md)} 字符）"
        return cached_md  # type: ignore[return-value]

    # Cache miss → fetch prompt and embed it inline
    try:
        prompt_text = await summarizer.get_submodule_prompt(project_root, name, file_path)
    except Exception as exc:
        prompt_text = f"（提示词获取失败：{exc}）"

    return (
        f"# 子模块「{file_path}」尚未生成文档，必须按照以下步骤生成文档\n\n"
        "## 方式 1：委派给子 Agent（推荐，避免污染主对话上下文）\n\n"
        "如果你的 Agent 框架支持子任务（如 `task` / `dispatch_subagent` / `Task` 工具），"
        "请创建一个子 Agent 并让它执行以下任务：\n\n"
        f"> 你是一个负责生成子模块文档的子 Agent。请按下列步骤完成任务：\n"
        f"> 1. 阅读下方「分析提示词」，生成该文件的 Markdown 文档，包含：\n"
        ">    - 子模块概述\n"
        ">    - 对外能力\n"
        ">    - 跨模块依赖\n"
        ">    - 典型调用链\n"
        f"> 2. 调用 `save_submodule_summary(module_name=\"{name}\", file_path=\"{file_path}\", summary=<生成的文档>)` 保存\n"
        "> 3. 完成后回复\"已完成\"\n\n"
        f"子 Agent 完成后，主 Agent 调用 `explore_submodule(module_name=\"{name}\", file_path=\"{file_path}\", verify_only=True)` 确认缓存命中，再正常重调获取最终文档。\n\n"
        "## 方式 2：主 Agent 直接执行（适用于无子 Agent 能力的场景）\n\n"
        "1. 阅读下方「分析提示词」，生成该文件的 Markdown 文档（包含：子模块概述、对外能力、跨模块依赖、典型调用链）\n"
        f"2. 调用 `save_submodule_summary(module_name=\"{name}\", file_path=\"{file_path}\", summary=<生成的文档>)` 保存\n"
        f"3. 调用 `explore_submodule(module_name=\"{name}\", file_path=\"{file_path}\", verify_only=True)` 确认缓存命中\n"
        f"4. 重新调用 `explore_submodule(module_name=\"{name}\", file_path=\"{file_path}\")` 获取结果\n\n"
        "---\n\n"
        "## 分析提示词\n\n"
        f"{prompt_text}\n"
    )
