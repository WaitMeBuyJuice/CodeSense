"""MCP Tool: project_map — returns cached project-level architecture overview."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from codesense_v1 import cache
from codesense_v1.data import (
    collect_identity_sources,
    compute_architecture_hash,
    compute_dependencies_hash,
    compute_identity_hash,
    extract_tech_stack_hint,
    find_cycles,
    list_modules,
    module_dependencies,
    topological_layers,
)
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.config import get_ignore_paths
from codesense_v1.data.files import _load_ignore_spec
from codesense_v1.data.hashes import _sha256
from codesense_v1.registry import tool
from codesense_v1.summarizer import (
    _build_symbol_module_map,
    _resolve_roots_and_aux,
    get_concepts_segment_prompt,
    get_constraints_segment_prompt,
    get_flows_segment_prompt,
    get_identity_segment_prompt,
    get_project_map_prompt,
    is_auto_expire_enabled,
    render_dependencies_segment,
)
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_PROJECT_MAP_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "_nonce": {
            "type": "string",
            "description": "必须传入，且同一会话内每次调用须使用不同的递增字符串（如 \"1\"、\"2\"、\"3\"……）。某些 MCP 客户端可能会拦截重复值。",
        }
    },
    "additionalProperties": False,
}


def _seg_valid(codesense_dir: Path, seg_id: str, current_hash: str, auto_expire: bool) -> bool:
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
        "- 模块边界规则\n"
        "- 关键流程描述\n"
        "- 概念索引\n"
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
        "若缓存未就绪，工具会返回初始化步骤，引导完成后重新调用；project_map 验证方式为直接重调（无需传 `verify_only` 参数）。\n\n"
        "示例：\n"
        "- 用户问「这个项目的整体架构是什么？」→ 调用 project_map\n"
        "- 用户问「登录功能在哪个模块？」→ 调用 project_map\n"
        "- 用户问「修改缓存逻辑会影响哪些地方？」→ 先 project_map 看依赖\n\n"
        "**调用要求**：每次调用必须传 _nonce 参数，且同一会话内不得重复（如依次传 \"1\"、\"2\"、\"3\"）。"
    ),
    input_schema=_PROJECT_MAP_INPUT_SCHEMA,
)
async def project_map(_nonce: str | None = None) -> str:
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

    auto_expire = is_auto_expire_enabled(project_root)

    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    # ---- Gather data --------------------------------------------------------
    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=True)
        edges_internal = [e for e in edges_all if not e.is_external]
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]
        identity_sources = collect_identity_sources(project_root, db)
        all_db_edges = list(db.iter_edges())
        symbol_map = _build_symbol_module_map(saved_modules, db)

    cycles = find_cycles(edges_internal, modules_data)

    # Filter edges: exclude any edge where source or target is under an ignored path
    _ignore_prefixes = [p.replace("\\", "/").rstrip("/") for p in get_ignore_paths(project_root) if p.strip()]
    if _ignore_prefixes:
        def _edge_ignored(path: str) -> bool:
            fp = path.replace("\\", "/")
            return any(fp == ip or fp.startswith(ip + "/") for ip in _ignore_prefixes)
        edges_internal = [e for e in edges_internal if not _edge_ignored(e.source) and not _edge_ignored(e.target)]

    # ---- Compute hashes -----------------------------------------------------
    hash_01 = compute_identity_hash(identity_sources)

    roots, _ = _resolve_roots_and_aux(all_file_paths, project_root)
    all_file_paths_l1 = [p for p in all_file_paths if any(p.startswith(r + "/") or p == r for r in roots)]

    # 应用 ignore_docs.paths 过滤，与 submit_project_map 保持一致（确保 hash_03 两侧相等）
    _pm_ignore_spec = _load_ignore_spec(project_root)
    if _pm_ignore_spec is not None:
        all_file_paths_l1 = [p for p in all_file_paths_l1 if not _pm_ignore_spec.match_file(p)]

    all_parent_dirs = {
        fp.replace("\\", "/").rsplit("/", 1)[0]
        for fp in all_file_paths_l1
        if "/" in fp.replace("\\", "/")
    }
    current_leaf_dirs = sorted({
        d for d in all_parent_dirs
        if not any(other != d and other.startswith(d + "/") for other in all_parent_dirs)
    })
    hash_03 = compute_architecture_hash([current_leaf_dirs])

    # 04 & 07 share the same imports edge hash
    imports_hash = compute_dependencies_hash(edges_internal)
    hash_04 = imports_hash
    hash_07 = imports_hash

    # 05: calls edge set
    calls_edges = sorted(
        (e.source, e.target)
        for e in all_db_edges
        if getattr(e, 'kind', '') == "calls"
    )
    hash_05 = _sha256(json.dumps(calls_edges))

    modules_desc = sorted(
        (str(m.get("name", "")), str(m.get("description", "")))
        for m in saved_modules if isinstance(m, dict)
    )
    # 06_concepts 内容结构跟随模块划分，故 hash 跟随 modules_desc + hash_03 联动
    # （03 失效 → 06 必失效；模块名/描述变化 → 06 失效）
    hash_06 = _sha256(json.dumps(modules_desc) + hash_03)

    # ---- Generate pure-program segments immediately -------------------------
    if not _seg_valid(codesense_dir, "07_dependencies", hash_07, auto_expire):
        content_07 = render_dependencies_segment(saved_modules, edges_internal, cycles)
        cache.write_segment(codesense_dir, "07_dependencies", content_07, hash_07)

    # ---- Check what needs Agent ---------------------------------------------
    need_03 = not _seg_valid(codesense_dir, "03_modules", hash_03, auto_expire)
    dep_note = "（需 03_modules 先完成）" if need_03 else ""

    missing: list[tuple[str, str, str | None]] = []  # (seg_id, desc, dep)
    if not _seg_valid(codesense_dir, "01_identity", hash_01, auto_expire):
        missing.append(("01_identity", "仓库定位 + 技术栈", None))
    if need_03:
        missing.append(("03_modules", "模块列表（其他段依赖此段，请优先完成）", None))
    if not _seg_valid(codesense_dir, "04_constraints", hash_04, auto_expire):
        missing.append(("04_constraints", "模块边界规则" + dep_note, "03_modules" if need_03 else None))
    if not _seg_valid(codesense_dir, "05_flows", hash_05, auto_expire):
        missing.append(("05_flows", "关键流程描述" + dep_note, "03_modules" if need_03 else None))
    if not _seg_valid(codesense_dir, "06_concepts", hash_06, auto_expire):
        missing.append(("06_concepts", "概念索引" + dep_note, "03_modules" if need_03 else None))

    if not missing:
        result = cache.render_project_map(codesense_dir)
        if result:
            return result

    # ---- Fetch prompts for missing segments ---------------------------------
    tech_hints = extract_tech_stack_hint(identity_sources)
    seg_prompts: dict[str, str] = {}
    for seg_id, _, dep in missing:
        if dep:  # blocked by 03_modules, skip prompt fetch
            continue
        try:
            if seg_id == "01_identity":
                seg_prompts[seg_id] = get_identity_segment_prompt(identity_sources, tech_hints)
            elif seg_id == "03_modules":
                seg_prompts[seg_id] = await get_project_map_prompt(project_root)
            elif seg_id == "04_constraints":
                seg_prompts[seg_id] = await get_constraints_segment_prompt(project_root)
            elif seg_id == "05_flows":
                seg_prompts[seg_id] = await get_flows_segment_prompt(project_root)
            elif seg_id == "06_concepts":
                seg_prompts[seg_id] = await get_concepts_segment_prompt(project_root)
        except Exception as exc:
            seg_prompts[seg_id] = f"（提示词获取失败：{exc}）"

    # ---- One-shot missing list with embedded prompts ------------------------
    steps = []
    for i, (seg_id, desc, dep) in enumerate(missing):
        dep_str = f"\n\n   ⚠️ 依赖 `{dep}`，请等 `{dep}` 完成后再生成此段。" if dep else ""
        save_call = (
            f"`submit_project_map(response=<生成的模块划分文本>)`"
            if seg_id == "03_modules"
            else f"`save_project_map_segment(segment_id=\"{seg_id}\", content=<生成内容>)`"
        )
        prompt_section = ""
        if seg_id in seg_prompts:
            prompt_section = f"\n\n### 分析提示词\n\n{seg_prompts[seg_id]}"

        # 过期段提示旧文档路径
        expired_note = ""
        if cache.read_segment(codesense_dir, seg_id) is not None:
            expired_note = f" ⚠️ 缓存已过期\n\n旧文档仍可参考：`.codesense/project_map_segments/{seg_id}.md`，生成时可作为基础修改。"

        steps.append(
            f"## 步骤 {i+1}：{seg_id}（{desc}）{expired_note}{dep_str}\n\n"
            f"生成后调用 {save_call} 保存。"
            f"{prompt_section}"
        )

    steps_str = "\n\n---\n\n".join(steps)

    # 分类：从未生成 vs 缓存失效（文件存在但 hash 过期）
    new_segs = [seg_id for seg_id, _, _ in missing if cache.read_segment(codesense_dir, seg_id) is None]
    expired_segs = [seg_id for seg_id, _, _ in missing if cache.read_segment(codesense_dir, seg_id) is not None]
    summary_parts = []
    if new_segs:
        summary_parts.append("**待生成**：" + "、".join(f"`{s}`" for s in new_segs))
    if expired_segs:
        summary_parts.append("**缓存失效**：" + "、".join(f"`{s}`" for s in expired_segs))
    summary_str = "\n".join(summary_parts) + "\n\n" if summary_parts else ""

    return (
        "# 项目概览尚未完整，需生成以下段落\n\n"
        + summary_str
        + "## 生成顺序说明\n\n"
        "- **必须先完成 `03_modules`**（其他段依赖模块划分结果）\n"
        "- `01_identity` 与 `03_modules` 可并行生成\n"
        "- `04_constraints`、`05_flows`、`06_concepts` 需在 `03_modules` 完成后执行\n\n"
        "**全部完成后，重新调用 `project_map` 获取完整概览。**\n\n"
        "---\n\n"
        f"{steps_str}\n"
    )
