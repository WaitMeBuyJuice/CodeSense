"""Summarizer: coordinates Data Layer + Cache to produce Markdown summaries."""

from __future__ import annotations

import difflib
import hashlib
import os
import re
from pathlib import Path

from codesense_v1 import cache
from codesense_v1.data.aggregate import directory_dependencies, directory_symbols
from codesense_v1.data.architecture import (
    DirCentrality,
    compute_centrality,
    cross_dir_public_api,
    external_dependencies_by_dir,
    find_cycles,
    topological_layers,
)
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.modules import list_modules, module_dependencies
from codesense_v1.errors import InvalidArgumentError

_CODESENSE_DIR_NAME = ".codesense"
_EXTERNAL_PREFIX = "external::"
_DESC_MAX_LEN = 60
_NAME_MIN_LEN = 2
_NAME_MAX_LEN = 20
_FUZZY_CUTOFF = 0.85
_FALLBACK_MODULE_NAME = "其他"
_FALLBACK_MODULE_DESC = "未归类目录"
_INCLUDE_DIRS_ENV = "CODESENSE_INCLUDE_DIRS"
_CACHE_AUTO_EXPIRE_ENV = "CODESENSE_CACHE_AUTO_EXPIRE"
_DEFAULT_INCLUDE_ROOTS: tuple[str, ...] = ("src",)

# Directories that should be listed briefly in project_map but not deeply analysed.
_AUXILIARY_DIR_NAMES: frozenset[str] = frozenset(
    {
        "test", "tests", "testing", "__tests__", "spec", "specs",
        "script", "scripts",
        "doc", "docs", "documentation", "dev-docs", "devdocs",
        "example", "examples", "sample", "samples", "demo", "demos",
    }
)

# Human-readable category labels for auxiliary dirs.
_AUXILIARY_CATEGORY: dict[str, str] = {
    "test": "测试代码", "tests": "测试代码", "testing": "测试代码",
    "__tests__": "测试代码", "spec": "测试代码", "specs": "测试代码",
    "script": "辅助脚本", "scripts": "辅助脚本",
    "doc": "文档", "docs": "文档", "documentation": "文档",
    "dev-docs": "文档", "devdocs": "文档",
    "example": "示例代码", "examples": "示例代码",
    "sample": "示例代码", "samples": "示例代码",
    "demo": "示例代码", "demos": "示例代码",
}

# Regex to detect root-level filenames mistakenly treated as directories
# (e.g. "vitest.config.mts/").
_HAS_EXTENSION_RE = re.compile(r"\.[a-zA-Z0-9]+$")


def _is_auto_expire_enabled() -> bool:
    """Return True iff CODESENSE_CACHE_AUTO_EXPIRE is explicitly set to 'true' (case-insensitive)."""
    return os.environ.get(_CACHE_AUTO_EXPIRE_ENV, "").strip().lower() == "true"


def _get_include_roots() -> tuple[str, ...] | None:
    """Return user-configured include roots, or ``None`` if not configured.

    Read from ``CODESENSE_INCLUDE_DIRS`` (comma-separated).  ``None`` means
    "auto-detect from DB"; an explicit empty string also returns ``None``
    (treated as not configured).
    """
    raw = os.environ.get(_INCLUDE_DIRS_ENV, "")
    parts = [
        r.strip().replace("\\", "/").rstrip("/")
        for r in raw.split(",")
        if r.strip()
    ]
    parts = [p for p in parts if p]
    return tuple(parts) if parts else None


def _is_auxiliary_dir(name: str) -> str | None:
    """Return a category label if *name* is an auxiliary directory, else ``None``.

    Matches exact names and compound names whose tokens (split by ``_`` or ``-``)
    include a known auxiliary pattern, e.g. ``js_tests`` → tests token → "测试代码".
    """
    name_lower = name.lower()
    if name_lower in _AUXILIARY_DIR_NAMES:
        return _AUXILIARY_CATEGORY.get(name_lower, "辅助代码")
    # Word-level match: "js_tests", "e2e-tests", "playwright-spec", etc.
    for token in re.split(r"[_\-]", name_lower):
        if token in _AUXILIARY_DIR_NAMES:
            return _AUXILIARY_CATEGORY.get(token, "辅助代码")
    return None


def _classify_top_dirs(
    all_file_paths: list[str],
) -> tuple[tuple[str, ...], list[dict[str, object]]]:
    """Classify top-level directories from *all_file_paths* into L1 and L2.

    Returns:
        l1_roots: directories to include in deep module analysis.
        aux_dirs: list of ``{"name", "file_count", "category"}`` dicts (L2).

    L3 (noise) is silently dropped:
        - directories starting with ``.``
        - names that look like filenames (contain a file extension, e.g.
          ``vitest.config.mts``)
    """
    import collections

    counts: dict[str, int] = collections.Counter()
    for fp in all_file_paths:
        top = fp.split("/")[0] if "/" in fp else ""
        if top:
            counts[top] += 1

    l1: list[str] = []
    aux: list[dict[str, object]] = []

    for name, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        # L3: starts with '.' or looks like a filename
        if name.startswith(".") or _HAS_EXTENSION_RE.search(name):
            continue
        name_lower = name.lower()
        category = _is_auxiliary_dir(name)
        if category is not None:
            aux.append({"name": name, "file_count": cnt, "category": category})
        else:
            l1.append(name)

    return tuple(l1), aux


def _resolve_roots_and_aux(
    all_file_paths: list[str],
) -> tuple[tuple[str, ...], list[dict[str, object]]]:
    """Return (include_roots, auxiliary_dirs) for the current run.

    Priority:
    1. User-configured ``CODESENSE_INCLUDE_DIRS`` → use as L1 roots;
       still detect L2 from DB paths under non-configured dirs.
    2. DB has files under ``src/`` → use ``("src",)`` (legacy default).
    3. Auto-detect from DB.
    """
    user_roots = _get_include_roots()

    if user_roots:
        # User explicitly configured roots: use them as L1, discover L2 from the rest.
        other_paths = [
            p for p in all_file_paths
            if not any(p.startswith(r + "/") or p == r for r in user_roots)
        ]
        _, aux = _classify_top_dirs(other_paths)
        return user_roots, aux

    # Check if default "src/" has any files
    has_src = any(p.startswith("src/") for p in all_file_paths)
    if has_src:
        _, aux = _classify_top_dirs(
            [p for p in all_file_paths if not p.startswith("src/")]
        )
        return _DEFAULT_INCLUDE_ROOTS, aux

    # Auto-detect
    return _classify_top_dirs(all_file_paths)


def _is_under_roots(d: str, roots: tuple[str, ...]) -> bool:
    """Return True if directory *d* equals or is nested under any root."""
    d_norm = d.replace("\\", "/").rstrip("/")
    return any(d_norm == r or d_norm.startswith(r + "/") for r in roots)


def _filter_dir_deps(
    dir_deps: dict[str, dict[str, list[str]]], roots: tuple[str, ...]
) -> dict[str, dict[str, list[str]]]:
    """Keep only edges where both source and target are under *roots*."""
    out: dict[str, dict[str, list[str]]] = {}
    for src, buckets in dir_deps.items():
        if not _is_under_roots(src, roots):
            continue
        kept_buckets: dict[str, list[str]] = {}
        for kind, targets in buckets.items():
            kept = [t for t in targets if _is_under_roots(t, roots)]
            if kept:
                kept_buckets[kind] = kept
        if kept_buckets:
            out[src] = kept_buckets
    return out


def _leaf_dirs_from_files(file_paths: list[str]) -> set[str]:
    """Return the set of leaf directories (those directly containing source files).

    Used to enrich ``valid_dirs`` so directories whose files define no
    function/class (e.g. constants-only modules like ``schemas/``) are still
    eligible for module assignment.
    """
    raw: set[str] = set()
    for fp in file_paths:
        fp_norm = fp.replace("\\", "/")
        if "/" not in fp_norm:
            continue
        raw.add(fp_norm.rsplit("/", 1)[0])
    return {
        d
        for d in raw
        if not any(other != d and other.startswith(d + "/") for other in raw)
    }


def _normalize_dir(
    d: str,
    valid_dirs: set[str] | None,
) -> tuple[str | None, bool]:
    """Clean a single directory string.

    Returns:
        (normalized_dir, is_fuzzy): ``normalized_dir`` is ``None`` if the dir
        cannot be matched; ``is_fuzzy`` is ``True`` when the result came from
        fuzzy matching rather than an exact hit.
    """
    d = d.strip().strip("`").strip("'").strip('"').rstrip("/").replace("\\", "/")
    if not d:
        return None, False
    if not valid_dirs:
        return d, False
    if d in valid_dirs:
        return d, False
    matches = difflib.get_close_matches(d, valid_dirs, n=1, cutoff=_FUZZY_CUTOFF)
    return (matches[0], True) if matches else (None, False)


def _dedup_description(desc: str) -> str:
    """Split desc by Chinese/ASCII commas, dedup preserving order, truncate."""
    parts = [p.strip() for p in re.split(r"[、,，]", desc) if p.strip()]
    if not parts:
        return desc.strip()[:_DESC_MAX_LEN]
    return "、".join(dict.fromkeys(parts))[:_DESC_MAX_LEN]


# ---------- public API -------------------------------------------------------


def _compute_module_hash(entry: dict[str, object], db: CodeGraphDB) -> str:
    """Return a stable hash representing this module's current content.

    Hash input: sorted file list + sorted symbol fingerprints (file:name:kind:sig).
    Changes when files are added/removed or any symbol signature changes.
    """
    files = sorted(str(f) for f in (entry.get("files") or []))
    file_set = set(files)
    symbols: list[str] = []
    for node in db.iter_nodes(kinds=("function", "class", "method")):
        fp = node.file_path.replace("\\", "/")
        if fp in file_set:
            symbols.append(f"{fp}:{node.name}:{node.kind}:{node.signature or ''}")
    symbols.sort()
    content = "\n".join(files + symbols)
    return hashlib.sha1(content.encode("utf-8")).hexdigest()  # noqa: S324


async def get_project_map_prompt(project_root: Path) -> str:
    """Return the prompt that would be sent to LLM for project-level module mapping.

    Raises:
        FileNotFoundError: if the CodeGraph DB does not exist.
    """
    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=True)
        edges_internal = [e for e in edges_all if not e.is_external]
        dir_deps = directory_dependencies(
            edges_internal, modules_data, include_external=False, include_self_loops=False
        )
        dir_syms = directory_symbols(db, max_per_dir=50)
        all_file_paths: list[str] = [f.path.replace("\\", "/") for f in db.iter_files()]

    roots, _ = _resolve_roots_and_aux(all_file_paths)
    dir_syms = {d: s for d, s in dir_syms.items() if _is_under_roots(d, roots)}
    dir_deps = _filter_dir_deps(dir_deps, roots)

    centrality = compute_centrality(edges_all, modules_data)
    layers = topological_layers(edges_internal, modules_data)
    cycles = find_cycles(edges_internal, modules_data)
    ext_by_dir = external_dependencies_by_dir(edges_all, modules_data)

    return _build_project_map_prompt(
        dir_deps,
        dir_syms,
        roots=roots,
        centrality=centrality,
        layers=layers,
        cycles=cycles,
        ext_by_dir=ext_by_dir,
    )


async def submit_project_map(project_root: Path, response: str) -> str:
    """Process a pipe-delimited module-list *response* and write project_map cache.

    *response* must follow the same format the project_map LLM prompt requests::

        模块名|一句话职责|目录1,目录2

    Returns the rendered ``project_map.md`` Markdown.

    Raises:
        FileNotFoundError: if the CodeGraph DB does not exist.
        InvalidArgumentError: if *response* cannot be parsed into any modules.
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME
    db_path = project_root / ".codegraph" / "codegraph.db"
    current_hash = cache.db_hash(db_path)

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges = module_dependencies(db, include_external=False)
        dir_deps = directory_dependencies(
            edges, modules_data, include_external=False, include_self_loops=False
        )
        dir_syms = directory_symbols(db, max_per_dir=50)
        all_file_paths: list[str] = [f.path.replace("\\", "/") for f in db.iter_files()]

    roots, aux_dirs = _resolve_roots_and_aux(all_file_paths)
    all_file_paths_l1 = [
        p for p in all_file_paths if any(p.startswith(r + "/") for r in roots)
    ]
    dir_deps_l1 = _filter_dir_deps(dir_deps, roots)
    dir_syms_l1 = {d: s for d, s in dir_syms.items() if _is_under_roots(d, roots)}
    valid_dirs: set[str] = (
        set(dir_deps_l1.keys())
        | set(dir_syms_l1.keys())
        | _leaf_dirs_from_files(all_file_paths_l1)
    )

    warnings: list[str] = []
    modules_json = _parse_modules_text(response, valid_dirs, warnings=warnings)
    if not modules_json:
        raise InvalidArgumentError(
            "解析失败：无法从响应中提取有效模块。"
            "请确保每行格式为「模块名|职责|目录」，不含多余内容。"
        )

    expanded = _expand_module_files(modules_json, all_file_paths_l1)
    cache.write_modules_index(codesense_dir, expanded, current_hash, aux_dirs=aux_dirs)
    markdown = _render_project_map_markdown(expanded, dir_deps_l1, aux_dirs=aux_dirs)
    cache.write_project_map(codesense_dir, markdown, current_hash)

    if warnings:
        warning_block = "\n\n---\n\n## ⚠️ 解析警告\n\n" + "\n".join(f"- {w}" for w in warnings)
        return markdown + warning_block
    return markdown


async def get_module_prompt(project_root: Path, module_name: str) -> str:
    """Return the prompt that would be sent to LLM for a specific module summary.

    Raises:
        InvalidArgumentError: if modules_index is missing or module_name not found.
        FileNotFoundError: if the CodeGraph DB does not exist.
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME

    index = cache.read_modules_index(codesense_dir)
    if index is None:
        raise InvalidArgumentError(
            "参数错误：尚未生成模块划分，请先调用 project_map 生成模块划分"
        )

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
            f"参数错误：模块 '{module_name}' 不存在。可用模块：{', '.join(available)}"
        )

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=True)
        edges_internal = [e for e in edges_all if not e.is_external]
        dir_deps = directory_dependencies(
            edges_internal, modules_data, include_external=False, include_self_loops=False
        )
        files_raw = entry.get("files")
        module_file_set = {str(f) for f in (files_raw if isinstance(files_raw, list) else [])}
        file_symbols: dict[str, list[str]] = {}
        for node in db.iter_nodes(kinds=("function", "class", "method")):
            fp = node.file_path.replace("\\", "/")
            if fp not in module_file_set:
                continue
            sig = node.signature or node.name
            file_symbols.setdefault(fp, []).append(
                f"- `{node.name}` ({node.kind}): {sig}"
            )
        public_api_all = cross_dir_public_api(db)
        ext_by_dir_all = external_dependencies_by_dir(edges_all, modules_data)

    dirs_raw = entry.get("directories")
    directories: list[str] = [str(d) for d in (dirs_raw if isinstance(dirs_raw, list) else [])]
    dirs_set = set(directories)

    # Flatten public symbols for this module's directories
    pub_syms: list[str] = []
    for d in directories:
        for sym in public_api_all.get(d, []):
            if sym not in pub_syms:
                pub_syms.append(sym)
    pub_syms.sort()

    # Aggregate external deps for this module's directories
    ext_deps: set[str] = set()
    for d in directories:
        ext_deps.update(ext_by_dir_all.get(d, []))

    return _build_module_prompt(
        entry,
        dir_deps,
        file_symbols,
        public_symbols=pub_syms,
        external_deps=sorted(ext_deps),
    )


def save_module_summary(project_root: Path, module_name: str, summary: str) -> None:
    """Write *summary* to cache for *module_name*, updating per-module hash.

    Raises:
        FileNotFoundError: if the CodeGraph DB does not exist.
        InvalidArgumentError: if modules_index is missing or module_name not found.
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME
    db_path = project_root / ".codegraph" / "codegraph.db"
    current_hash = cache.db_hash(db_path)
    mkey = cache.safe_key(module_name)

    index = cache.read_modules_index(codesense_dir)
    if index is None:
        raise InvalidArgumentError(
            "参数错误：尚未生成模块划分，请先调用 project_map 生成模块划分"
        )
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
            f"参数错误：模块 '{module_name}' 不存在。可用模块：{', '.join(available)}"
        )

    with CodeGraphDB(project_root) as db:
        module_hash = _compute_module_hash(entry, db)

    cache.write_module(codesense_dir, mkey, module_name, summary, current_hash, module_hash)


def _parse_modules_text(
    response: str,
    valid_dirs: set[str] | None = None,
    warnings: list[str] | None = None,
) -> list[dict[str, object]]:
    """Parse pipe-delimited module list from LLM/Agent response.

    Expected line format::

        模块名|一句话职责|目录1,目录2,...

    When *valid_dirs* is provided, every directory must either match a member
    of *valid_dirs* exactly or be within fuzzy-match distance; otherwise it is
    dropped. Description fields are split by Chinese/ASCII commas,
    deduplicated while preserving order, and truncated to 60 chars to fix the
    "add、add、list" class of LLM hallucinations.

    When *warnings* is provided (a mutable list), it is populated with:
    - fuzzy-correction messages (directory was rewritten)
    - drop messages (directory was already claimed by another module)
    - skip messages (module had no valid directory)

    Malformed lines are silently skipped; duplicate names and overlapping
    directories are deduplicated.
    """
    modules: list[dict[str, object]] = []
    seen_names: set[str] = set()
    seen_dirs: list[str] = []

    for line in response.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        name, desc = parts[0], parts[1]
        if not name or name.lower() in seen_names:
            continue
        if not (_NAME_MIN_LEN <= len(name) <= _NAME_MAX_LEN):
            continue
        desc = _dedup_description(desc)
        dirs_str = parts[2]
        dirs: list[str] = []
        for raw in dirs_str.split(","):
            normalized, is_fuzzy = _normalize_dir(raw, valid_dirs)
            if normalized is not None:
                dirs.append(normalized)
                if is_fuzzy and warnings is not None:
                    raw_clean = raw.strip()
                    warnings.append(
                        f"⚠️ 目录修正：「{name}」的目录 `{raw_clean}` "
                        f"未精确匹配，已自动修正为 `{normalized}`"
                    )
            elif warnings is not None and raw.strip():
                warnings.append(
                    f"⚠️ 目录无效：「{name}」的目录 `{raw.strip()}` "
                    f"在代码库中不存在，已忽略"
                )
        clean_dirs: list[str] = []
        for d in dirs:
            if d not in seen_dirs:
                clean_dirs.append(d)
                seen_dirs.append(d)
            elif warnings is not None:
                warnings.append(
                    f"⚠️ 目录冲突：「{name}」的目录 `{d}` "
                    f"已被其他模块占用，已忽略"
                )
        if not clean_dirs:
            if warnings is not None:
                warnings.append(
                    f"⚠️ 模块跳过：「{name}」没有有效目录，整个模块被跳过"
                )
            continue
        seen_names.add(name.lower())
        modules.append({"name": name, "description": desc, "directories": clean_dirs})

    return modules


# ---------- private: data expansion + rendering ------------------------------


def _expand_module_files(
    modules_json: list[dict[str, object]],
    all_file_paths: list[str],
) -> list[dict[str, object]]:
    """Expand ``directories`` in each module entry to a concrete ``files`` list.

    When a module claims a parent directory (e.g. ``src/core``) and another
    module explicitly claims a sub-directory (e.g. ``src/core/utils``), the
    parent module's files exclude the sub-directory's files so there is no
    overlap between modules.
    """
    # Collect all claimed directories across all modules
    all_claimed: set[str] = {
        str(d).rstrip("/")
        for m in modules_json
        for d in (m.get("directories") or [])
        if d
    }

    result: list[dict[str, object]] = []
    for m in modules_json:
        dirs_raw = m.get("directories")
        dirs: list[str] = [
            str(d).rstrip("/")
            for d in (dirs_raw if isinstance(dirs_raw, list) else [])
            if d
        ]
        # Sub-directories that are explicitly claimed by OTHER modules
        excluded: set[str] = {
            c for c in all_claimed
            if c not in set(dirs)
            and any(c.startswith(d + "/") for d in dirs)
        }
        matched: list[str] = []
        for fp in all_file_paths:
            fp_norm = fp.rstrip("/")
            for d in dirs:
                if fp_norm == d or fp_norm.startswith(d + "/"):
                    # Skip if this file belongs to an excluded sub-directory
                    if not any(
                        fp_norm == ex or fp_norm.startswith(ex + "/")
                        for ex in excluded
                    ):
                        matched.append(fp)
                    break
        result.append(
            {
                "name": m.get("name", ""),
                "description": m.get("description", ""),
                "directories": dirs,
                "files": sorted(matched),
            }
        )
    return result


def _render_project_map_markdown(
    modules: list[dict[str, object]],
    dir_deps: dict[str, dict[str, list[str]]],
    aux_dirs: list[dict[str, object]] | None = None,
) -> str:
    """Render project_map.md from structured module data (no LLM call)."""
    lines: list[str] = [
        "# 项目架构概览",
        "",
        "> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。",
        "",
        "## 模块列表",
        "",
        "| 模块 | 职责 | 主要目录 |",
        "|------|------|---------|",
    ]

    dir_to_module: dict[str, str] = {}
    for m in modules:
        dirs_raw = m.get("directories")
        for d in (dirs_raw if isinstance(dirs_raw, list) else []):
            dir_to_module[str(d).rstrip("/")] = str(m.get("name", ""))

    for m in modules:
        name = str(m.get("name", ""))
        desc = str(m.get("description", ""))
        dirs_raw2 = m.get("directories")
        dirs_list: list[object] = dirs_raw2 if isinstance(dirs_raw2, list) else []
        dirs_str = ", ".join(f"`{d}`" for d in dirs_list) if dirs_list else "—"
        lines.append(f"| {name} | {desc} | {dirs_str} |")

    lines.extend(["", "## 模块间依赖", ""])

    dep_rows: list[tuple[str, str, str]] = []
    for src_dir, buckets in sorted(dir_deps.items()):
        src_mod = dir_to_module.get(src_dir.rstrip("/"))
        if src_mod is None:
            continue
        for kind, targets in buckets.items():
            for tgt in targets:
                if tgt.startswith(_EXTERNAL_PREFIX):
                    continue
                tgt_mod = dir_to_module.get(tgt.rstrip("/"))
                if tgt_mod is None or tgt_mod == src_mod:
                    continue
                dep_rows.append((src_mod, tgt_mod, kind))

    seen_deps: set[tuple[str, str]] = set()
    unique_deps: list[tuple[str, str, str]] = []
    for src_mod, tgt_mod, kind in dep_rows:
        key = (src_mod, tgt_mod)
        if key not in seen_deps:
            seen_deps.add(key)
            unique_deps.append((src_mod, tgt_mod, kind))

    if unique_deps:
        lines.extend(
            [
                "| 来源模块 | 依赖模块 | 依赖类型 |",
                "|----------|----------|----------|",
            ]
        )
        for src_mod, tgt_mod, kind in sorted(unique_deps):
            lines.append(f"| {src_mod} | {tgt_mod} | {kind} |")
    else:
        lines.append("（无跨模块依赖）")

    if aux_dirs:
        lines.extend(
            [
                "",
                "## 其他目录",
                "",
                "| 目录 | 类型 | 文件数 |",
                "|------|------|--------|",
            ]
        )
        for aux in aux_dirs:
            name = str(aux.get("name", ""))
            category = str(aux.get("category", "辅助代码"))
            file_count = aux.get("file_count", "?")
            lines.append(f"| `{name}` | {category} | {file_count} |")

    return "\n".join(lines)


# ---------- private: prompt builders -----------------------------------------


def _build_project_map_prompt(
    dir_deps: dict[str, dict[str, list[str]]],
    dir_syms: dict[str, list[dict[str, str]]],
    roots: tuple[str, ...] = _DEFAULT_INCLUDE_ROOTS,
    *,
    centrality: dict[str, DirCentrality] | None = None,
    layers: list[list[str]] | None = None,
    cycles: list[list[str]] | None = None,
    ext_by_dir: dict[str, list[str]] | None = None,
) -> str:
    all_dirs = sorted(set(dir_deps.keys()) | set(dir_syms.keys()))
    all_dirs_set = set(all_dirs)
    n_dirs = len(all_dirs)
    roots_str = "、".join(f"`{r}`" for r in roots)

    # ---- directory section: symbol count + centrality + external deps -------
    dir_lines: list[str] = []
    for d in all_dirs:
        syms = dir_syms.get(d, [])
        sym_names = ", ".join(s["name"] for s in syms)

        # (←fan_in →fan_out) centrality annotation
        cent_str = ""
        if centrality and d in centrality:
            c = centrality[d]
            cent_str = f"  (←{c.fan_in} →{c.fan_out})"

        # external deps annotation (up to 5 to stay compact)
        ext_str = ""
        if ext_by_dir and d in ext_by_dir:
            deps = ext_by_dir[d]
            if deps:
                ext_str = "  外部: " + ", ".join(deps[:5])
                if len(deps) > 5:
                    ext_str += f" …+{len(deps) - 5}"

        sym_part = f"  [{sym_names}]" if sym_names else ""
        dir_lines.append(f"- `{d}`: {len(syms)} 个符号{cent_str}{ext_str}{sym_part}")
    dir_section = "\n".join(dir_lines) if dir_lines else "（无目录数据）"

    # ---- architecture layers section ----------------------------------------
    layer_section_str = ""
    if layers:
        filtered_layers = [
            sorted(d for d in layer if d in all_dirs_set)
            for layer in layers
        ]
        filtered_layers = [layer for layer in filtered_layers if layer]
        if filtered_layers:
            layer_lines: list[str] = []
            last_idx = len(filtered_layers) - 1
            for i, layer in enumerate(filtered_layers):
                dirs_str = ", ".join(f"`{d}`" for d in layer)
                if i == 0:
                    label = "第 0 层（基础层，被其他层依赖，无内部出边）"
                elif i == last_idx:
                    label = f"第 {i} 层（入口层，不被其他层依赖）"
                else:
                    label = f"第 {i} 层"
                layer_lines.append(f"- {label}：{dirs_str}")
            layer_section_str = (
                "\n\n### 架构层级（拓扑排序，可辅助理解各目录在调用栈中的位置）\n"
                + "\n".join(layer_lines)
            )

    # ---- cycle warning -------------------------------------------------------
    cycle_warning_str = ""
    if cycles:
        root_cycles = [
            comp for comp in cycles
            if any(d in all_dirs_set for d in comp)
        ]
        if root_cycles:
            cycle_lines = [
                "  " + " ↔ ".join(f"`{d}`" for d in comp)
                for comp in root_cycles
            ]
            cycle_warning_str = (
                "\n- ⚠️ **循环依赖警告**：以下目录组存在相互依赖，划分时可合并为同一模块，"
                "或在描述中注明耦合关系：\n" + "\n".join(cycle_lines)
            )

    # ---- dependency section --------------------------------------------------
    dep_lines: list[str] = []
    for src, buckets in sorted(dir_deps.items()):
        all_targets: set[str] = set()
        for kind, targets in buckets.items():
            for t in targets:
                if not t.startswith(_EXTERNAL_PREFIX):
                    all_targets.add(f"{t} [{kind}]")
        if all_targets:
            dep_lines.append(f"- `{src}` → {', '.join(sorted(all_targets))}")
    dep_section = "\n".join(dep_lines) if dep_lines else "（无内部依赖）"

    return (
        "# 项目模块划分请求\n\n"
        "你是一位软件架构师。根据以下项目结构数据，请你推断项目的逻辑模块划分。\n\n"
        "## 上下文\n"
        f"- 以下目录均位于产品源代码根（{roots_str}）下，是项目的核心实现，"
        "已排除测试与脚手架。\n"
        f"- 项目共 {n_dirs} 个目录，**默认假设：每个目录代表一个独立模块**，"
        f"预期产出约 {n_dirs} 个模块。\n"
        "- 仅当两个目录承担**完全相同**的职责且强耦合时，才可合并为同一模块；"
        "语义不同的目录（如 errors、llm、cache）必须独立成模块。\n"
        "- 目录条目中 `(←N →M)` 表示：该目录被 N 个其他目录依赖（fan-in），"
        "自身依赖 M 个其他目录（fan-out）。fan-in 高 → 基础设施；fan-out 高且 fan-in 低 → 入口/编排层。"
        f"{cycle_warning_str}\n\n"
        "## 输入数据\n\n"
        "### 目录结构（含代表性符号，最多 50 个/目录）\n"
        f"{dir_section}"
        f"{layer_section_str}\n\n"
        "### 目录间依赖（仅内部依赖）\n"
        f"{dep_section}\n\n"
        "## 输出格式\n\n"
        "每行一个模块，用竖线（|）分隔三列：\n"
        "  模块名|一句话职责|所属目录（多目录用英文逗号分隔）\n\n"
        "示例行：\n"
        "  缓存层|管理 .codesense 缓存文件的读写与失效|src/codesense_v1/cache\n"
        "  数据层|封装 CodeGraph DB 查询与模块依赖聚合|src/data,src/models\n\n"
        "规则：\n"
        "- 每个模块占一行\n"
        "- 不要输出标题行、编号、Markdown 格式或任何其他内容\n"
        "- 目录路径为相对项目根的路径\n"
        "- 同一目录不归属多个模块\n"
        "- 必须覆盖所有目录\n"
        "- **禁止把所有目录归到单一模块**（这是错误划分；至少 2 个模块）\n"
        "- 模块名 2-20 个字符；不得包含重复词或与描述列粘连\n"
    )


def _build_module_prompt(
    entry: dict[str, object],
    dir_deps: dict[str, dict[str, list[str]]],
    file_symbols: dict[str, list[str]],
    *,
    public_symbols: list[str] | None = None,
    external_deps: list[str] | None = None,
) -> str:
    name = str(entry.get("name", ""))
    description = str(entry.get("description", ""))
    files_raw = entry.get("files")
    files: list[str] = [str(f) for f in (files_raw if isinstance(files_raw, list) else [])]
    dirs_raw = entry.get("directories")
    directories: list[str] = [str(d) for d in (dirs_raw if isinstance(dirs_raw, list) else [])]

    module_dirs = set(directories)
    outbound: set[str] = set()
    inbound: set[str] = set()
    for src_dir, buckets in dir_deps.items():
        all_targets: set[str] = set()
        for targets in buckets.values():
            all_targets.update(targets)
        if src_dir in module_dirs:
            outbound.update(
                t
                for t in all_targets
                if t not in module_dirs and not t.startswith(_EXTERNAL_PREFIX)
            )
        for tgt in all_targets:
            if tgt in module_dirs and src_dir not in module_dirs:
                inbound.add(src_dir)

    # Build per-file symbol section
    sym_lines: list[str] = []
    for fp in sorted(files):
        syms = file_symbols.get(fp, [])
        sym_lines.append(f"\n**`{fp}`**")
        if syms:
            sym_lines.extend(syms)
        else:
            sym_lines.append("  （无符号）")
    symbols_txt = "\n".join(sym_lines) if sym_lines else "（无符号数据）"

    files_txt = "\n".join(f"- `{f}`" for f in sorted(files)) or "（无）"
    outbound_txt = "\n".join(f"- `{d}`" for d in sorted(outbound)) or "（无）"
    inbound_txt = "\n".join(f"- `{d}`" for d in sorted(inbound)) or "（无）"

    # Graph-derived public API (cross-directory imports, language-agnostic)
    pub_api_txt = (
        "\n".join(f"- `{s}`" for s in public_symbols)
        if public_symbols
        else "（暂无外部调用记录——该模块可能为纯内部实现）"
    )

    # External library dependencies
    ext_deps_txt = (
        "\n".join(f"- `{d}`" for d in external_deps)
        if external_deps
        else "（无）"
    )

    return (
        "# 模块详细分析请求\n\n"
        "你是一位软件架构师，请根据以下模块结构数据，生成一份**模块理解文档**。\n\n"
        "## 要求\n\n"
        "输出为 Markdown 格式，包含：\n"
        "1. **概述**：该模块的核心职责（不超过 50 字）\n"
        "2. **对外接口**：直接使用下方「对外接口（图推导）」列出的符号，"
        "逐一说明其用途；若该列表为空，可从「模块内符号」中依据语言惯例补充推断\n"
        "3. **内部文件**：该模块包含的文件列表，每个文件一句话说明作用\n"
        "4. **依赖关系**：上游（该模块依赖的目录）/ 下游（依赖该模块的目录）\n"
        "5. **外部依赖**：该模块引入的第三方或标准库（来自下方「外部依赖库」）\n\n"
        "## 模块数据\n\n"
        f"### 模块名称\n{name}\n\n"
        f"### project_map 中的初步描述\n{description}\n\n"
        f"### 包含文件\n{files_txt}\n\n"
        f"### 对外接口（图推导：被其他目录实际 import 的符号，无语言偏见）\n"
        f"{pub_api_txt}\n\n"
        f"### 外部依赖库（该模块直接引入的第三方/标准库）\n"
        f"{ext_deps_txt}\n\n"
        f"### 模块内符号（函数/类/方法，含签名）\n{symbols_txt}\n\n"
        f"### 上游依赖（该模块依赖的目录）\n{outbound_txt}\n\n"
        f"### 下游依赖（依赖该模块的目录）\n{inbound_txt}\n"
    )
