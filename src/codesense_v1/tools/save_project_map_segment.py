"""MCP Tool: save_project_map_segment — saves an Agent-generated project_map segment."""

from __future__ import annotations

import json
from typing import Final

from codesense_v1 import cache
from codesense_v1.data import (
    collect_identity_sources,
    compute_architecture_hash,
    compute_dependencies_hash,
    compute_identity_hash,
    list_modules,
    module_dependencies,
)
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.config import get_ignore_paths
from codesense_v1.data.hashes import _sha256
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.summarizer import _resolve_roots_and_aux
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_VALID_SEGMENT_IDS = (
    "01_identity",
    "02_modules",
    "03_constraints",
    "04_flows",
    "05_concepts",
)

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "segment_id": {
            "type": "string",
            "description": "段落 ID：01_identity、02_modules、03_constraints、04_flows 或 05_concepts",
            "enum": list(_VALID_SEGMENT_IDS),
        },
        "content": {
            "type": "string",
            "description": "段落的 Markdown 内容",
        },
    },
    "required": ["segment_id", "content"],
    "additionalProperties": False,
}


@tool(
    name="save_project_map_segment",
    description=(
        "保存 Agent 生成的 project_map 段落内容到缓存。\n\n"
        "仅在 project_map 提示需要生成特定段落时使用。\n"
        "segment_id 必须是 project_map 返回的缺失段落之一。\n"
        "保存后，主 Agent 重新调用 project_map 获取完整概览。"
    ),
    input_schema=_SCHEMA,
)
async def save_project_map_segment_tool(segment_id: str, content: str) -> str:
    if segment_id not in _VALID_SEGMENT_IDS:
        raise InvalidArgumentError(
            f"无效的 segment_id: {segment_id!r}。"
            f"有效值为：{', '.join(_VALID_SEGMENT_IDS)}"
        )
    if not content.strip():
        raise InvalidArgumentError("content 不能为空")

    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / ".codesense"
    db_path = project_root / ".codegraph" / "codegraph.db"
    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )

    with CodeGraphDB(project_root) as db:
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]

        if segment_id == "01_identity":
            sources = collect_identity_sources(project_root, db)
            source_hash = compute_identity_hash(sources)

        elif segment_id == "02_modules":
            roots, _ = _resolve_roots_and_aux(all_file_paths, project_root)
            all_file_paths_l1 = [p for p in all_file_paths if any(p.startswith(r + "/") or p == r for r in roots)]
            # Apply ignore_docs.paths filter (same as project_map.py hash_03)
            _ignore_prefixes_03 = [p.replace("\\", "/").rstrip("/") for p in get_ignore_paths(project_root) if p.strip()]
            if _ignore_prefixes_03:
                all_file_paths_l1 = [
                    p for p in all_file_paths_l1
                    if not any(p == ip or p.startswith(ip + "/") for ip in _ignore_prefixes_03)
                ]
            all_parent_dirs = {
                fp.rsplit("/", 1)[0] for fp in all_file_paths_l1 if "/" in fp
            }
            current_leaf_dirs = sorted({
                d for d in all_parent_dirs
                if not any(other != d and other.startswith(d + "/") for other in all_parent_dirs)
            })
            source_hash = compute_architecture_hash([current_leaf_dirs])

        elif segment_id == "03_constraints":
            _edges_all = [e for e in module_dependencies(db, include_external=False)]
            # Apply ignore_docs.paths filter (same as project_map.py hash_04)
            _ignore_prefixes_04 = [p.replace("\\", "/").rstrip("/") for p in get_ignore_paths(project_root) if p.strip()]
            if _ignore_prefixes_04:
                _edges_all = [
                    e for e in _edges_all
                    if not any(e.source.replace("\\", "/") == ip or e.source.replace("\\", "/").startswith(ip + "/") for ip in _ignore_prefixes_04)
                    and not any(e.target.replace("\\", "/") == ip or e.target.replace("\\", "/").startswith(ip + "/") for ip in _ignore_prefixes_04)
                ]
            source_hash = compute_dependencies_hash(_edges_all)

        elif segment_id == "04_flows":
            all_db_edges = list(db.iter_edges())
            calls_edges = sorted(
                (e.source, e.target)
                for e in all_db_edges
                if getattr(e, 'kind', '') == "calls"
            )
            source_hash = _sha256(json.dumps(calls_edges))

        elif segment_id == "05_concepts":  # 05_concepts
            modules_index = cache.read_modules_index(codesense_dir)
            saved_modules = (modules_index or {}).get("modules", [])
            modules_desc = sorted(
                (str(m.get("name", "")), str(m.get("description", "")))
                for m in saved_modules if isinstance(m, dict)
            )
            # 与 project_map.py 保持一致：modules_desc + hash_03 联动
            # 重算 hash_03（叶子目录 hash，应用 ignore 过滤）
            _all_file_paths_06 = [f.path.replace("\\", "/") for f in db.iter_files()]
            _roots_06, _ = _resolve_roots_and_aux(_all_file_paths_06, project_root)
            _file_paths_l1_06 = [p for p in _all_file_paths_06 if any(p.startswith(r + "/") or p == r for r in _roots_06)]
            _ignore_prefixes_06 = [p.replace("\\", "/").rstrip("/") for p in get_ignore_paths(project_root) if p.strip()]
            if _ignore_prefixes_06:
                _file_paths_l1_06 = [
                    p for p in _file_paths_l1_06
                    if not any(p == ip or p.startswith(ip + "/") for ip in _ignore_prefixes_06)
                ]
            _all_parent_dirs_06 = {
                fp.rsplit("/", 1)[0] for fp in _file_paths_l1_06 if "/" in fp
            }
            _current_leaf_dirs_06 = sorted({
                d for d in _all_parent_dirs_06
                if not any(other != d and other.startswith(d + "/") for other in _all_parent_dirs_06)
            })
            _hash_03_06 = compute_architecture_hash([_current_leaf_dirs_06])
            source_hash = _sha256(json.dumps(modules_desc) + _hash_03_06)

    cache.write_segment(codesense_dir, segment_id, content, source_hash)
    return f"段落 `{segment_id}` 已保存（{len(content)} 字符）。重新调用 `project_map` 获取完整概览。"
