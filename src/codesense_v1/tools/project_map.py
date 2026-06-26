"""MCP Tool: project_map — returns cached project-level architecture overview."""

from __future__ import annotations

from typing import Final

from codesense_v1 import cache
from codesense_v1.data import (
    classify_top_dirs,
    collect_identity_sources,
    compute_architecture_hash,
    compute_dependencies_hash,
    compute_tree_max_depth,
    compute_identity_hash,
    compute_structure_hash,
    find_cycles,
    list_modules,
    module_dependencies,
    topological_layers,
)
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.files import directory_tree
from codesense_v1.registry import tool
from codesense_v1.summarizer import (
    is_auto_expire_enabled,
    render_dependencies_segment,
    render_structure_segment,
)
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_PROJECT_MAP_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def _seg_valid(codesense_dir, seg_id: str, current_hash: str, auto_expire: bool) -> bool:
    if not auto_expire:
        return cache.read_segment(codesense_dir, seg_id) is not None
    return cache.is_segment_valid(codesense_dir, seg_id, current_hash)


@tool(
    name="project_map",
    description=(
        "返回整个代码仓库的高层架构信息，包括：\n"
        "- 仓库定位与技术栈\n"
        "- 顶层目录结构\n"
        "- 系统分层与模块列表\n"
        "- 模块间依赖关系\n\n"
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
        "若缓存未就绪，工具会返回初始化步骤，引导完成后重新调用。\n\n"
        "示例：\n"
        "- 用户问「这个项目的整体架构是什么？」→ 调用 project_map\n"
        "- 用户问「登录功能在哪个模块？」→ 调用 project_map\n"
        "- 用户问「修改缓存逻辑会影响哪些地方？」→ 先 project_map 看依赖"
    ),
    input_schema=_PROJECT_MAP_INPUT_SCHEMA,
)
async def project_map() -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / _CODESENSE_DIR
    db_path = project_root / ".codegraph" / "codegraph.db"

    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`，完成后重新调用 project_map。"
        )

    auto_expire = is_auto_expire_enabled()

    # ---- Gather raw data (single DB open) ------------------------------------
    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=True)
        edges_internal = [e for e in edges_all if not e.is_external]
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]
        tree_root = directory_tree(db)
        identity_sources = collect_identity_sources(project_root, db)

    top_dirs = classify_top_dirs(all_file_paths)
    layers = topological_layers(edges_internal, modules_data)
    cycles = find_cycles(edges_internal, modules_data)

    # ---- Compute segment hashes ---------------------------------------------
    hash_01 = compute_identity_hash(identity_sources)
    hash_02 = compute_structure_hash(top_dirs)
    hash_04 = compute_dependencies_hash(edges_all)

    # 03 hash depends on saved module-dir assignments
    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])
    module_dir_groups: list[list[str]] = [
        m.get("directories", []) for m in saved_modules
        if isinstance(m, dict)
    ]
    hash_03 = compute_architecture_hash(module_dir_groups)

    # ---- Generate 02 and 04 immediately (pure program, no Agent) ------------
    if not _seg_valid(codesense_dir, "02_structure", hash_02, auto_expire):
        adaptive_depth = compute_tree_max_depth(all_file_paths)
        content_02 = render_structure_segment(project_root, top_dirs, tree_root, max_depth=adaptive_depth)
        cache.write_segment(codesense_dir, "02_structure", content_02, hash_02)

    if not _seg_valid(codesense_dir, "04_dependencies", hash_04, auto_expire):
        content_04 = render_dependencies_segment(
            saved_modules, edges_all, cycles
        )
        cache.write_segment(codesense_dir, "04_dependencies", content_04, hash_04)

    # ---- Check if 01 / 03 need Agent ----------------------------------------
    need_01 = not _seg_valid(codesense_dir, "01_identity", hash_01, auto_expire)
    need_03 = not _seg_valid(codesense_dir, "03_modules", hash_03, auto_expire)

    if not need_01 and not need_03:
        result = cache.render_project_map(codesense_dir)
        if result:
            return result

    # ---- Return Agent instructions for missing segments ---------------------
    missing = []
    if need_01:
        missing.append("**01_identity**（仓库定位 + 技术栈）\n   → 调用 `get_identity_segment_prompt` 获取提示词，生成内容后调用 `save_project_map_segment(segment_id=\"01_identity\", content=...)`")
    if need_03:
        missing.append("**03_modules**（模块列表）\n   → 调用 `get_modules_segment_prompt` 获取提示词，按格式生成后调用 `submit_project_map(response=...)`")

    missing_str = "\n".join(f"{i+1}. {m}" for i, m in enumerate(missing))

    return (
        "# 项目概览尚未完整生成，需要生成以下段落\n\n"
        f"{missing_str}\n\n"
        "# 请自己选用以下方式的一中（若没有子Agent就选用方式2）\n\n"
        "## 方式 1：委派给子 Agent（推荐）\n\n"
        "请创建子 Agent 执行以下任务：\n\n"
        "> 1. 按顺序完成上方缺失段落的生成步骤\n"
        "> 2. 每个段落生成后立即调用对应工具保存\n"
        "> 3. 所有段落完成后回复「已完成」\n\n"
        "子 Agent 完成后，主 Agent 重新调用 `project_map` 获取完整概览。\n\n"
        "## 方式 2：主 Agent 直接执行\n\n"
        "按顺序执行上方缺失段落的生成步骤，完成后重新调用 `project_map`。"
    )
