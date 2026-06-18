"""Summarizer: coordinates Data Layer + LLM + Cache to produce Markdown summaries."""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

from codesense_v1 import cache, llm
from codesense_v1.data.aggregate import directory_dependencies, directory_symbols
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.modules import list_modules, module_dependencies
from codesense_v1.errors import InvalidArgumentError, LLMError

_CODESENSE_DIR_NAME = ".codesense"
_EXTERNAL_PREFIX = "external::"
_DESC_MAX_LEN = 60
_NAME_MIN_LEN = 2
_NAME_MAX_LEN = 20
_FUZZY_CUTOFF = 0.85
_FALLBACK_MODULE_NAME = "其他"
_FALLBACK_MODULE_DESC = "未归类目录"
_INCLUDE_DIRS_ENV = "CODESENSE_INCLUDE_DIRS"
_DEFAULT_INCLUDE_ROOTS: tuple[str, ...] = ("src",)


def _get_include_roots() -> tuple[str, ...]:
    """Return the directory roots to be included in module analysis.

    Read from env var ``CODESENSE_INCLUDE_DIRS`` (comma-separated). Defaults to
    ``("src",)``. Empty/whitespace values fall back to the default. Trailing
    slashes and backslashes are normalised so ``"src/"``/``"src\\"`` are
    accepted equivalents.
    """
    raw = os.environ.get(_INCLUDE_DIRS_ENV, "")
    parts = [
        r.strip().replace("\\", "/").rstrip("/")
        for r in raw.split(",")
        if r.strip()
    ]
    parts = [p for p in parts if p]
    return tuple(parts) if parts else _DEFAULT_INCLUDE_ROOTS


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


def _normalize_dir(d: str, valid_dirs: set[str] | None) -> str | None:
    """Clean a single directory string. Return None if invalid (when validating)."""
    d = d.strip().strip("`").strip("'").strip('"').rstrip("/").replace("\\", "/")
    if not d:
        return None
    if not valid_dirs:
        return d
    if d in valid_dirs:
        return d
    matches = difflib.get_close_matches(d, valid_dirs, n=1, cutoff=_FUZZY_CUTOFF)
    return matches[0] if matches else None


def _dedup_description(desc: str) -> str:
    """Split desc by Chinese/ASCII commas, dedup preserving order, truncate."""
    parts = [p.strip() for p in re.split(r"[、,，]", desc) if p.strip()]
    if not parts:
        return desc.strip()[:_DESC_MAX_LEN]
    return "、".join(dict.fromkeys(parts))[:_DESC_MAX_LEN]


# ---------- public API -------------------------------------------------------


async def project_map_summary(project_root: Path) -> str:
    """Return project-level architecture summary as Markdown.

    Lazy cache: if DB hash unchanged → return cached project_map.md.
    Otherwise: invalidate, call LLM for JSON module mapping, render Markdown,
    write cache, return.

    Raises:
        FileNotFoundError: if the CodeGraph DB does not exist.
        LLMError: if the LLM call fails or returns unparseable JSON (after retry).
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME
    db_path = project_root / ".codegraph" / "codegraph.db"

    current_hash = cache.db_hash(db_path)

    if cache.is_cache_valid(codesense_dir, current_hash):
        cached = cache.read_project_map(codesense_dir)
        if cached is not None:
            return cached
    else:
        cache.invalidate(codesense_dir)

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges = module_dependencies(db, include_external=False)
        dir_deps = directory_dependencies(
            edges, modules_data, include_external=False, include_self_loops=False
        )
        dir_syms = directory_symbols(db, max_per_dir=50)
        all_file_paths: list[str] = [f.path.replace("\\", "/") for f in db.iter_files()]

    roots = _get_include_roots()
    all_file_paths = [
        p for p in all_file_paths if any(p.startswith(r + "/") for r in roots)
    ]
    dir_syms = {d: s for d, s in dir_syms.items() if _is_under_roots(d, roots)}
    dir_deps = _filter_dir_deps(dir_deps, roots)

    valid_dirs: set[str] = (
        set(dir_deps.keys())
        | set(dir_syms.keys())
        | _leaf_dirs_from_files(all_file_paths)
    )
    prompt = _build_project_map_prompt(dir_deps, dir_syms, roots=roots)
    modules_json = await _call_llm_for_modules(prompt, valid_dirs=valid_dirs)

    expanded = _expand_module_files(modules_json, all_file_paths)

    cache.write_modules_index(codesense_dir, expanded, current_hash)

    markdown = _render_project_map_markdown(expanded, dir_deps)
    cache.write_project_map(codesense_dir, markdown, current_hash)
    return markdown


async def module_summary(project_root: Path, module_name: str) -> str:
    """Return module-level summary as Markdown for *module_name*.

    *module_name* must match a name in ``.codesense/modules_index.json``
    (case-insensitive, trimmed).  If the index does not exist yet, raises
    ``InvalidArgumentError`` asking the caller to read ``project_map`` first.

    Raises:
        InvalidArgumentError: if modules_index is missing or module_name not found.
        FileNotFoundError: if the CodeGraph DB does not exist.
        LLMError: if the LLM call fails.
    """
    codesense_dir = project_root / _CODESENSE_DIR_NAME
    db_path = project_root / ".codegraph" / "codegraph.db"

    current_hash = cache.db_hash(db_path)
    mkey = cache.safe_key(module_name)

    if cache.is_cache_valid(codesense_dir, current_hash):
        cached = cache.read_module(codesense_dir, mkey)
        if cached is not None:
            return cached
    else:
        cache.invalidate(codesense_dir)

    index = cache.read_modules_index(codesense_dir)
    if index is None:
        raise InvalidArgumentError(
            "参数错误：尚未生成模块划分，请先读取 codesense://project_map 资源"
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
            f"参数错误：模块 '{module_name}' 不存在。"
            f"可用模块：{', '.join(available)}"
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

    prompt = _build_module_prompt(entry, dir_deps, file_symbols)
    summary = await llm.call_llm(prompt)
    cache.write_module(
        codesense_dir, mkey, str(entry.get("name", module_name)), summary, current_hash
    )
    return summary


# ---------- private: LLM call for module list (pipe-delimited text) ----------


async def _call_llm_for_modules(
    initial_prompt: str,
    valid_dirs: set[str] | None = None,
) -> list[dict[str, object]]:
    """Call LLM, parse modules, then validate & repair against *valid_dirs*.

    Repair pipeline (only when ``valid_dirs`` is provided):
      1. Drop / fuzzy-correct directories not in ``valid_dirs`` (inside parser).
      2. If any directory is still uncovered, run one more LLM call asking it
         to assign the missing directories.
      3. If anything still missing, append a deterministic fallback module
         ``"其他"`` so coverage is total.
    """
    response = await llm.call_llm(initial_prompt)
    modules = _parse_modules_text(response, valid_dirs)
    if not modules:
        retry_prompt = (
            initial_prompt
            + "\n\n前次输出解析为空，请确保每行严格遵循「模块名|职责|目录」格式，"
            "不要输出任何其他内容（不要标题行、不要编号、不要 Markdown）。"
        )
        response2 = await llm.call_llm(retry_prompt)
        modules = _parse_modules_text(response2, valid_dirs)
        if not modules:
            raise LLMError("LLM 未输出有效的模块列表（已重试一次）")

    if not valid_dirs:
        return modules

    missing = _missing_dirs(modules, valid_dirs)
    if missing:
        modules = await _fill_missing_dirs(modules, missing, valid_dirs)

    missing_final = _missing_dirs(modules, valid_dirs)
    if missing_final:
        modules.append(
            {
                "name": _FALLBACK_MODULE_NAME,
                "description": _FALLBACK_MODULE_DESC,
                "directories": sorted(missing_final),
            }
        )
    return modules


def _missing_dirs(
    modules: list[dict[str, object]], valid_dirs: set[str]
) -> set[str]:
    covered: set[str] = set()
    for m in modules:
        dirs_raw = m.get("directories")
        if isinstance(dirs_raw, list):
            covered.update(str(d) for d in dirs_raw)
    return valid_dirs - covered


async def _fill_missing_dirs(
    modules: list[dict[str, object]],
    missing: set[str],
    valid_dirs: set[str],
) -> list[dict[str, object]]:
    """Ask LLM to assign *missing* dirs into existing or new modules."""
    existing_names = [str(m.get("name", "")) for m in modules]
    fill_prompt = (
        "上一轮模块划分遗漏了以下目录，请把它们分配到已有模块或新增模块。\n\n"
        "## 已有模块\n"
        + "\n".join(f"- {n}" for n in existing_names)
        + "\n\n## 未分配目录\n"
        + "\n".join(f"- `{d}`" for d in sorted(missing))
        + "\n\n## 输出格式\n"
        "每行一个模块（仅输出涉及未分配目录的模块），用竖线（|）分隔三列：\n"
        "  模块名|一句话职责|所属目录（多目录用英文逗号分隔）\n"
        "- 若复用已有模块，模块名必须与上方完全一致\n"
        "- 不要输出标题行、编号、Markdown 或其他内容\n"
    )
    response = await llm.call_llm(fill_prompt)
    extra = _parse_modules_text(response, valid_dirs)

    by_name: dict[str, dict[str, object]] = {
        str(m.get("name", "")).strip().lower(): m for m in modules
    }
    for m in extra:
        key = str(m.get("name", "")).strip().lower()
        m_dirs_raw = m.get("directories")
        m_dirs: list[str] = [
            str(d) for d in (m_dirs_raw if isinstance(m_dirs_raw, list) else [])
        ]
        if key in by_name:
            target = by_name[key]
            tgt_dirs_raw = target.get("directories")
            tgt_dirs: list[str] = [
                str(d) for d in (tgt_dirs_raw if isinstance(tgt_dirs_raw, list) else [])
            ]
            for d in m_dirs:
                if d not in tgt_dirs and d in missing:
                    tgt_dirs.append(d)
            target["directories"] = tgt_dirs
        else:
            kept = [d for d in m_dirs if d in missing]
            if kept:
                modules.append(
                    {
                        "name": m.get("name", ""),
                        "description": m.get("description", ""),
                        "directories": kept,
                    }
                )
                by_name[key] = modules[-1]
    return modules


def _parse_modules_text(
    response: str,
    valid_dirs: set[str] | None = None,
) -> list[dict[str, object]]:
    """Parse pipe-delimited module list from LLM response.

    Expected line format::

        模块名|一句话职责|目录1,目录2,...

    When *valid_dirs* is provided, every directory must either match a member
    of *valid_dirs* exactly or be within fuzzy-match distance; otherwise it is
    silently dropped. Description fields are split by Chinese/ASCII commas,
    deduplicated while preserving order, and truncated to 60 chars to fix the
    "add、add、list" class of LLM hallucinations.

    Malformed lines are silently skipped; duplicate names and overlapping
    directories are deduplicated so a single bad line never breaks the whole
    result.
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
            normalized = _normalize_dir(raw, valid_dirs)
            if normalized is not None:
                dirs.append(normalized)
        clean_dirs: list[str] = []
        for d in dirs:
            if not any(
                d == s or d.startswith(s + "/") or s.startswith(d + "/")
                for s in seen_dirs
            ):
                clean_dirs.append(d)
                seen_dirs.append(d)
        if not clean_dirs:
            continue
        seen_names.add(name.lower())
        modules.append({"name": name, "description": desc, "directories": clean_dirs})

    return modules


# ---------- private: data expansion + rendering ------------------------------


def _expand_module_files(
    modules_json: list[dict[str, object]],
    all_file_paths: list[str],
) -> list[dict[str, object]]:
    """Expand ``directories`` in each module entry to a concrete ``files`` list."""
    result: list[dict[str, object]] = []
    for m in modules_json:
        dirs_raw = m.get("directories")
        dirs: list[str] = [
            str(d).rstrip("/")
            for d in (dirs_raw if isinstance(dirs_raw, list) else [])
            if d
        ]
        matched: list[str] = []
        for fp in all_file_paths:
            fp_norm = fp.rstrip("/")
            for d in dirs:
                if fp_norm == d or fp_norm.startswith(d + "/"):
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
        "1. **一句话描述**：该模块的核心职责（不超过 30 字）\n"
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
