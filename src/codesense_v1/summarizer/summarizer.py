"""Summarizer: coordinates Data Layer + Cache to produce Markdown summaries."""

from __future__ import annotations

import difflib
import hashlib
import os
import re
from pathlib import Path

from codesense_v1 import cache
from codesense_v1.data.aggregate import directory_dependencies, directory_symbols
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
        edges = module_dependencies(db, include_external=False)
        dir_deps = directory_dependencies(
            edges, modules_data, include_external=False, include_self_loops=False
        )
        dir_syms = directory_symbols(db, max_per_dir=50)
        all_file_paths: list[str] = [f.path.replace("\\", "/") for f in db.iter_files()]

    roots, _ = _resolve_roots_and_aux(all_file_paths)
    dir_syms = {d: s for d, s in dir_syms.items() if _is_under_roots(d, roots)}
    dir_deps = _filter_dir_deps(dir_deps, roots)
    return _build_project_map_prompt(dir_deps, dir_syms, roots=roots)


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
        edges = module_dependencies(db, include_external=False)
        dir_deps = directory_dependencies(
            edges, modules_data, include_external=False, include_self_loops=False
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

    return _build_module_prompt(entry, dir_deps, file_symbols)


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
) -> str:
    all_dirs = sorted(set(dir_deps.keys()) | set(dir_syms.keys()))
    n_dirs = len(all_dirs)
    roots_str = "、".join(f"`{r}`" for r in roots)

    dir_lines: list[str] = []
    for d in all_dirs:
        syms = dir_syms.get(d, [])
        sym_names = ", ".join(s["name"] for s in syms)
        if sym_names:
            dir_lines.append(f"- `{d}`: {len(syms)} 个符号  [{sym_names}]")
        else:
            dir_lines.append(f"- `{d}`: {len(syms)} 个符号")
    dir_section = "\n".join(dir_lines) if dir_lines else "（无目录数据）"

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
        "语义不同的目录（如 errors、llm、cache）必须独立成模块。\n\n"
        "## 输入数据\n\n"
        "### 目录结构（含代表性符号，最多 50 个/目录）\n"
        f"{dir_section}\n\n"
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

    return (
        "# 模块详细分析请求\n\n"
        "你是一位软件架构师，请根据以下模块结构数据，生成一份**模块理解文档**。\n\n"
        "## 要求\n\n"
        "输出为 Markdown 格式，包含：\n"
        "1. **概述**：该模块的核心职责（不超过 50 字）\n"
        "2. **对外接口**：列出该模块对外暴露的函数/类（参考语言惯例：Python 看名称是否以 _ 开头；"
        "TypeScript/JS 看是否 export；其他语言依据签名特征推断）\n"
        "   注意：请**仅列出下方「模块内符号」中实际存在的符号**，不要编造不存在的接口\n"
        "3. **内部文件**：该模块包含的文件列表，每个文件一句话说明作用\n"
        "4. **依赖关系**：上游（该模块依赖的目录）/ 下游（依赖该模块的目录）\n\n"
        "## 模块数据\n\n"
        f"### 模块名称\n{name}\n\n"
        f"### project_map 中的初步描述\n{description}\n\n"
        f"### 包含文件\n{files_txt}\n\n"
        f"### 模块内符号（函数/类/方法）\n{symbols_txt}\n\n"
        f"### 上游依赖（该模块依赖的目录）\n{outbound_txt}\n\n"
        f"### 下游依赖（依赖该模块的目录）\n{inbound_txt}\n"
    )
