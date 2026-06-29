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
from codesense_v1.data.docstrings import (
    extract_file_docstring,
    extract_symbol_docstrings,
    is_enabled as _docstrings_enabled,
)
from codesense_v1.data.files import DirectoryNode
from codesense_v1.data.modules import list_modules, module_dependencies
from codesense_v1.data.project_info import IdentitySource
from codesense_v1.data.ref_docs import ref_docs_prompt_section
from codesense_v1.data.structure import (
    AUXILIARY_CATEGORY as _AUXILIARY_CATEGORY,
    AUXILIARY_DIR_NAMES as _AUXILIARY_DIR_NAMES,
    TopLevelDir,
    auxiliary_category as _is_auxiliary_dir_cat,
    classify_top_dirs as _classify_top_dirs_data,
)
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


# Regex to detect root-level filenames mistakenly treated as directories
# (e.g. "vitest.config.mts/").
_HAS_EXTENSION_RE = re.compile(r"\.[a-zA-Z0-9]+$")

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "typescriptreact",
    ".js": "javascript", ".jsx": "javascriptreact",
    ".go": "go",
    ".rs": "rust",
    ".erl": "erlang", ".hrl": "erlang",
    ".rb": "ruby",
    ".sh": "shell", ".bash": "bash",
}


def _lang_from_path(path: str) -> str:
    """Infer language from file extension; returns empty string if unknown."""
    return _EXT_TO_LANG.get(Path(path).suffix.lower(), "")


# Symbol names that are too generic to convey semantics without a docstring.
_GENERIC_SYMBOL_NAMES: frozenset[str] = frozenset(
    {
        "run", "execute", "process", "handle", "do", "call", "invoke",
        "start", "stop", "init", "setup", "teardown", "main",
        "update", "create", "delete", "get", "set", "load", "save",
        "build", "parse", "validate", "check", "test",
    }
)

# Directory-name fragments that suggest an entry / adapter layer.
_ENTRY_LAYER_HINTS: frozenset[str] = frozenset(
    {"tool", "tools", "server", "cli", "cmd", "api", "main", "bin", "app", "handler", "endpoint"}
)


def _is_generic_name(name: str) -> bool:
    """Return True if *name* is too generic to understand without a docstring."""
    base = name.lstrip("_").lower()
    return (
        base in _GENERIC_SYMBOL_NAMES
        or any(base.startswith(p) for p in ("on_", "do_", "handle_"))
    )


def _looks_like_entry_layer(directories: list[str]) -> bool:
    """Return True if any directory path fragment suggests an entry/service layer."""
    for d in directories:
        for part in d.replace("\\", "/").split("/"):
            if part.lower() in _ENTRY_LAYER_HINTS:
                return True
    return False


def _is_auto_expire_enabled() -> bool:
    """Return False only when CODESENSE_CACHE_AUTO_EXPIRE is explicitly set to 'false'.

    Defaults to True — cache expires when DB hash changes.
    Set CODESENSE_CACHE_AUTO_EXPIRE=false to always serve stale cache.
    """
    return os.environ.get(_CACHE_AUTO_EXPIRE_ENV, "true").strip().lower() != "false"


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
    """Thin wrapper for data.structure.auxiliary_category (kept for internal use)."""
    return _is_auxiliary_dir_cat(name)


def _classify_top_dirs(
    all_file_paths: list[str],
) -> tuple[tuple[str, ...], list[dict[str, object]]]:
    """Classify top-level dirs; returns (l1_roots, aux_dirs) for backward compatibility."""
    dirs = _classify_top_dirs_data(all_file_paths)
    l1 = tuple(d.name for d in dirs if not d.is_auxiliary)
    aux: list[dict[str, object]] = [
        {"name": d.name, "file_count": d.file_count, "category": d.category}
        for d in dirs
        if d.is_auxiliary
    ]
    return l1, aux


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


def _top_level_files_from_paths(file_paths: list[str]) -> set[str]:
    """Return individual file paths that sit in a 'parent' directory.

    When a directory (e.g. ``src/pkg``) is a parent of other directories
    (e.g. ``src/pkg/cache``), files directly in it (e.g. ``src/pkg/errors.py``)
    cannot be addressed via the directory approach.  This helper surfaces those
    files so they can be used as module identifiers directly.
    """
    all_dirs: set[str] = {
        fp.replace("\\", "/").rsplit("/", 1)[0]
        for fp in file_paths
        if "/" in fp
    }
    parent_dirs = {
        d for d in all_dirs
        if any(other != d and other.startswith(d + "/") for other in all_dirs)
    }
    result: set[str] = set()
    for fp in file_paths:
        fp_norm = fp.replace("\\", "/")
        parent = fp_norm.rsplit("/", 1)[0] if "/" in fp_norm else ""
        if parent in parent_dirs:
            result.add(fp_norm)
    return result


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
        all_file_rows = list(db.iter_files())
        all_file_paths: list[str] = [f.path.replace("\\", "/") for f in all_file_rows]
        file_languages: dict[str, str] = {
            f.path.replace("\\", "/"): f.language for f in all_file_rows
        }

    roots, _ = _resolve_roots_and_aux(all_file_paths)
    dir_syms = {d: s for d, s in dir_syms.items() if _is_under_roots(d, roots)}
    dir_deps = _filter_dir_deps(dir_deps, roots)

    centrality = compute_centrality(edges_all, modules_data)
    layers = topological_layers(edges_internal, modules_data)
    cycles = find_cycles(edges_internal, modules_data)
    ext_by_dir = external_dependencies_by_dir(edges_all, modules_data)

    # Extract docstrings: one per directory (for leaf dirs) + per-file (for parent dirs).
    dir_file_docstrings: dict[str, str] = {}
    file_docstrings: dict[str, str] = {}  # file_path → docstring
    if _docstrings_enabled():
        all_dirs_set_check = set(dir_syms.keys())
        for d, syms in dir_syms.items():
            is_parent = any(other.startswith(d + "/") for other in all_dirs_set_check if other != d)
            # Unique file paths in this dir, ordered by first appearance.
            seen: dict[str, None] = {}
            for s in syms:
                fp = s["file"].replace("\\", "/")
                seen[fp] = None
            if is_parent:
                # Collect per-file docstrings for parent dirs
                for fp in seen:
                    lang = file_languages.get(fp) or _lang_from_path(fp)
                    doc = extract_file_docstring(project_root / fp, lang)
                    if doc:
                        file_docstrings[fp] = doc
            else:
                for fp in seen:
                    lang = file_languages.get(fp) or _lang_from_path(fp)
                    doc = extract_file_docstring(project_root / fp, lang)
                    if doc:
                        dir_file_docstrings[d] = doc
                        break

    return _build_project_map_prompt(
        dir_deps,
        dir_syms,
        roots=roots,
        centrality=centrality,
        layers=layers,
        cycles=cycles,
        ext_by_dir=ext_by_dir,
        dir_file_docstrings=dir_file_docstrings,
        file_docstrings=file_docstrings,
        ref_docs_section=ref_docs_prompt_section(project_root),
    )


def _migrate_renamed_module_caches(
    codesense_dir: Path,
    new_modules: list[dict[str, object]],
    db: CodeGraphDB,
) -> None:
    """Reuse existing .md caches when a module is renamed but content unchanged.

    Computes module_hash for each new module and checks whether any old module
    (not in the new index) has the same hash.  When a 1-to-1 match is found,
    the old ``.md`` file is renamed to the new key and the ``.hashes.json``
    entry is updated accordingly.  The old key will then be cleaned up by
    ``_prune_stale_modules`` in the subsequent ``write_modules_index`` call.
    """
    existing_hashes = cache.read_module_hashes(codesense_dir)
    if not existing_hashes:
        return

    new_keys: set[str] = {
        cache.safe_key(str(m.get("name", ""))) for m in new_modules
    }

    # Build hash → new_key mapping; mark collisions (same hash for two new modules)
    hash_to_new_key: dict[str, str] = {}
    for m in new_modules:
        mkey = cache.safe_key(str(m.get("name", "")))
        h = _compute_module_hash(m, db)
        if h in hash_to_new_key:
            hash_to_new_key[h] = ""  # collision sentinel
        else:
            hash_to_new_key[h] = mkey

    modules_dir = codesense_dir / "modules"

    for old_key, old_hash in existing_hashes.items():
        if old_key in new_keys:
            continue  # same name survives, nothing to migrate

        new_key = hash_to_new_key.get(old_hash, "")
        if not new_key:
            continue  # no match or ambiguous hash collision

        if new_key in existing_hashes:
            continue  # new name already has its own cache, don't overwrite

        old_md = modules_dir / f"{old_key}.md"
        new_md = modules_dir / f"{new_key}.md"
        if old_md.exists() and not new_md.exists():
            old_md.rename(new_md)
            cache.write_module_hash(codesense_dir, new_key, old_hash)
            # old_key entry is left for _prune_stale_modules to delete


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
            | _top_level_files_from_paths(all_file_paths_l1)
        )

        warnings: list[str] = []
        modules_json = _parse_modules_text(response, valid_dirs, warnings=warnings)
        if not modules_json:
            raise InvalidArgumentError(
                "解析失败：无法从响应中提取有效模块。"
                "请确保每行格式为「模块名|职责|目录」，不含多余内容。"
            )

        expanded = _expand_module_files(modules_json, all_file_paths_l1)

        # Migrate renamed modules before pruning stale entries
        _migrate_renamed_module_caches(codesense_dir, expanded, db)

    cache.write_modules_index(codesense_dir, expanded, current_hash, aux_dirs=aux_dirs)

    # Save basic 03_modules segment so project_map can render immediately.
    from codesense_v1.data.hashes import compute_architecture_hash, compute_dependencies_hash  # avoid circular
    # Use the same leaf-dir-based hash as project_map.py (not module assignments).
    _all_parent_dirs = {
        fp.replace("\\", "/").rsplit("/", 1)[0]
        for fp in all_file_paths_l1
        if "/" in fp.replace("\\", "/")
    }
    _current_leaf_dirs = sorted({
        d for d in _all_parent_dirs
        if not any(other != d and other.startswith(d + "/") for other in _all_parent_dirs)
    })
    seg03_hash = compute_architecture_hash([_current_leaf_dirs])
    if not cache.is_segment_valid(codesense_dir, "03_modules", seg03_hash):
        layers_for_seg = topological_layers(edges, modules_data)
        seg03_content = _render_basic_architecture_segment(expanded, layers_for_seg)
        cache.write_segment(codesense_dir, "03_modules", seg03_content, seg03_hash)

    # Always regenerate 07_dependencies with module name mappings now available.
    cycles_for_07 = find_cycles(edges, modules_data)
    seg07_content = render_dependencies_segment(expanded, edges, cycles_for_07)
    seg07_hash = compute_dependencies_hash(edges)
    cache.write_segment(codesense_dir, "07_dependencies", seg07_content, seg07_hash)

    # Render and persist the new segment-based project_map.md.
    cache.render_project_map(codesense_dir)

    n_modules = len(expanded)
    warning_suffix = ""
    if warnings:
        warning_suffix = "\n\n⚠️ 解析警告：\n" + "\n".join(f"- {w}" for w in warnings)

    return (
        f"模块划分已保存（{n_modules} 个模块）。"
        "请重新调用 `project_map` 获取完整架构概览。"
        + warning_suffix
    )


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
        # Structured symbol data: {fp: [{id, name, kind, sig}]}
        file_symbols: dict[str, list[dict[str, str]]] = {}
        # Nodes per file for docstring extraction
        file_nodes: dict[str, list] = {}
        for node in db.iter_nodes(kinds=("function", "class", "method")):
            fp = node.file_path.replace("\\", "/")
            if fp not in module_file_set:
                continue
            sig = node.signature or node.name
            file_symbols.setdefault(fp, []).append(
                {"id": node.id, "name": node.name, "kind": node.kind, "sig": sig}
            )
            file_nodes.setdefault(fp, []).append(node)
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

    # Extract file and symbol docstrings
    file_docstrings: dict[str, str] = {}
    symbol_docstrings: dict[str, str] = {}
    if _docstrings_enabled():
        pr = Path(project_root)
        for fp, nodes_list in file_nodes.items():
            lang = nodes_list[0].language if nodes_list else _lang_from_path(fp)
            doc = extract_file_docstring(pr / fp, lang)
            if doc:
                file_docstrings[fp] = doc
            symbol_docstrings.update(extract_symbol_docstrings(pr / fp, lang, nodes_list))
        # Files with no symbols also need file docstring
        for fp in sorted(module_file_set):
            if fp not in file_docstrings and fp not in file_nodes:
                lang = _lang_from_path(fp)
                doc = extract_file_docstring(pr / fp, lang)
                if doc:
                    file_docstrings[fp] = doc

    return _build_module_prompt(
        entry,
        dir_deps,
        file_symbols,
        public_symbols=pub_syms,
        external_deps=sorted(ext_deps),
        file_docstrings=file_docstrings,
        symbol_docstrings=symbol_docstrings,
        ref_docs_section=ref_docs_prompt_section(project_root),
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

    Entries in ``directories`` may be either directory paths or individual file
    paths (for single-file modules like ``src/pkg/errors.py``).  File-path
    entries are added to ``files`` directly without directory expansion.

    When a module claims a parent directory (e.g. ``src/core``) and another
    module explicitly claims a sub-directory (e.g. ``src/core/utils``), the
    parent module's files exclude the sub-directory's files so there is no
    overlap between modules.
    """
    all_file_set = {fp.replace("\\", "/") for fp in all_file_paths}

    def _is_file_entry(entry: str) -> bool:
        """Return True if *entry* looks like a file path (has an extension)."""
        return bool(_HAS_EXTENSION_RE.search(entry.split("/")[-1]))

    # Collect all claimed directories/files across all modules
    all_claimed_dirs: set[str] = set()
    for m in modules_json:
        for d in (m.get("directories") or []):
            d_str = str(d).rstrip("/")
            if d_str and not _is_file_entry(d_str):
                all_claimed_dirs.add(d_str)

    result: list[dict[str, object]] = []
    for m in modules_json:
        dirs_raw = m.get("directories")
        entries: list[str] = [
            str(d).rstrip("/")
            for d in (dirs_raw if isinstance(dirs_raw, list) else [])
            if d
        ]

        # Split entries into file refs and directory refs
        file_refs: list[str] = []
        dir_refs: list[str] = []
        for e in entries:
            if _is_file_entry(e):
                file_refs.append(e)
            else:
                dir_refs.append(e)

        # Sub-directories claimed by OTHER modules (exclude from dir expansion)
        excluded: set[str] = {
            c for c in all_claimed_dirs
            if c not in set(dir_refs)
            and any(c.startswith(d + "/") for d in dir_refs)
        }

        # Expand directory refs to files
        matched: list[str] = []
        for fp in all_file_paths:
            fp_norm = fp.replace("\\", "/").rstrip("/")
            for d in dir_refs:
                if fp_norm == d or fp_norm.startswith(d + "/"):
                    if not any(
                        fp_norm == ex or fp_norm.startswith(ex + "/")
                        for ex in excluded
                    ):
                        matched.append(fp_norm)
                    break

        # Add direct file refs (only if they actually exist)
        for fr in file_refs:
            if fr in all_file_set and fr not in matched:
                matched.append(fr)

        # Determine stored directories: dir_refs + deduce parent dir for file refs
        stored_dirs = dir_refs[:]
        # File-ref modules: store as empty dirs list (files field is authoritative)
        if not dir_refs and file_refs:
            stored_dirs = []

        result.append(
            {
                "name": m.get("name", ""),
                "description": m.get("description", ""),
                "directories": stored_dirs,
                "files": sorted(set(matched)),
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


def _render_basic_architecture_segment(
    modules: list[dict[str, object]],
    layers: list[list[str]],
) -> str:
    """Render 03_architecture segment from module list + topo layers (no LLM)."""
    from codesense_v1.data.structure import auxiliary_category

    # Build dir/file → module name lookup for layer label resolution
    dir_to_name: dict[str, str] = {}
    for m in modules:
        if not isinstance(m, dict):
            continue
        mname = str(m.get("name", ""))
        for d in (m.get("directories") or []):
            dir_to_name[str(d)] = mname
        for f in (m.get("files") or []):
            fp = str(f).replace("\\", "/")
            dir_to_name[fp] = mname
            # Also map parent dir so topological layer dirs resolve correctly
            parent = fp.rsplit("/", 1)[0] if "/" in fp else ""
            if parent:  # never map empty string
                dir_to_name.setdefault(parent, mname)

    def _layer_label(d: str) -> str | None:
        """Return module name for a layer dir, or None to skip it."""
        # Skip auxiliary directories (tests, scripts, docs…)
        top = d.split("/")[0]
        if auxiliary_category(top) is not None:
            return None
        label = dir_to_name.get(d, d.split("/")[-1] if "/" in d else d)
        return label if label else None  # skip empty strings

    lines: list[str] = []

    # Module list table
    # Collect all dirs across modules to detect "parent dirs" (dirs that are
    # prefixes of other modules' dirs → should display files instead).
    all_module_dirs: set[str] = {
        str(d)
        for m in modules if isinstance(m, dict)
        for d in (m.get("directories") or [])
    }

    def _best_path(m: dict) -> str:
        dirs = m.get("directories") or []
        files = m.get("files") or []
        if not dirs:
            # File-level module: show all files (skip __init__.py)
            meaningful = [f for f in files if not str(f).endswith("__init__.py")]
            return "、".join(str(f) for f in (meaningful or files))
        # Check if any of this module's dirs is a parent of another module's dir
        is_parent = any(
            other != str(d) and other.startswith(str(d) + "/")
            for d in dirs
            for other in all_module_dirs
        )
        if is_parent:
            meaningful = [f for f in files if not str(f).endswith("__init__.py")]
            if meaningful:
                return "、".join(str(f) for f in meaningful)
        return "、".join(str(d) for d in dirs)

    lines.append("## 模块列表\n")
    lines.append("| 模块 | 职责 | 主要目录 |")
    lines.append("|------|------|----------|")
    for m in modules:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", ""))
        desc = str(m.get("description", m.get("desc", "")))
        path_str = _best_path(m)
        lines.append(f"| {name} | {desc} | {path_str} |")

    return "\n".join(lines)


def _build_project_map_prompt(
    dir_deps: dict[str, dict[str, list[str]]],
    dir_syms: dict[str, list[dict[str, str]]],
    roots: tuple[str, ...] = _DEFAULT_INCLUDE_ROOTS,
    *,
    centrality: dict[str, DirCentrality] | None = None,
    layers: list[list[str]] | None = None,
    cycles: list[list[str]] | None = None,
    ext_by_dir: dict[str, list[str]] | None = None,
    dir_file_docstrings: dict[str, str] | None = None,
    file_docstrings: dict[str, str] | None = None,
    ref_docs_section: str = "",
) -> str:
    all_dirs = sorted(set(dir_deps.keys()) | set(dir_syms.keys()))
    all_dirs_set = set(all_dirs)
    n_dirs = len(all_dirs)
    roots_str = "、".join(f"`{r}`" for r in roots)

    # ---- directory section --------------------------------------------------
    dir_lines: list[str] = []
    for d in all_dirs:
        syms = dir_syms.get(d, [])

        cent_str = ""
        if centrality and d in centrality:
            c = centrality[d]
            cent_str = f"  (←{c.fan_in} →{c.fan_out})"

        ext_str = ""
        if ext_by_dir and d in ext_by_dir:
            deps = ext_by_dir[d]
            if deps:
                ext_str = "  外部: " + ", ".join(deps[:5])
                if len(deps) > 5:
                    ext_str += f" …+{len(deps) - 5}"

        # Detect parent dirs: dirs that have child dirs in the analysis set
        is_parent = any(other.startswith(d + "/") for other in all_dirs_set if other != d)

        if is_parent and syms:
            # Group symbols by file for per-file display
            import collections
            file_syms: dict[str, list[str]] = collections.defaultdict(list)
            for sym in syms:
                fp = sym.get("file", "").replace("\\", "/")
                file_syms[fp].append(sym.get("name", ""))

            line = f"- `{d}`（父目录，含独立文件）{cent_str}{ext_str}"
            for fp in sorted(file_syms):
                fname = fp.split("/")[-1]
                sym_str = ", ".join(file_syms[fp][:8])
                file_line = f"\n  - `{fname}`: [{sym_str}]"
                if file_docstrings and fp in file_docstrings:
                    file_line += f"\n    > {file_docstrings[fp]}"
                line += file_line
        else:
            sym_names = ", ".join(s["name"] for s in syms)
            sym_part = f"  [{sym_names}]" if sym_names else ""
            line = f"- `{d}`: {len(syms)} 个符号{cent_str}{ext_str}{sym_part}"

            fdoc = dir_file_docstrings.get(d, "") if dir_file_docstrings else ""
            if fdoc:
                line += f"\n  > {fdoc}"

        dir_lines.append(line)
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
        + (f"## 参考文档\n\n{ref_docs_section}\n" if ref_docs_section else "")
        + "## 输出格式\n\n"
        "每行一个模块，用竖线（|）分隔三列：\n"
        "  模块名|一句话职责|所属目录或文件路径（多个用英文逗号分隔）\n\n"
        "示例行：\n"
        "  缓存层|管理 .codesense 缓存文件的读写与失效|src/codesense_v1/cache\n"
        "  数据层|封装 CodeGraph DB 查询与模块依赖聚合|src/data,src/models\n"
        "  错误定义|统一异常层次|src/codesense_v1/errors.py\n\n"
        "规则：\n"
        "- 每个模块占一行\n"
        "- 不要输出标题行、编号、Markdown 格式或任何其他内容\n"
        "- 路径为相对项目根的路径；单文件模块可直接写文件路径（如 `src/pkg/errors.py`）\n"
        "- 同一目录/文件不归属多个模块\n"
        "- 必须覆盖所有目录\n"
        "- **禁止把所有目录归到单一模块**（这是错误划分；至少 2 个模块）\n"
        "- 模块名 2-20 个字符；不得包含重复词或与描述列粘连\n"
    )


def _build_module_prompt(
    entry: dict[str, object],
    dir_deps: dict[str, dict[str, list[str]]],
    file_symbols: dict[str, list[dict[str, str]]],
    *,
    public_symbols: list[str] | None = None,
    external_deps: list[str] | None = None,
    file_docstrings: dict[str, str] | None = None,
    symbol_docstrings: dict[str, str] | None = None,
    ref_docs_section: str = "",
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

    # Build per-file symbol section (structured data + docstrings)
    sym_lines: list[str] = []
    for fp in sorted(files):
        sym_list = file_symbols.get(fp, [])
        fdoc = (file_docstrings or {}).get(fp, "")
        header = f"\n**`{fp}`**"
        if fdoc:
            header += f"  — [文件注释] {fdoc}"
        sym_lines.append(header)
        if sym_list:
            for sym in sym_list:
                line = f"- `{sym['name']}` ({sym['kind']}): {sym['sig']}"
                sdoc = (symbol_docstrings or {}).get(sym["id"], "")
                if sdoc:
                    line += f"\n  > [docstring] {sdoc}"
                elif _is_generic_name(sym["name"]):
                    line += "\n  ⚠️ 无 docstring 且名称通用，建议 read_file 确认实现语义"
                sym_lines.append(line)
        else:
            sym_lines.append("  （无符号）")
    symbols_txt = "\n".join(sym_lines) if sym_lines else "（无符号数据）"

    # Build file list with inline docstrings
    file_lines: list[str] = []
    for f in sorted(files):
        fdoc = (file_docstrings or {}).get(f, "")
        file_lines.append(f"- `{f}`" + (f"  — [文件注释] {fdoc}" if fdoc else ""))
    files_txt = "\n".join(file_lines) or "（无）"

    outbound_txt = "\n".join(f"- `{d}`" for d in sorted(outbound)) or "（无）"
    inbound_txt = "\n".join(f"- `{d}`" for d in sorted(inbound)) or "（无）"

    # Graph-derived public API (cross-directory imports, language-agnostic)
    if public_symbols:
        pub_api_txt = "\n".join(f"- `{s}`" for s in public_symbols)
    elif _looks_like_entry_layer(directories):
        pub_api_txt = (
            "（未检测到项目内部 import——目录名称暗示此模块为入口/服务层。\n"
            "对外接口由外部协议（MCP/CLI/HTTP/RPC）定义，不在图推导范围内；\n"
            "建议查阅协议文档或通过 `read_file` 确认实际接口契约）"
        )
    else:
        pub_api_txt = "（暂无外部调用记录——该模块可能为纯内部实现）"

    # External library dependencies
    ext_deps_txt = (
        "\n".join(f"- `{d}`" for d in external_deps)
        if external_deps
        else "（无）"
    )

    _DATA_TRUST_NOTICE = (
        "\n---\n\n"
        "**数据可信度说明**\n\n"
        "以上信息由静态图分析（CodeGraph）与源码文本提取生成，存在以下已知局限：\n"
        "- `[文件注释]` / `[docstring]` 标注内容反映**写作时的设计意图**，与最新实现可能存在偏差；\n"
        "- 函数签名不显示副作用（I/O、全局状态、异常路径）；\n"
        "- 图推导对外接口仅统计项目内部 import，不覆盖外部调用方（MCP/CLI/HTTP）；\n"
        "- 标注 ⚠️ 的符号，建议调用 `read_file` 核实实现细节。\n"
    )

    return (
        "# 模块知识文档生成请求\n\n"
        "你是一位软件架构师，请根据以下模块结构数据，生成一份**模块知识文档**。\n\n"
        "## 输出要求\n\n"
        "严格输出以下 5 个 H2 章节，**不得增删章节、不得添加「对外接口」等额外章节**：\n\n"
        "## 一句话定位\n"
        "（10-20 字说明模块职责）\n\n"
        "## 架构简析\n"
        "（描述模块内部分层，如「入口→核心→辅助」，各层包含哪些文件；单文件模块简述职责即可）\n\n"
        "## 文件清单\n"
        "（每个文件一行：`文件名` — 一句话说明；若有 __init__.py，说明其导出的主要符号）\n\n"
        "## 上下游关系\n"
        "（「上游」= 依赖此模块的目录；「下游」= 此模块依赖的目录；数据来自 imports 边，置信度 extracted）\n\n"
        "## 实现约束清单\n"
        "（边界行为、踩坑点、禁忌；**只写模块内部约束**，跨模块架构禁忌在 project_map 04_constraints 已有，此处不重复）\n\n"
        "---\n\n"
        "## 模块数据（参考，不要在输出中重复这些原始数据）\n\n"
        f"### 模块名称\n{name}\n\n"
        f"### project_map 中的初步描述\n{description}\n\n"
        f"### 包含文件\n{files_txt}\n\n"
        f"### 被其他目录 import 的公开符号（图推导，仅作参考）\n"
        f"{pub_api_txt}\n\n"
        f"### 外部依赖库（该模块直接引入的第三方/标准库）\n"
        f"{ext_deps_txt}\n\n"
        f"### 模块内符号（函数/类/方法，含签名）\n{symbols_txt}\n\n"
        f"### 上游依赖（该模块依赖的目录）\n{outbound_txt}\n\n"
        f"### 下游依赖（依赖该模块的目录）\n{inbound_txt}\n"
        + (f"\n## 参考文档\n\n{ref_docs_section}\n" if ref_docs_section else "")
        + f"{_DATA_TRUST_NOTICE}"
    )


# ---------- project_map segment API -----------------------------------------


def render_structure_segment(
    project_root: Path,
    top_dirs: list[TopLevelDir],
    tree_root: DirectoryNode,
    max_depth: int = 3,
) -> str:
    """Render 02_structure.md — pure program, no Agent needed.

    Produces a depth-3 directory tree with auxiliary dir annotations.
    """
    project_name = project_root.resolve().name or project_root.resolve().parts[-1]
    lines: list[str] = [f"## 顶层目录结构\n", f"```", f"{project_name}/"]

    # Set of auxiliary top-level dir names for skip-expansion
    aux_names = {d.name for d in top_dirs if d.is_auxiliary}

    def _render_node(node: DirectoryNode, depth: int, prefix: str) -> None:
        children = sorted(node.subdirs.values(), key=lambda n: n.name)
        all_items: list[tuple[str, bool, DirectoryNode | None]] = []
        for c in children:
            all_items.append((c.name, True, c))
        for f in sorted(node.files, key=lambda f: f.path):
            all_items.append((f.path.replace("\\", "/").split("/")[-1], False, None))

        for i, (name, is_dir, child) in enumerate(all_items):
            is_last = i == len(all_items) - 1
            connector = "└── " if is_last else "├── "
            ext_prefix = "    " if is_last else "│   "

            if is_dir:
                td = next((d for d in top_dirs if d.name == name), None)
                annotation = f"  [{td.category}]" if td and td.category else ""
                lines.append(f"{prefix}{connector}{name}/{annotation}")
                # Don't expand auxiliary dirs (already summarised below)
                if depth < max_depth and child and name not in aux_names:
                    _render_node(child, depth + 1, prefix + ext_prefix)
            else:
                lines.append(f"{prefix}{connector}{name}")

    _render_node(tree_root, depth=1, prefix="")
    lines.append("```")

    return "\n".join(lines)


def render_dependencies_segment(
    modules: list[dict[str, object]],
    edges: list,  # list[ModuleEdge]
    cycles: list[list[str]],
    centrality: dict[str, object] | None = None,
) -> str:
    """Render 07_dependencies.md — pure program, no Agent needed."""
    from codesense_v1.data.structure import auxiliary_category

    # Build lookup: path (dir or file) → module name
    dir_to_name: dict[str, str] = {}
    for m in modules:
        mname = str(m.get("name", ""))
        for d in (m.get("directories") or []):
            dir_to_name[str(d)] = mname
        for f in (m.get("files") or []):
            fp = str(f).replace("\\", "/")
            dir_to_name[fp] = mname
            parent = fp.rsplit("/", 1)[0] if "/" in fp else ""
            if parent:
                dir_to_name.setdefault(parent, mname)

    # Compute common prefix to strip when no module names available
    all_dirs_in_edges: list[str] = []
    for e in edges:
        if not getattr(e, "is_external", False):
            src = e.source.replace("\\", "/")
            tgt = e.target.replace("\\", "/")
            all_dirs_in_edges.append(src.rsplit("/", 1)[0] if "/" in src else src)
            all_dirs_in_edges.append(tgt.rsplit("/", 1)[0] if "/" in tgt else tgt)

    def _strip_prefix(path: str) -> str:
        """Remove the longest common prefix from a path for display."""
        if not all_dirs_in_edges:
            return path
        import os
        common = os.path.commonprefix(all_dirs_in_edges).replace("\\", "/").rstrip("/")
        if common and path.startswith(common + "/"):
            return path[len(common) + 1:]
        if path == common:
            # Path IS the prefix itself — use last segment
            return path.split("/")[-1]
        return path

    def _dir_to_label(file_path: str) -> str | None:
        """Return module name (or shortened path) for a file edge endpoint.
        Returns None if the path should be filtered out (auxiliary directory).
        """
        fp = file_path.replace("\\", "/")
        top = fp.split("/")[0]
        if auxiliary_category(top) is not None:
            return None

        d = fp.rsplit("/", 1)[0] if "/" in fp else fp

        # Check direct file match first
        if fp in dir_to_name:
            return dir_to_name[fp]
        # Then check directory match
        if d in dir_to_name:
            return dir_to_name[d]
        # No module name → use stripped path
        return _strip_prefix(d) if dir_to_name else _strip_prefix(d)

    # Aggregate edges
    edge_set: set[tuple[str, str]] = set()
    upstream: dict[str, set[str]] = {}
    downstream: dict[str, set[str]] = {}
    for e in edges:
        if getattr(e, "is_external", False):
            continue
        src_label = _dir_to_label(e.source.replace("\\", "/"))
        tgt_label = _dir_to_label(e.target.replace("\\", "/"))
        if src_label is None or tgt_label is None:
            continue
        if src_label == tgt_label:
            continue
        edge_set.add((src_label, tgt_label))
        downstream.setdefault(src_label, set()).add(tgt_label)
        upstream.setdefault(tgt_label, set()).add(src_label)

    lines: list[str] = []

    # Table: use module names if available, else all unique labels from edges
    if modules:
        all_names = sorted({str(m.get("name", "")) for m in modules if isinstance(m, dict)})
    else:
        all_names = sorted({label for pair in edge_set for label in pair})

    if all_names:
        lines.append("\n## 上下游详表\n")
        lines.append("| 模块 | 上游（依赖于我） | 下游（我依赖） |")
        lines.append("|------|----------------|--------------|")
        for name in all_names:
            up = "、".join(sorted(upstream.get(name, set()))) or "无"
            down = "、".join(sorted(downstream.get(name, set()))) or "无"
            lines.append(f"| {name} | {up} | {down} |")

    if cycles:
        lines.append("\n## ⚠️ 循环依赖\n")
        for cycle in cycles:
            lines.append(f"- {' → '.join(cycle)} → {cycle[0]}")
    else:
        lines.append("\n> 无循环依赖。")

    return "\n".join(lines)


# ---------- submodule helpers ------------------------------------------------


def _compute_submodule_hash(file_path: str, db: "CodeGraphDB") -> str:
    """Hash 单文件的 nodes 指纹 + 出边 imports 集合（基于文件路径）。"""
    # Build node-id → file mapping for edge resolution
    node_id_to_file: dict[str, str] = {}
    for node in db.iter_nodes():
        node_id_to_file[node.id] = node.file_path.replace("\\", "/")

    parts: list[str] = []
    for node in sorted(
        db.iter_nodes(kinds=("function", "class", "method")),
        key=lambda n: (n.name, n.kind),
    ):
        if node.file_path.replace("\\", "/") == file_path:
            parts.append(f"{node.name}:{node.kind}:{node.signature or ''}")
    for edge in sorted(
        db.iter_edges(kinds=("imports", "calls")),
        key=lambda e: (e.source, e.target),
    ):
        src_file = node_id_to_file.get(edge.source, edge.source).replace("\\", "/")
        if src_file == file_path and edge.kind in ("imports", "calls"):
            tgt_file = node_id_to_file.get(edge.target, edge.target).replace("\\", "/")
            parts.append(f"edge:{edge.kind}:{src_file}->{tgt_file}")
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()  # noqa: S324


def _is_single_file_module(entry: dict) -> bool:
    """模块下除 __init__.py 外只有 0 或 1 个 .py 文件 → 视为单文件模块。"""
    py_files = [f for f in entry.get("files", []) if f.endswith(".py") and not f.endswith("__init__.py")]
    return len(py_files) <= 1


def _build_submodule_prompt(
    module_entry: dict,
    file_path: str,
    file_nodes: list,
    outbound_edges: list,
    inbound_edges: list,
    ref_docs_section: str = "",
    *,
    out_files: list[str] | None = None,
    in_files: list[str] | None = None,
) -> str:
    """构造单文件子模块摘要的 LLM prompt。

    outbound_edges / inbound_edges 是 EdgeRow 列表。EdgeRow.source/target 是 node id，
    所以调用方应通过 out_files / in_files 参数直接传入已解析的文件路径列表，
    避免依赖 edge.target 作为文件路径。
    若 out_files / in_files 未提供，则尝试直接从 edge.target / edge.source 获取
    （仅在 source/target 本身已是文件路径时正确）。
    """
    module_name = module_entry.get("name", "")
    file_name = file_path.split("/")[-1]

    public_symbols = [
        f"- `{n.name}` ({n.kind}): {n.signature or ''}"
        for n in file_nodes
        if not n.name.startswith("_") and n.kind in ("function", "class", "method")
    ]
    all_symbols = [
        f"- `{n.name}` ({n.kind}): {n.signature or ''}"
        for n in file_nodes
        if n.kind in ("function", "class", "method")
    ]

    resolved_out = (
        sorted(out_files)
        if out_files is not None
        else sorted({e.target for e in outbound_edges if e.kind == "imports"})
    )
    resolved_in = (
        sorted(in_files)
        if in_files is not None
        else sorted({e.source for e in inbound_edges if e.kind == "imports"})
    )

    lines = [
        "# 子模块文档生成任务",
        "",
        f"模块：`{module_name}`  文件：`{file_name}`  路径：`{file_path}`",
        "",
        "## 全部符号",
        "\n".join(all_symbols) or "（无）",
        "",
        "## 对外接口候选（非下划线开头）",
        "\n".join(public_symbols) or "（无公开符号，请在输出中注明「仅供内部调用」）",
        "",
        "## 出向依赖文件（imports）",
        "\n".join(f"- `{f}`" for f in resolved_out) or "（无）",
        "",
        "## 入向依赖文件（被哪些文件 import）",
        "\n".join(f"- `{f}`" for f in resolved_in) or "（无）",
    ]
    if ref_docs_section:
        lines += ["", "## 参考文档", ref_docs_section]

    lines += [
        "",
        "---",
        "",
        "请基于以上数据生成子模块文档，格式如下（严格输出 Markdown，不要输出其他内容）：",
        "",
        "## 文件概述",
        "（2-3 句话说明该文件的职责）",
        "",
        "## 对外接口",
        "（列表：函数/类名 + 签名 + 一句话说明；若无公开接口则写「仅供内部调用」）",
        "",
        "## 跨模块依赖",
        "（出向：该文件依赖的外部模块文件；入向：依赖该文件的外部模块文件）",
        "",
        "## 典型调用链",
        "（2-3 条关键调用链，格式：`调用者` → `被调用者`；数据不足可省略）",
    ]
    return "\n".join(lines)


def save_submodule_summary(project_root: Path, module_name: str, file_path: str, summary: str) -> None:
    """保存子模块文档到 .codesense/modules/<module>/<file>.md。

    Raises:
        FileNotFoundError: if the CodeGraph DB does not exist.
        InvalidArgumentError: if modules_index is missing or module_name not found.
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME
    db_path = project_root / ".codegraph" / "codegraph.db"

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

    module_key = cache.safe_key(module_name)
    # file_path 形如 "src/codesense_v1/cache/cache.py"，取末段去扩展名
    file_stem = file_path.rstrip("/").split("/")[-1]
    # Replace dots with underscores for a safe filename key
    file_stem_safe = file_stem.replace(".", "_")
    file_key = cache.safe_key(file_stem_safe)

    with CodeGraphDB(project_root) as db:
        submodule_hash = _compute_submodule_hash(file_path, db)

    cache.write_submodule(codesense_dir, module_key, file_key, summary, submodule_hash)


def get_identity_segment_prompt(
    sources: list[IdentitySource],
    tech_hints: dict[str, str],
) -> str:
    """Return LLM prompt for generating 01_identity.md."""
    sources_text = "\n\n".join(
        f"### [{s.kind}] {s.path}\n```\n{s.content[:3000]}\n```"
        for s in sources
    ) or "（无可用项目文档，请根据后续模块数据推断）"

    hints_text = "\n".join(f"- {k}: {v}" for k, v in tech_hints.items()) or "（未检测到配置文件）"

    return (
        "# 项目身份信息生成\n\n"
        "你是一位软件架构师，请根据以下资料生成项目的**仓库定位**和**技术栈**描述。\n\n"
        "## 输出格式（严格按此 Markdown 结构）\n\n"
        "```markdown\n"
        "## 仓库定位\n\n"
        "<一句话总结项目>\n\n"
        "<2-3 段：项目解决什么问题、目标用户、核心价值>\n\n"
        "## 技术栈\n\n"
        "| 类别 | 内容 |\n"
        "|------|------|\n"
        "| 主语言 | ... |\n"
        "| 核心框架 | ... |\n"
        "| 关键依赖 | ... |\n"
        "| 构建工具 | ... |\n"
        "```\n\n"
        "## 参考资料\n\n"
        "### 自动检测到的技术栈线索\n"
        f"{hints_text}\n\n"
        "### 项目文档\n\n"
        f"{sources_text}\n\n"
        "**注意**：如无足够信息，请如实标注「信息不足，以下为推断」，不要捏造。"
    )


def get_architecture_segment_prompt(
    layers: list[list[str]],
    modules: list[dict[str, object]],
    dir_deps: dict[str, dict[str, list[str]]],
    dir_syms: dict[str, list[dict[str, str]]],
) -> str:
    """Return LLM prompt for generating 03_architecture.md."""
    # Layer description
    layer_lines: list[str] = []
    for i, layer in enumerate(layers):
        if i == 0:
            label = "第 0 层（基础层）"
        elif i == len(layers) - 1:
            label = f"第 {i} 层（入口层）"
        else:
            label = f"第 {i} 层（中间层）"
        dir_labels = ", ".join("`" + d + "`" for d in sorted(layer))
        layer_lines.append("- " + label + "：" + dir_labels)
    layer_text = "\n".join(layer_lines) or "（无层次数据）"

    # Module list text
    module_lines: list[str] = []
    for m in modules:
        name = m.get("name", "")
        raw_dirs = m.get("dirs", [m.get("dir", "")])
        dirs_str = ", ".join(str(d) for d in raw_dirs)
        module_lines.append(f"- `{name}` → 目录：{dirs_str}")
    modules_text = "\n".join(module_lines) or "（无模块数据）"

    return (
        "# 架构分析与模块列表生成\n\n"
        "你是一位软件架构师，请根据以下数据生成项目的**系统分层图**和**模块列表**。\n\n"
        "## 输出格式（严格按此 Markdown 结构）\n\n"
        "```markdown\n"
        "## 系统分层\n\n"
        "```\n"
        "（参考下方数据画 ASCII 框图：箱式分层 + 箭头 + 层次标注 + 关键交互说明）\n"
        "```\n\n"
        "## 层次职责\n\n"
        "| 层次 | 模块 | 职责 |\n"
        "|------|------|------|\n"
        "| 传输层 | ... | ... |\n\n"
        "## 核心数据流\n\n"
        "```\n"
        "（简洁描述请求从入口到数据存储的主要路径）\n"
        "```\n\n"
        "## 模块列表\n\n"
        "| 模块 | 职责 | 主要目录 |\n"
        "|------|------|----------|\n"
        "| ... | ... | ... |\n"
        "```\n\n"
        "## 拓扑分层数据\n\n"
        f"{layer_text}\n\n"
        "## 模块划分\n\n"
        f"{modules_text}\n\n"
        "**注意**：\n"
        "- 层名须从代码职责推断（不要直接用「第0层」），参考箱式分层风格\n"
        "- 模块列表直接使用上方「模块划分」的模块名，不要自行命名\n"
        "- ASCII 图风格参考 `_architecture.md` 中的风格（带边框 + 职责标注）"
    )


def save_project_map_segment(
    project_root: Path,
    segment_id: str,
    content: str,
    source_hash: str,
) -> None:
    """Save a project_map segment to cache.

    Args:
        segment_id: One of "01_identity", "02_structure", "03_modules", "04_constraints", "05_flows", "06_concepts", "07_dependencies"
        content: Markdown content of the segment
        source_hash: Hash of the data sources used to generate this segment
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME
    cache.write_segment(codesense_dir, segment_id, content, source_hash)


# ---------- Entry-module heuristics for 05_flows ----------------------------

_ENTRY_LAYER_KEYWORDS = frozenset({
    "tool", "tools", "handler", "handlers",
    "controller", "controllers", "server",
    "main", "api", "cli", "cmd", "endpoint", "endpoints",
    "route", "routes", "app",
})


def _identify_entry_modules(saved_modules: list[dict]) -> list[dict]:
    """Identify candidate entry modules by name heuristics."""
    candidates = []
    for m in saved_modules:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", "")).lower()
        dirs = [str(d).lower() for d in (m.get("directories") or m.get("files") or [])]
        is_candidate = any(kw in name for kw in _ENTRY_LAYER_KEYWORDS) or \
                       any(any(kw in d for kw in _ENTRY_LAYER_KEYWORDS) for d in dirs)
        if is_candidate:
            candidates.append(m)
    return candidates


# ---------- Symbol-module map for 06_concepts --------------------------------


def _build_symbol_module_map(
    saved_modules: list[dict],
    db: CodeGraphDB,
    public_kinds: tuple[str, ...] = ("function", "class", "method"),
) -> dict[str, str]:
    """Build {symbol_name: module_name} for all public symbols."""
    dir_to_module: dict[str, str] = {}
    for m in saved_modules:
        if not isinstance(m, dict):
            continue
        mname = str(m.get("name", ""))
        for d in (m.get("directories") or []):
            dir_to_module[str(d)] = mname
        for f in (m.get("files") or []):
            fp = str(f).replace("\\", "/")
            dir_to_module[fp] = mname
            parent = fp.rsplit("/", 1)[0] if "/" in fp else ""
            if parent:
                dir_to_module.setdefault(parent, mname)

    symbol_map: dict[str, str] = {}
    for node in db.iter_nodes(kinds=public_kinds):
        fp = node.file_path.replace("\\", "/")
        parent = fp.rsplit("/", 1)[0] if "/" in fp else fp
        module = dir_to_module.get(fp) or dir_to_module.get(parent)
        if module and not node.name.startswith("_"):
            symbol_map[node.name] = module
    return symbol_map


# ---------- New segment prompt generators ------------------------------------


async def get_constraints_segment_prompt(project_root: Path) -> str:
    """Return LLM prompt for generating 04_constraints."""
    import json
    from codesense_v1.data.hashes import _sha256  # noqa: F401 — used below for hash ref

    codesense_dir = project_root / _CODESENSE_DIR_NAME

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=False)
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]

    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    dir_deps = directory_dependencies(edges_all, modules_data,
                                      include_external=False, include_self_loops=False)
    layers = topological_layers(edges_all, modules_data)
    cycles = find_cycles(edges_all, modules_data)

    ref_section = ref_docs_prompt_section(project_root)

    modules_text = "\n".join(
        f"- `{m.get('name')}` ({', '.join(m.get('directories', []) or m.get('files', []))}): {m.get('description', '')}"
        for m in saved_modules if isinstance(m, dict)
    )
    deps_text = "\n".join(
        f"- {src} → {', '.join(tgts.get('imports', []))}"
        for src, tgts in dir_deps.items() if tgts.get('imports')
    )
    layers_text = "\n".join(
        f"- 第{i}层: {', '.join(sorted(layer))}"
        for i, layer in enumerate(layers)
    )
    cycle_text = "无循环依赖" if not cycles else "\n".join(
        f"- 循环: {' → '.join(c)}" for c in cycles
    )

    return (
        "# 模块边界规则生成\n\n"
        "你是一位软件架构师。请根据以下模块结构数据，推断并总结项目的**架构规则与边界约束**。\n\n"
        "## 输出格式（Markdown）\n\n"
        "```markdown\n"
        "## 模块边界规则\n\n"
        "### 层次约束\n"
        "- <层次结构规则，如「server → registry → tools → summarizer」单向依赖>\n\n"
        "### 访问禁忌\n"
        "- <哪些模块不能直接调用哪些，如「tools 层禁止直接操作 .codesense/ 目录」>\n\n"
        "### 职责边界\n"
        "- <每层的唯一职责，如「data 层只读，不写任何文件」>\n\n"
        "### 新增代码约束\n"
        "- <新增功能时必须遵守的规则>\n"
        "```\n\n"
        "## 模块数据\n\n"
        f"### 模块列表\n{modules_text}\n\n"
        f"### 模块间依赖（imports）\n{deps_text or '（无数据）'}\n\n"
        f"### 拓扑层次\n{layers_text or '（无数据）'}\n\n"
        f"### 循环依赖\n{cycle_text}\n\n"
        + (f"## 参考文档\n\n{ref_section}\n" if ref_section else "")
        + "**注意**：规则要基于数据推断，不要凭空捏造；如推断依据不足，请注明「待人工补充」。"
    )


async def get_flows_segment_prompt(project_root: Path) -> str:
    """Return LLM prompt for generating 05_flows."""
    from codesense_v1.data.aggregate import directory_symbols

    codesense_dir = project_root / _CODESENSE_DIR_NAME

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_imports = [e for e in module_dependencies(db, include_external=False)
                         if getattr(e, 'kind', '') == "imports"]
        dir_syms = directory_symbols(db, max_per_dir=20)

    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    candidates = _identify_entry_modules(saved_modules)
    candidate_names = [m.get("name", "") for m in candidates]

    entry_syms_text = ""
    for m in candidates:
        dirs = m.get("directories") or [str(f).rsplit("/", 1)[0] for f in (m.get("files") or [])]
        syms = []
        for d in dirs:
            syms.extend(dir_syms.get(d, []))
        if syms:
            sym_str = ", ".join(s["name"] for s in syms[:10])
            entry_syms_text += f"\n- `{m.get('name')}` 符号: [{sym_str}]"

    ref_section = ref_docs_prompt_section(project_root)

    return (
        "# 关键流程描述生成\n\n"
        "你是一位软件架构师。请根据以下数据，识别并描述项目中**最重要的跨模块端到端流程**（3-5 个）。\n\n"
        "## 输出格式（Markdown）\n\n"
        "```markdown\n"
        "## 关键流程描述\n\n"
        "### 流程名称\n"
        "**场景**：<什么时候触发>\n"
        "**调用链**：模块A → 模块B → 模块C\n"
        "**关键步骤**：\n"
        "1. <步骤1>\n"
        "2. <步骤2>\n"
        "3. <步骤3>\n"
        "```\n\n"
        "## 候选入口模块（程序启发式识别，请根据实际情况确认/修改）\n\n"
        f"以下模块可能是流程入口：**{', '.join(candidate_names) or '（未识别到，请自行判断）'}**\n"
        f"{entry_syms_text}\n\n"
        "如有遗漏或误判（如项目用不同命名规范），请在流程描述中自行补充正确入口。\n\n"
        "## 模块列表（用于理解跨模块协作）\n\n"
        + "\n".join(
            f"- `{m.get('name')}`: {m.get('description', '')}"
            for m in saved_modules if isinstance(m, dict)
        )
        + "\n\n"
        + (f"## 参考文档\n\n{ref_section}\n" if ref_section else "")
        + "**要求**：每个流程必须跨越至少 2 个模块；描述要具体到函数名或数据流向，不要泛泛而谈。"
    )


async def get_concepts_segment_prompt(project_root: Path) -> str:
    """Return LLM prompt for generating 06_concepts."""
    codesense_dir = project_root / _CODESENSE_DIR_NAME

    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    with CodeGraphDB(project_root) as db:
        symbol_map = _build_symbol_module_map(saved_modules, db)

    module_symbols: dict[str, list[str]] = {}
    for sym, mod in symbol_map.items():
        module_symbols.setdefault(mod, []).append(sym)

    symbol_table_text = "\n".join(
        f"- 模块 `{mod}` 公开符号: {', '.join(sorted(syms)[:15])}"
        for mod, syms in sorted(module_symbols.items())
    )

    modules_text = "\n".join(
        f"- `{m.get('name')}`: {m.get('description', '')}"
        for m in saved_modules if isinstance(m, dict)
    )

    return (
        "# 概念索引生成\n\n"
        "你是一位软件架构师。请根据以下数据，生成项目的**概念索引**——即「用户可能会用哪些词语搜索，对应的是哪个模块/符号」。\n\n"
        "## 输出格式（Markdown，表格形式）\n\n"
        "```markdown\n"
        "## 概念索引\n\n"
        "| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |\n"
        "|-----------------|---------|---------|------|\n"
        "| 关键词（中文或英文）| 模块名 | 函数/类名 | 易混淆提示或说明 |\n"
        "```\n\n"
        "## 要求\n"
        "1. 关键词要覆盖：业务操作词（如「缓存失效」「模块划分」）+ 技术词（如「segment」「prompt」）\n"
        "2. 对同名/近义系统，必须加「备注」区分（如「submit_project_map vs save_project_map_segment 的区别」）\n"
        "3. 至少 15 条，覆盖所有模块\n\n"
        "## 程序提取的符号-模块映射（已完成，你只需添加关键词和备注）\n\n"
        f"{symbol_table_text}\n\n"
        "## 模块描述\n\n"
        f"{modules_text}\n\n"
        "**注意**：关键词要是用户实际可能搜索的词，不要是技术实现细节词；备注栏专门写易混淆说明。"
    )
