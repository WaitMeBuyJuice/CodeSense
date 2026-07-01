"""MCP Tool: explore_module — returns cached module-level architecture understanding."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from codesense_v1 import cache, summarizer
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.summarizer import is_auto_expire_enabled
from codesense_v1.summarizer.summarizer import _compute_module_hash
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_EXPLORE_MODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_name": {
            "type": "string",
            "description": "project_map 中列出的模块名（精确名称）",
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
    name="explore_module",
    description=(
        "返回指定模块的深度架构理解，包括：\n"
        "- 一句话定位\n"
        "- 架构简析（模块内部分层）\n"
        "- 子模块列表（子模块名 | 职责 | 包含文件）\n"
        "- 上下游依赖\n"
        "- 实现约束清单\n\n"
        "当用户希望：\n"
        "- 了解某功能的实现\n"
        "- 修改某个功能，修改某个模块\n"
        "- 了解某模块的作用、结构、如何运行\n"
        "- 修改某模块前，理解其接口契约和依赖关系\n\n"
        "参数 module_name 必须是 project_map 返回的模块名之一（精确匹配）。\n"
        "不确定有哪些模块时，先调用 project_map 获取模块列表，不要猜测名称。\n\n"
        "不适用场景：\n"
        "- 只需知道功能属于哪个模块（使用 project_map）\n"
        "- 需要查看具体子模块实现（使用 explore_submodule）\n\n"
        "返回模块级架构描述，不含具体代码实现。\n"
        "传 `verify_only=true` 可获得轻量验证信号（缓存命中时 <100 字符），用于 cache miss 后的保存→验证流程。\n"
        "若缓存未就绪，工具会返回生成步骤，引导完成后重新调用。\n\n"
        "示例：\n"
        "- 用户问「cache 模块的作用？」→ explore_module(module_name=\"cache\")\n"
        "- 准备修改某模块前 → 先 explore_module 了解边界和约束"
    ),
    input_schema=_EXPLORE_MODULE_INPUT_SCHEMA,
)
async def explore_module(module_name: str, verify_only: bool = False) -> str:
    module_name = module_name.strip()
    if not module_name:
        raise InvalidArgumentError(
            "参数错误：module_name 不能为空。"
            "请检查工具参数说明，补充必要参数后重新调用。"
        )

    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / _CODESENSE_DIR
    db_path = project_root / ".codegraph" / "codegraph.db"
    mkey = cache.safe_key(module_name)

    # DB existence check
    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`，完成后重新调用 explore_module。"
        )

    # modules_index must exist
    index = cache.read_modules_index(codesense_dir)
    if index is None:
        return (
            "# 项目架构尚未生成\n\n"
            "请先调用 `project_map` 完成项目架构概览的生成流程，"
            "再调用 `explore_module`。"
        )

    # L2 auxiliary directory check
    raw_aux = index.get("auxiliary_dirs")
    aux_list: list[dict[str, object]] = (
        [a for a in raw_aux if isinstance(a, dict)]
        if isinstance(raw_aux, list)
        else []
    )
    norm_name = module_name.strip().lower()
    for aux in aux_list:
        if str(aux.get("name", "")).strip().lower() == norm_name:
            category = str(aux.get("category", "辅助代码"))
            file_count = aux.get("file_count", "?")
            name = str(aux.get("name", module_name))
            return (
                f"# {name}\n\n"
                f"此目录属于 **{category}**，包含约 {file_count} 个文件，"
                "未做深入的模块结构分析。\n\n"
                "如需了解其中的具体代码，请直接使用 `read_file` 或 codegraph 工具查询。"
            )

    # Find L1 entry
    raw_modules = index.get("modules")
    modules_list: list[dict[str, object]] = (
        [m for m in raw_modules if isinstance(m, dict)]
        if isinstance(raw_modules, list)
        else []
    )
    entry: dict[str, object] | None = None
    for m in modules_list:
        if str(m.get("name", "")).strip().lower() == norm_name:
            entry = m
            break

    if entry is None:
        available_l1 = [str(m.get("name", "")) for m in modules_list]
        available_l2 = [str(a.get("name", "")) for a in aux_list]
        available = available_l1 + (
            [f"{n}（辅助目录）" for n in available_l2] if available_l2 else []
        )
        raise InvalidArgumentError(
            f"参数错误：模块 '{module_name}' 不存在。"
            f"可用模块：{', '.join(available)}。"
            f"请使用上述模块名之一重新调用 explore_module。"
        )

    # Per-module cache check
    with CodeGraphDB(project_root) as db:
        current_module_hash = _compute_module_hash(entry, db)

    cached_md = cache.read_module(codesense_dir, mkey)
    stored_hashes = cache.read_module_hashes(codesense_dir)
    if is_auto_expire_enabled(project_root):
        module_cache_valid = cached_md is not None and stored_hashes.get(mkey) == current_module_hash
    else:
        module_cache_valid = cached_md is not None
    if module_cache_valid:
        if verify_only:
            subgroups = entry.get("subgroups") or []
            sg_names = " / ".join(str(sg.get("name", "")) for sg in subgroups if isinstance(sg, dict))
            size = len(cached_md)
            sg_part = f"，子模块：{sg_names}" if sg_names else ""
            return f"✅ 缓存命中：{module_name}（{size} 字符{sg_part}）"
        return cached_md  # type: ignore[return-value]

    # Cache miss → fetch prompt and embed it inline
    name = str(entry.get("name", module_name))
    try:
        prompt_text = await summarizer.get_module_prompt(project_root, name)
    except Exception as exc:
        prompt_text = f"（提示词获取失败：{exc}）"

    return (
        f"# 模块「{name}」尚未生成摘要，必须按照以下步骤生成摘要，自行判断使用哪种方式\n\n"
        "## 方式 1：委派给子 Agent\n\n"
        "如果你的 Agent 框架支持子任务（如 `task` / `dispatch_subagent` / `Task` 工具），"
        "请创建一个子 Agent 并让它执行以下任务：\n\n"
        f"> 你是一个负责生成模块摘要的子 Agent。请按下列步骤完成任务：\n"
        f"> 1. 阅读下方「分析提示词」，生成该模块的 Markdown 摘要，包含：\n"
        ">    - 一句话描述\n"
        ">    - 对外接口（函数/类签名）\n"
        ">    - 内部文件清单及职责\n"
        ">    - 依赖关系（上游/下游模块）\n"
        f"> 2. 调用 `save_module_summary(module_name=\"{name}\", summary=<生成的摘要>)` 保存\n"
        "> 3. 完成后回复\"已完成\"\n\n"
        f"子 Agent 完成后，主 Agent 调用 `explore_module(module_name=\"{name}\", verify_only=True)` 确认缓存命中，再正常重调获取最终摘要。\n\n"
        "## 方式 2：主 Agent 直接执行（适用于无子 Agent 能力的场景）\n\n"
        "1. 阅读下方「分析提示词」，生成该模块的 Markdown 摘要（包含：一句话描述、对外接口、内部文件、依赖关系）\n"
        f"2. 调用 `save_module_summary(module_name=\"{name}\", summary=<生成的摘要>)` 保存\n"
        f"3. 调用 `explore_module(module_name=\"{name}\", verify_only=True)` 确认缓存命中\n"
        f"4. 重新调用 `explore_module(module_name=\"{name}\")` 获取结果\n\n"
        "---\n\n"
        "## 分析提示词\n\n"
        f"{prompt_text}\n"
    )
