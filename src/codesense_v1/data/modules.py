"""Module-level dependency extraction.

Maps CodeGraph's file/symbol-level edges to **file-level** module edges:
  - `imports` edges:  file → import_node  ⇒  file → imported module
  - `calls`   edges:  function → function ⇒  file(src) → file(dst)

Outputs ignore intra-file (a file depending on itself) edges.

Identifiers:
  - File-level id (`Module.id`): POSIX file path verbatim, e.g.
    `codesense/data/db.py`, `src/bin/codegraph.ts`.
  - For import resolution we also derive an internal "resolve id" per file
    that matches how import statements address files (Python dotted name;
    other languages: path without extension). This is kept private.

External dependencies are emitted with the `external::` prefix in dict views
so internal vs external is visually unambiguous.
"""

from dataclasses import dataclass

from codesense_v1.data.db import CodeGraphDB, NodeRow

EXTERNAL_PREFIX = "external::"


@dataclass(frozen=True)
class Module:
    """A single source file in the project.

    `id` is the POSIX file path (e.g. `codesense/data/db.py`).
    `package_id` is the Python package or directory the file belongs to
    (e.g. `codesense.data` for Python, `src/bin` for TypeScript).
    """

    id: str               # file-level id  = POSIX file path
    file_path: str        # same as `id`, kept for clarity
    language: str
    package_id: str       # the package / directory this file belongs to


@dataclass(frozen=True)
class ModuleEdge:
    """A directed dependency between two files (or file → external module).

    `source` is always a project file id (POSIX path).
    `target` is either a project file id (`is_external=False`) or the raw
    imported module name as written in source (`is_external=True`).
    """

    source: str
    target: str
    kind: str              # "imports" | "calls"
    is_external: bool


# ---------- helpers ---------------------------------------------------------


_STRIP_EXT_LANGS = {
    "typescript": (".d.ts", ".ts", ".tsx"),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
}


def _file_id(file_path: str) -> str:
    """Public file-level id = POSIX file path."""
    return file_path.replace("\\", "/")


def _resolve_id(file_path: str, language: str) -> str:
    """Private id used only for import-statement matching.

    For Python: dotted module name (`a/b/c.py` → `a.b.c`).
    For TS/JS:  path without extension (`a/b/c.ts` → `a/b/c`).
    Other:      file path verbatim.
    """
    p = file_path.replace("\\", "/")
    if language == "python":
        if p.endswith("/__init__.py"):
            return p[: -len("/__init__.py")].replace("/", ".")
        if p == "__init__.py":
            return ""
        if p.endswith(".py"):
            return p[:-3].replace("/", ".")
    exts = _STRIP_EXT_LANGS.get(language)
    if exts:
        for ext in exts:
            if p.endswith(ext):
                return p[: -len(ext)]
    return p


def _package_id(file_path: str, language: str) -> str:
    """Package / directory this file belongs to.

    Python: dotted package name (containing directory).
            `codesense/data/db.py` → `codesense.data`
            `codesense/__init__.py` → `codesense` (the package is the file)
    Others: containing directory as POSIX slash path.
            `src/bin/codegraph.ts` → `src/bin`
            top-level file → `.`
    """
    p = file_path.replace("\\", "/")
    parts = p.split("/")
    if language == "python":
        if p.endswith("/__init__.py") or p == "__init__.py":
            # The file IS a package init — the package id is the dir itself.
            return "/".join(parts[:-1]).replace("/", ".") if len(parts) > 1 else ""
        # Regular module: package = containing directory in dotted form.
        return "/".join(parts[:-1]).replace("/", ".") if len(parts) > 1 else ""
    # Non-Python: containing directory in slash form.
    return "/".join(parts[:-1]) if len(parts) > 1 else "."


def _resolve_relative_path(source_file: str, relative: str) -> str:
    """Resolve a relative path (`./x`, `../x`) from `source_file`'s directory."""
    src_dir = "/".join(source_file.replace("\\", "/").split("/")[:-1])
    parts: list[str] = src_dir.split("/") if src_dir else []
    for seg in relative.replace("\\", "/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def _resolve_internal_import(
    import_name: str,
    source_file: str,
    project_resolve_ids: set[str],
) -> str | None:
    """Return the project file's resolve_id that an import refers to, if any."""
    # Relative path style (TS / JS).
    if import_name.startswith(("./", "../", ".\\", "..\\")):
        resolved = _resolve_relative_path(source_file, import_name)
        if resolved in project_resolve_ids:
            return resolved
        for ext in (".d.ts", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            if resolved.endswith(ext):
                stripped = resolved[: -len(ext)]
                if stripped in project_resolve_ids:
                    return stripped
                if f"{stripped}/index" in project_resolve_ids:
                    return f"{stripped}/index"
                break
        if f"{resolved}/index" in project_resolve_ids:
            return f"{resolved}/index"
        return None

    # Dotted-name style (Python).
    if import_name in project_resolve_ids:
        return import_name
    parts = import_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in project_resolve_ids:
            return candidate
    return None


# ---------- public API ------------------------------------------------------


def list_modules(db: CodeGraphDB) -> list[Module]:
    """Return every project file as a Module (file-level id = POSIX path)."""
    out: list[Module] = []
    for f in db.iter_files():
        out.append(
            Module(
                id=_file_id(f.path),
                file_path=_file_id(f.path),
                language=f.language,
                package_id=_package_id(f.path, f.language),
            )
        )
    return out


def module_dependencies(
    db: CodeGraphDB,
    *,
    include_external: bool = True,
    include_calls: bool = True,
    include_imports: bool = True,
) -> list[ModuleEdge]:
    """Compute the file-level dependency edge set for the indexed project.

    Edge endpoints are file ids (POSIX path) for internal edges; for external
    edges the target is the raw imported module name as it appears in source.
    """
    # Build (file_path → resolve_id) and (resolve_id → file_id) maps.
    resolve_id_by_path: dict[str, str] = {}
    file_id_by_resolve_id: dict[str, str] = {}
    file_id_by_path: dict[str, str] = {}
    for f in db.iter_files():
        fid = _file_id(f.path)
        rid = _resolve_id(f.path, f.language)
        file_id_by_path[f.path] = fid
        resolve_id_by_path[f.path] = rid
        if rid:
            file_id_by_resolve_id[rid] = fid

    project_resolve_ids: set[str] = {rid for rid in resolve_id_by_path.values() if rid}

    nodes_by_id: dict[str, NodeRow] = {n.id: n for n in db.iter_nodes()}

    seen: set[tuple[str, str, str]] = set()
    edges: list[ModuleEdge] = []

    def emit(src: str, tgt: str, kind: str, external: bool) -> None:
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append(ModuleEdge(source=src, target=tgt, kind=kind, is_external=external))

    if include_imports:
        for e in db.iter_edges(kinds=("imports",)):
            src_node = nodes_by_id.get(e.source)
            tgt_node = nodes_by_id.get(e.target)
            if src_node is None or tgt_node is None:
                continue
            src_fid = file_id_by_path.get(src_node.file_path)
            if src_fid is None:
                continue

            # New-version CodeGraph already resolves internal imports to the
            # target node: tgt_node.file_path points at the real owning file
            # (and is never the source file itself). External imports remain
            # as placeholder `import` nodes whose file_path == source file.
            tgt_path = tgt_node.file_path
            if (
                tgt_node.kind != "import"
                and tgt_path in file_id_by_path
                and tgt_path != src_node.file_path
            ):
                emit(src_fid, file_id_by_path[tgt_path], "imports", external=False)
                continue

            # Fallback: legacy bare-import placeholder — match by name
            # (dotted / relative path) for older indexes and edge cases.
            imported_name = tgt_node.name
            internal_rid = _resolve_internal_import(
                imported_name, src_node.file_path, project_resolve_ids
            )
            if internal_rid is not None:
                tgt_fid = file_id_by_resolve_id.get(internal_rid)
                if tgt_fid is not None:
                    emit(src_fid, tgt_fid, "imports", external=False)
            elif include_external:
                emit(src_fid, imported_name, "imports", external=True)

    if include_calls:
        # Only trust calls edges where:
        #   - target is a callable symbol (function / method / class)
        #   - source is either a callable symbol, or a file node calling into
        #     the *same* file (top-level invocation).  A file-node source that
        #     crosses file boundaries is a CodeGraph mis-fire (e.g. a string
        #     literal "calls" triggering a spurious cross-file edge).
        _CALLABLE_KINDS = frozenset({"function", "method", "class"})
        for e in db.iter_edges(kinds=("calls",)):
            src_node = nodes_by_id.get(e.source)
            tgt_node = nodes_by_id.get(e.target)
            if src_node is None or tgt_node is None:
                continue
            if tgt_node.kind not in _CALLABLE_KINDS:
                continue
            if src_node.kind not in _CALLABLE_KINDS:
                # file-node source: only trust same-file calls
                if src_node.file_path != tgt_node.file_path:
                    continue
            src_fid = file_id_by_path.get(src_node.file_path)
            tgt_fid = file_id_by_path.get(tgt_node.file_path)
            if src_fid is None or tgt_fid is None:
                continue
            # Guard: only trust a cross-file calls edge when the source file
            # already has an imports edge to the target file.  CodeGraph
            # occasionally resolves a method name (e.g. `set.add`) to an
            # unrelated project function with the same name, producing
            # spurious cross-file calls edges.
            if src_fid != tgt_fid and (src_fid, tgt_fid, "imports") not in seen:
                continue
            emit(src_fid, tgt_fid, "calls", external=False)

    return edges


def to_file_dependency_dict(
    edges: list[ModuleEdge],
) -> dict[str, dict[str, list[str]]]:
    """File-level view: `{file_path: {imports: [...], calls: [...]}}`.

    External targets are prefixed with `external::` for visual distinction.
    """
    out: dict[str, dict[str, list[str]]] = {}
    for e in edges:
        bucket = out.setdefault(e.source, {"imports": [], "calls": []})
        tgt = f"{EXTERNAL_PREFIX}{e.target}" if e.is_external else e.target
        if tgt not in bucket[e.kind]:
            bucket[e.kind].append(tgt)
    for v in out.values():
        v["imports"].sort()
        v["calls"].sort()
    return dict(sorted(out.items()))


def to_package_dependency_dict(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    include_self_loops: bool = False,
) -> dict[str, dict[str, list[str]]]:
    """Module-level view: file edges aggregated by their owning package / dir.

    Python  : package id is a dotted name (`codesense.data`).
    Others  : package id is the containing directory (`src/bin`).

    External targets remain literal but get the `external::` prefix.
    """
    pkg_by_file: dict[str, str] = {m.id: m.package_id for m in modules}

    bucket_sets: dict[str, dict[str, set[str]]] = {}
    for e in edges:
        src_pkg = pkg_by_file.get(e.source)
        if src_pkg is None:
            continue
        if e.is_external:
            tgt = f"{EXTERNAL_PREFIX}{e.target}"
        else:
            tgt_pkg = pkg_by_file.get(e.target)
            if tgt_pkg is None:
                continue
            tgt = tgt_pkg

        if not include_self_loops and src_pkg == tgt:
            continue

        bucket = bucket_sets.setdefault(src_pkg, {"imports": set(), "calls": set()})
        bucket[e.kind].add(tgt)

    return {
        src: {kind: sorted(targets) for kind, targets in buckets.items()}
        for src, buckets in sorted(bucket_sets.items())
    }


# Backwards-compatible alias (deprecated): prefer to_file_dependency_dict.
to_dependency_dict = to_file_dependency_dict
