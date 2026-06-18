"""Aggregate file-level edges to a coarser directory view (optional).

Note: with the new `to_package_dependency_dict` in `modules.py`, the
package / module-level view is now part of the core module API. This
file remains for directory-level (filesystem path) aggregation, which is
slightly different from package id for non-Python languages.
"""

from pathlib import PurePosixPath

from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.modules import EXTERNAL_PREFIX, Module, ModuleEdge


def _module_to_dir(file_path: str, max_depth: int | None) -> str:
    parts = PurePosixPath(file_path.replace("\\", "/")).parts[:-1]
    if max_depth is not None:
        parts = parts[:max_depth]
    return "/".join(parts) if parts else "."


def directory_dependencies(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
    include_external: bool = True,
    include_self_loops: bool = False,
) -> dict[str, dict[str, list[str]]]:
    """Group `ModuleEdge`s by (source_dir, target_dir) where dir = file_path's dirname."""
    module_dir: dict[str, str] = {
        m.id: _module_to_dir(m.file_path, max_depth) for m in modules
    }

    out: dict[str, dict[str, set[str]]] = {}
    for e in edges:
        src_dir = module_dir.get(e.source)
        if src_dir is None:
            continue

        if e.is_external:
            if not include_external:
                continue
            tgt_dir = f"{EXTERNAL_PREFIX}{e.target}"
        else:
            tgt_dir_or_none = module_dir.get(e.target)
            if tgt_dir_or_none is None:
                continue
            tgt_dir = tgt_dir_or_none

        if not include_self_loops and src_dir == tgt_dir:
            continue

        bucket = out.setdefault(src_dir, {"imports": set(), "calls": set()})
        bucket[e.kind].add(tgt_dir)

    return {
        src: {kind: sorted(targets) for kind, targets in buckets.items()}
        for src, buckets in sorted(out.items())
    }


def directory_edges(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
    include_external: bool = True,
    include_self_loops: bool = False,
) -> list[tuple[str, str, str]]:
    """Flat list variant of `directory_dependencies`: list of `(src, tgt, kind)`."""
    grouped = directory_dependencies(
        edges,
        modules,
        max_depth=max_depth,
        include_external=include_external,
        include_self_loops=include_self_loops,
    )
    out: list[tuple[str, str, str]] = []
    for src, buckets in grouped.items():
        for kind, targets in buckets.items():
            for t in targets:
                out.append((src, t, kind))
    return out


def directory_symbols(
    db: CodeGraphDB,
    *,
    max_depth: int | None = None,
    kinds: tuple[str, ...] = ("function", "class", "method"),
    max_per_dir: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Return mapping of directory → list of symbols defined in that directory.

    Each symbol entry: {"name": str, "kind": str, "file": str}.
    Used by summarizer to give LLM enough info to describe each directory's role.
    """
    out: dict[str, list[dict[str, str]]] = {}
    for node in db.iter_nodes(kinds=kinds):
        fp = node.file_path.replace("\\", "/")
        d = _module_to_dir(fp, max_depth)
        entries = out.setdefault(d, [])
        if max_per_dir is None or len(entries) < max_per_dir:
            entries.append({"name": node.name, "kind": node.kind, "file": fp})
    return dict(sorted(out.items()))
