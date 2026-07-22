"""Read/write cache for the `.codesense/` directory.

All `read_*` functions return ``None`` on any error (treat as cache miss).
All `write_*` functions propagate ``OSError`` on genuine I/O failure.
``invalidate`` silently ignores missing files/dirs; clears entire cache:
project_map, modules_index, project_map.json, and all module files.
``db_hash`` propagates ``FileNotFoundError`` when the DB is absent.
``is_cache_valid`` returns ``False`` on any error.
"""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

_CHUNK = 65536
_META_FILE = "project_map.json"
_PROJECT_MAP_FILE = "project_map.md"
_MODULES_INDEX_FILE = "modules_index.json"
_MODULES_DIR = "modules"
_MODULE_HASHES_FILE = ".hashes.json"
_SEGMENTS_DIR = "project_map_segments"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017


def _meta_path(codesense_dir: Path) -> Path:
    return codesense_dir / _META_FILE


def db_hash(db_path: Path) -> str:
    """Compute SHA-256 hex digest of the file at *db_path*.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    h = hashlib.sha256()
    with open(db_path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def is_cache_valid(codesense_dir: Path, current_hash: str) -> bool:
    """Return ``True`` iff ``project_map.json`` exists and its ``db_hash`` matches *current_hash*."""
    try:
        meta = json.loads(_meta_path(codesense_dir).read_text(encoding="utf-8"))
        return str(meta.get("db_hash", "")) == current_hash
    except Exception:  # noqa: BLE001
        return False


def read_project_map(codesense_dir: Path) -> str | None:
    """Return content of ``project_map.md``, or ``None`` if missing/unreadable."""
    try:
        return (codesense_dir / _PROJECT_MAP_FILE).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def write_project_map(codesense_dir: Path, content: str, current_hash: str) -> None:
    """Write ``project_map.md`` and update ``meta.json`` with *current_hash*.

    Creates *codesense_dir* if it does not exist.
    """
    codesense_dir.mkdir(parents=True, exist_ok=True)
    (codesense_dir / _PROJECT_MAP_FILE).write_text(content, encoding="utf-8")
    _write_meta(codesense_dir, current_hash)


def read_modules_index(codesense_dir: Path) -> dict[str, object] | None:
    """Return parsed content of ``modules_index.json``, or ``None`` if missing/unreadable."""
    try:
        raw = (codesense_dir / _MODULES_INDEX_FILE).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def write_modules_index(
    codesense_dir: Path,
    modules: list[dict[str, object]],
    current_hash: str,
    aux_dirs: list[dict[str, object]] | None = None,
) -> None:
    """Write ``modules_index.json``, prune stale module files, update ``meta.json``.

    *aux_dirs* (optional) is stored under ``"auxiliary_dirs"`` for L2 directory info.
    Only removes ``.md`` files and hash entries for modules that no longer appear
    in the new index (by safe_key).  Existing module summaries for surviving
    modules are preserved so per-module invalidation can decide whether to
    regenerate.

    Subgroups defined on existing entries are preserved: if the old index already
    has ``subgroups`` for a module, they are merged into the new entry (keeping
    only subgroup items whose files are still present in the module's file list).

    Creates *codesense_dir* if it does not exist.
    """
    # Collect existing subgroups before pruning
    old_index = read_modules_index(codesense_dir)
    old_modules: list[dict[str, object]] = []
    if old_index is not None:
        raw = old_index.get("modules")
        if isinstance(raw, list):
            old_modules = [m for m in raw if isinstance(m, dict)]
    old_subgroups_map: dict[str, list] = {
        str(m.get("name", "")): list(m.get("subgroups") or [])
        for m in old_modules
    }

    new_keys = {safe_key(str(m.get("name", ""))) for m in modules}
    _prune_stale_modules(codesense_dir, new_keys)
    codesense_dir.mkdir(parents=True, exist_ok=True)

    # Merge old subgroups into new module entries
    merged_modules: list[dict[str, object]] = []
    for m in modules:
        m_name = str(m.get("name", ""))
        old_sgs = old_subgroups_map.get(m_name)
        if old_sgs:
            # Only keep subgroup items whose files are still in the module's file list
            m_files = set(str(f) for f in (m.get("files") or []))
            cleaned: list[dict] = []
            for sg in old_sgs:
                sg_files = [f for f in (sg.get("files") or []) if f in m_files]
                if sg_files:
                    cleaned.append({**sg, "files": sg_files})
            if cleaned:
                m = {**m, "subgroups": cleaned}
        merged_modules.append(m)

    payload: dict[str, object] = {
        "generated_at": _now_iso(),
        "modules": merged_modules,
    }
    if aux_dirs is not None:
        payload["auxiliary_dirs"] = aux_dirs
    (codesense_dir / _MODULES_INDEX_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_meta(codesense_dir, current_hash)


def read_module_hashes(codesense_dir: Path) -> dict[str, str]:
    """Aggregate module overview hashes from each ``modules/<mkey>/.hashes.json``.

    Each per-module ``.hashes.json`` stores at least a ``"overview"`` key.
    Returns ``{mkey: hash}`` for all modules that have a recorded overview hash.
    Returns an empty dict on any error (treat as all-miss).
    """
    modules_dir = codesense_dir / _MODULES_DIR
    result: dict[str, str] = {}
    if not modules_dir.is_dir():
        return result
    for child in modules_dir.iterdir():
        if not child.is_dir():
            continue
        mkey = child.name
        hashes_path = child / _MODULE_HASHES_FILE
        try:
            data = json.loads(hashes_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            entry = data.get("overview")
            if isinstance(entry, str):
                result[mkey] = entry
            elif isinstance(entry, dict):
                result[mkey] = str(entry.get("hash", ""))
        except Exception:  # noqa: BLE001
            continue
    return result


def write_module_hash(codesense_dir: Path, module_key_str: str, module_hash: str) -> None:
    """Upsert *module_hash* under key ``"overview"`` in ``modules/<mkey>/.hashes.json``."""
    mkey_dir = codesense_dir / _MODULES_DIR / module_key_str
    mkey_dir.mkdir(parents=True, exist_ok=True)
    hashes_path = mkey_dir / _MODULE_HASHES_FILE
    try:
        full_data: dict[str, object] = json.loads(hashes_path.read_text(encoding="utf-8"))
        if not isinstance(full_data, dict):
            full_data = {}
    except Exception:  # noqa: BLE001
        full_data = {}
    full_data["overview"] = {"hash": module_hash, "generated_at": _now_iso()}
    hashes_path.write_text(
        json.dumps(full_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_module(codesense_dir: Path, module_key_str: str) -> str | None:
    """Return module summary from ``modules/<mkey>/<mkey>_overview.md``, or ``None`` if missing."""
    try:
        return (
            codesense_dir / _MODULES_DIR / module_key_str / f"{module_key_str}_overview.md"
        ).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def write_module(
    codesense_dir: Path,
    module_key_str: str,
    module_name: str,  # noqa: ARG001 — kept for API compatibility
    summary: str,
    current_hash: str,
    module_content_hash: str = "",
) -> None:
    """Write ``modules/<mkey>/<mkey>_overview.md``, update per-module hash, update ``meta.json``.

    *module_content_hash* is stored in ``modules/<mkey>/.hashes.json`` under key
    ``"overview"`` for per-module invalidation.  Pass an empty string to skip hash
    persistence.
    Creates ``codesense_dir/modules/<mkey>/`` if needed.
    """
    mkey_dir = codesense_dir / _MODULES_DIR / module_key_str
    mkey_dir.mkdir(parents=True, exist_ok=True)
    (mkey_dir / f"{module_key_str}_overview.md").write_text(summary, encoding="utf-8")
    if module_content_hash:
        write_module_hash(codesense_dir, module_key_str, module_content_hash)
    _write_meta(codesense_dir, current_hash)


def invalidate(codesense_dir: Path) -> None:
    """Delete ``project_map.md``, ``modules_index.json``, ``meta.json`` and all
    ``modules/`` files (including ``.hashes.json``).

    Silently ignores missing files or directories.
    Entire cache is cleared.
    """
    for target in [
        codesense_dir / _PROJECT_MAP_FILE,
        codesense_dir / _MODULES_INDEX_FILE,
        _meta_path(codesense_dir),
    ]:
        try:
            target.unlink()
        except OSError:
            pass
    _clear_modules_dir(codesense_dir)
    invalidate_segments(codesense_dir)


def module_key(module_path: str) -> str:
    """Convert a module path to a safe filename key.

    Replaces ``/`` and ``\\`` with ``_``, strips surrounding whitespace.

    Example::

        >>> module_key("src/auth")
        'src_auth'
    """
    return module_path.strip().replace("/", "_").replace("\\", "_")


_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_key(module_name: str) -> str:
    """Generate a human-readable filename key from a module name.

    Replaces characters illegal on Windows/Linux filesystems (``/ \\ : * ? " < > |``
    and ASCII control chars) with ``_``, strips surrounding ``_``, and truncates to
    100 characters.  The original name is stored in the JSON payload under
    ``module_name``.

    Example::

        >>> safe_key("缓存层") == safe_key(" 缓存层 ")  # trim-invariant
        True
        >>> safe_key("模块 A/B (核心)")
        '模块 A_B (核心)'
    """
    sanitised = _ILLEGAL_CHARS.sub("_", module_name.strip())
    sanitised = sanitised.strip("_")
    return sanitised[:100] if sanitised else "_"


# ---------- private helpers -------------------------------------------------


def _write_meta(codesense_dir: Path, current_hash: str) -> None:
    codesense_dir.mkdir(parents=True, exist_ok=True)
    meta = {"db_hash": current_hash, "generated_at": _now_iso()}
    _meta_path(codesense_dir).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _clear_modules_dir(codesense_dir: Path) -> None:
    """Delete the entire ``modules/`` directory tree."""
    modules_dir = codesense_dir / _MODULES_DIR
    if modules_dir.is_dir():
        try:
            shutil.rmtree(modules_dir)
        except OSError:
            pass


# ---------- project_map segment cache ---------------------------------------

_SEGMENT_IDS: tuple[str, ...] = (
    "01_identity",
    "02_modules",
    "03_constraints",
    "04_flows",
    "05_concepts",
    "06_dependencies",
)


def _segment_dir(codesense_dir: Path) -> Path:
    return codesense_dir / _SEGMENTS_DIR


def _segment_md_path(codesense_dir: Path, segment_id: str) -> Path:
    return _segment_dir(codesense_dir) / f"{segment_id}.md"


def _segment_hash_path(codesense_dir: Path, segment_id: str) -> Path:
    return _segment_dir(codesense_dir) / f"{segment_id}.hash"


def read_segment(codesense_dir: Path, segment_id: str) -> str | None:
    """Return cached segment Markdown content, or None on any error."""
    try:
        return _segment_md_path(codesense_dir, segment_id).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def read_segment_hash(codesense_dir: Path, segment_id: str) -> str | None:
    """Return stored hash for a segment, or None if absent."""
    try:
        return _segment_hash_path(codesense_dir, segment_id).read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return None


def is_segment_valid(codesense_dir: Path, segment_id: str, current_hash: str) -> bool:
    """Return True iff the segment exists and its stored hash matches *current_hash*."""
    stored = read_segment_hash(codesense_dir, segment_id)
    return stored == current_hash and read_segment(codesense_dir, segment_id) is not None


def write_segment(codesense_dir: Path, segment_id: str, content: str, source_hash: str) -> None:
    """Write segment Markdown content and its source hash to disk."""
    seg_dir = _segment_dir(codesense_dir)
    seg_dir.mkdir(parents=True, exist_ok=True)
    _segment_md_path(codesense_dir, segment_id).write_text(content, encoding="utf-8")
    _segment_hash_path(codesense_dir, segment_id).write_text(source_hash, encoding="utf-8")


def render_project_map(codesense_dir: Path) -> str | None:
    """Concatenate all segment Markdown files into the final project_map.md.

    Returns None if any segment is missing.
    Writes the assembled content to project_map.md and returns it.
    """
    parts: list[str] = []
    for seg_id in _SEGMENT_IDS:
        content = read_segment(codesense_dir, seg_id)
        if content is None:
            return None
        parts.append(content.strip())

    assembled = "\n\n---\n\n".join(parts)
    (codesense_dir / _PROJECT_MAP_FILE).write_text(assembled, encoding="utf-8")
    return assembled


def invalidate_segments(codesense_dir: Path) -> None:
    """Delete all segment files under project_map_segments/."""
    seg_dir = _segment_dir(codesense_dir)
    if seg_dir.is_dir():
        for child in seg_dir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
        try:
            seg_dir.rmdir()
        except OSError:
            pass



# ── 子模块文档 ──────────────────────────────────────────────

def submodule_dir(codesense_dir: Path, module_key: str) -> Path:
    return codesense_dir / "modules" / module_key


def read_submodule_hashes(codesense_dir: Path, module_key: str) -> dict[str, str]:
    path = submodule_dir(codesense_dir, module_key) / ".hashes.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Exclude the "overview" key — that belongs to the module-level hash
        return {
            k: (v.get("hash", "") if isinstance(v, dict) else str(v))
            for k, v in data.items()
            if k != "overview" and isinstance(v, (dict, str))
        }
    except Exception:  # noqa: BLE001
        return {}


def write_submodule_hash(codesense_dir: Path, module_key: str, file_key: str, submodule_hash: str) -> None:
    hashes_path = submodule_dir(codesense_dir, module_key) / ".hashes.json"
    hashes_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {}
    if hashes_path.exists():
        try:
            with open(hashes_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {}
    data[file_key] = {"hash": submodule_hash, "generated_at": _now_iso()}
    with open(hashes_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_submodule(codesense_dir: Path, module_key: str, file_key: str) -> str | None:
    path = submodule_dir(codesense_dir, module_key) / f"{file_key}.md"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def write_submodule(
    codesense_dir: Path,
    module_key: str,
    file_key: str,
    content: str,
    submodule_hash: str,
) -> None:
    d = submodule_dir(codesense_dir, module_key)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{file_key}.md").write_text(content, encoding="utf-8")
    write_submodule_hash(codesense_dir, module_key, file_key, submodule_hash)


def _prune_stale_modules(codesense_dir: Path, active_keys: set[str]) -> None:
    """Remove module subdirectories whose name is not in *active_keys*.

    Each module now lives in its own directory ``modules/<mkey>/``; this function
    deletes any directory whose name (the module key) is absent from *active_keys*.
    """
    modules_dir = codesense_dir / _MODULES_DIR
    if not modules_dir.is_dir():
        return
    for child in modules_dir.iterdir():
        if child.is_dir() and child.name not in active_keys:
            try:
                shutil.rmtree(child)
            except OSError:
                pass
        elif child.is_file() and child.name != ".hashes.json":
            try:
                child.unlink()
            except OSError:
                pass
