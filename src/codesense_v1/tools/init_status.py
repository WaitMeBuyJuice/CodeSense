"""MCP Tool: init_status — reports CodeSense initialization progress across all three phases."""

from __future__ import annotations

import json
from typing import Final

from codesense_v1 import cache
from codesense_v1.data import (
    collect_identity_sources,
    compute_architecture_hash,
    compute_dependencies_hash,
    compute_identity_hash,
    module_dependencies,
)
from codesense_v1.data.config import get_ignore_paths
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.files import _load_ignore_spec
from codesense_v1.data.hashes import _sha256
from codesense_v1.registry import tool
from codesense_v1.summarizer import (
    _compute_submodule_hash,
    _resolve_roots_and_aux,
    is_auto_expire_enabled,
)
from codesense_v1.summarizer.summarizer import _compute_module_hash
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_SEGMENT_IDS: tuple[str, ...] = (
    "01_identity",
    "02_modules",
    "03_constraints",
    "04_flows",
    "05_concepts",
    "06_dependencies",
)

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def _compute_segment_hashes(project_root, codesense_dir, saved_modules, db) -> dict[str, str]:
    """复用 project_map.py 的 hash 计算逻辑，返回 {segment_id: current_hash}。"""
    edges_all = module_dependencies(db, include_external=True)
    edges_internal = [e for e in edges_all if not e.is_external]
    all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]
    identity_sources = collect_identity_sources(project_root, db)
    all_db_edges = list(db.iter_edges())

    # ignore 过滤 edges
    _ignore_prefixes = [p.replace("\\", "/").rstrip("/") for p in get_ignore_paths(project_root) if p.strip()]
    if _ignore_prefixes:
        def _edge_ignored(path: str) -> bool:
            fp = path.replace("\\", "/")
            return any(fp == ip or fp.startswith(ip + "/") for ip in _ignore_prefixes)
        edges_internal = [e for e in edges_internal if not _edge_ignored(e.source) and not _edge_ignored(e.target)]

    # hash_01
    hash_01 = compute_identity_hash(identity_sources)

    # hash_03
    roots, _ = _resolve_roots_and_aux(all_file_paths, project_root)
    all_file_paths_l1 = [p for p in all_file_paths if any(p.startswith(r + "/") or p == r for r in roots)]
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

    # hash_04 / hash_07
    imports_hash = compute_dependencies_hash(edges_internal)

    # hash_05
    calls_edges = sorted(
        (e.source, e.target)
        for e in all_db_edges
        if getattr(e, 'kind', '') == "calls"
    )
    hash_05 = _sha256(json.dumps(calls_edges))

    # hash_06
    modules_desc = sorted(
        (str(m.get("name", "")), str(m.get("description", "")))
        for m in saved_modules if isinstance(m, dict)
    )
    hash_06 = _sha256(json.dumps(modules_desc) + hash_03)

    return {
        "01_identity": hash_01,
        "02_modules": hash_03,
        "03_constraints": imports_hash,
        "04_flows": hash_05,
        "05_concepts": hash_06,
        "06_dependencies": imports_hash,
    }


@tool(
    name="init_status",
    description=(
        "返回 CodeSense 三阶段初始化的完成情况：\n"
        "- Phase 1：project_map 6 个段落的生成状态\n"
        "- Phase 2：所有模块文档的生成状态\n"
        "- Phase 3：所有子模块文档的生成状态\n\n"
        "当 cache_auto_expire=true（默认）时，会校验 hash 有效性，区分三种状态：\n"
        "- ✅ 已生成且 hash 有效\n"
        "- ⚠️ 已生成但缓存已过期（需重新生成）\n"
        "- ❌ 未生成\n\n"
        "当 cache_auto_expire=false 时，只检查文件存在性（✅/❌ 两态）。\n\n"
        "在以下场景调用：\n"
        "- 初始化开始前，了解当前进度，避免重复生成\n"
        "- 初始化中断后恢复，确认从哪个阶段继续\n"
        "- 不确定某模块/子模块是否已生成或是否过期时\n\n"
        "无需入参，直接调用即可。"
    ),
    input_schema=_SCHEMA,
)
async def init_status() -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / _CODESENSE_DIR
    db_path = project_root / ".codegraph" / "codegraph.db"
    lines: list[str] = ["## CodeSense 初始化状态\n"]

    auto_expire = is_auto_expire_enabled(project_root)

    # ── Phase 1: project_map segments ────────────────────────────────────────
    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    seg_hashes: dict[str, str] = {}
    if auto_expire and db_path.exists():
        with CodeGraphDB(project_root) as db:
            seg_hashes = _compute_segment_hashes(project_root, codesense_dir, saved_modules, db)

    seg_done: list[str] = []
    seg_expired: list[str] = []
    seg_missing: list[str] = []
    for sid in _SEGMENT_IDS:
        content = cache.read_segment(codesense_dir, sid)
        if content is None:
            seg_missing.append(sid)
        elif auto_expire and sid in seg_hashes:
            if cache.is_segment_valid(codesense_dir, sid, seg_hashes[sid]):
                seg_done.append(sid)
            else:
                seg_expired.append(sid)
        else:
            seg_done.append(sid)

    seg_valid_count = len(seg_done)
    lines.append(f"### Phase 1：项目概览（{seg_valid_count}/{len(_SEGMENT_IDS)} 段落有效）")
    for sid in _SEGMENT_IDS:
        if sid in seg_done:
            lines.append(f"- ✅ {sid}")
        elif sid in seg_expired:
            lines.append(f"- ⚠️ {sid}（缓存已过期，需重新生成）")
        else:
            lines.append(f"- ❌ {sid}")
    lines.append("")

    # ── Phase 2 & 3: modules and subgroups ───────────────────────────────────
    if modules_index is None:
        lines.append("### Phase 2：模块文档")
        lines.append("❌ modules_index 不存在，请先完成 Phase 1（02_modules 段落）。")
        lines.append("")
        lines.append("### Phase 3：子模块文档")
        lines.append("❌ 依赖 Phase 2，暂无数据。")
        return "\n".join(lines)

    raw_modules = modules_index.get("modules") or []
    modules_list = [m for m in raw_modules if isinstance(m, dict)]
    total_modules = len(modules_list)

    # Phase 2 hash 校验
    module_hashes: dict[str, str] = {}
    if auto_expire and db_path.exists():
        with CodeGraphDB(project_root) as db:
            for m in modules_list:
                module_hashes[str(m.get("name", ""))] = _compute_module_hash(m, db)

    stored_module_hashes = cache.read_module_hashes(codesense_dir)
    p2_done: list[str] = []
    p2_expired: list[str] = []
    p2_missing: list[str] = []
    for m in modules_list:
        mname = str(m.get("name", ""))
        mkey = cache.safe_key(mname)
        cached_md = cache.read_module(codesense_dir, mkey)
        if cached_md is None:
            p2_missing.append(mname)
        elif auto_expire and mname in module_hashes:
            if stored_module_hashes.get(mkey) == module_hashes[mname]:
                p2_done.append(mname)
            else:
                p2_expired.append(mname)
        else:
            p2_done.append(mname)

    lines.append(f"### Phase 2：模块文档（{len(p2_done)}/{total_modules} 模块有效）")
    if p2_done:
        lines.append("✅ " + " / ".join(p2_done))
    if p2_expired:
        lines.append("⚠️ 缓存过期：" + " / ".join(p2_expired))
    if p2_missing:
        lines.append("❌ 未生成：" + " / ".join(p2_missing))
    lines.append("")

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    total_sgs = 0
    total_sgs_valid = 0
    p3_lines: list[str] = []

    for m in modules_list:
        mname = str(m.get("name", ""))
        mkey = cache.safe_key(mname)
        subgroups = [sg for sg in (m.get("subgroups") or []) if isinstance(sg, dict)]
        if not subgroups:
            continue

        sg_done: list[str] = []
        sg_expired: list[str] = []
        sg_missing: list[str] = []
        stored_sg_hashes = cache.read_submodule_hashes(codesense_dir, mkey)

        # 按模块批量处理：auto_expire 时开一次 DB 计算所有 subgroup hash
        sg_current_hashes: dict[str, str] = {}
        if auto_expire and db_path.exists():
            with CodeGraphDB(project_root) as db:
                for sg in subgroups:
                    sg_name = str(sg.get("name", ""))
                    sg_files = sg.get("files") or []
                    sg_current_hashes[sg_name] = _compute_submodule_hash(list(sg_files), db)

        for sg in subgroups:
            sg_name = str(sg.get("name", ""))
            file_key = f"{mkey}_{sg_name}"
            cached_md = cache.read_submodule(codesense_dir, mkey, file_key)
            if cached_md is None:
                sg_missing.append(sg_name)
            elif auto_expire and sg_name in sg_current_hashes:
                if stored_sg_hashes.get(file_key) == sg_current_hashes[sg_name]:
                    sg_done.append(sg_name)
                else:
                    sg_expired.append(sg_name)
            else:
                sg_done.append(sg_name)

        total_sgs += len(subgroups)
        total_sgs_valid += len(sg_done)
        parts: list[str] = []
        if sg_done:
            parts.append("✅ " + ", ".join(sg_done))
        if sg_expired:
            parts.append("⚠️ 过期 " + ", ".join(sg_expired))
        if sg_missing:
            parts.append("❌ 缺 " + ", ".join(sg_missing))
        p3_lines.append(f"- {mname}：{' | '.join(parts)}")

    lines.append(f"### Phase 3：子模块文档（{total_sgs_valid}/{total_sgs} 子模块有效）")
    lines.extend(p3_lines if p3_lines else ["（无模块定义了子模块划分）"])

    return "\n".join(lines)
