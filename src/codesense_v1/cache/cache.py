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

    Creates *codesense_dir* if it does not exist.
    """
    new_keys = {safe_key(str(m.get("name", ""))) for m in modules}
    _prune_stale_modules(codesense_dir, new_keys)
    codesense_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "generated_at": _now_iso(),
        "modules": modules,
    }
    if aux_dirs is not None:
        payload["auxiliary_dirs"] = aux_dirs
    (codesense_dir / _MODULES_INDEX_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_meta(codesense_dir, current_hash)


def read_module_hashes(codesense_dir: Path) -> dict[str, str]:
    """Return the per-module hash table from ``modules/.hashes.json``.

    Returns an empty dict on any error (treat as all-miss).
    """
    try:
        raw = (codesense_dir / _MODULES_DIR / _MODULE_HASHES_FILE).read_text(
            encoding="utf-8"
        )
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        result: dict[str, str] = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = v  # legacy flat format
            elif isinstance(v, dict):
                result[k] = str(v.get("hash", ""))
        return result
    except Exception:  # noqa: BLE001
        return {}


def write_module_hash(codesense_dir: Path, module_key_str: str, module_hash: str) -> None:
    """Upsert *module_hash* + ``generated_at`` for *module_key_str* in ``modules/.hashes.json``."""
    modules_dir = codesense_dir / _MODULES_DIR
    modules_dir.mkdir(parents=True, exist_ok=True)
    hashes_path = modules_dir / _MODULE_HASHES_FILE
    try:
        full_data: dict[str, object] = json.loads(hashes_path.read_text(encoding="utf-8"))
        if not isinstance(full_data, dict):
            full_data = {}
    except Exception:  # noqa: BLE001
        full_data = {}
    full_data[module_key_str] = {"hash": module_hash, "generated_at": _now_iso()}
    hashes_path.write_text(
        json.dumps(full_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_module(codesense_dir: Path, module_key_str: str) -> str | None:
    """Return module summary from ``modules/<module_key>.md``, or ``None`` if missing."""
    try:
        return (codesense_dir / _MODULES_DIR / f"{module_key_str}.md").read_text(
            encoding="utf-8"
        )
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
    """Write ``modules/<module_key>.md``, update per-module hash, update ``meta.json``.

    *module_content_hash* is stored in ``modules/.hashes.json`` for per-module
    invalidation.  Pass an empty string to skip hash persistence.
    Creates ``codesense_dir/modules/`` if needed.
    """
    modules_dir = codesense_dir / _MODULES_DIR
    modules_dir.mkdir(parents=True, exist_ok=True)
    (modules_dir / f"{module_key_str}.md").write_text(summary, encoding="utf-8")
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
    """Delete all files under ``modules/`` and the directory itself if empty."""
    modules_dir = codesense_dir / _MODULES_DIR
    if modules_dir.is_dir():
        for child in modules_dir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
        try:
            modules_dir.rmdir()
        except OSError:
            pass


# ---------- project_map segment cache ---------------------------------------

_SEGMENT_IDS: tuple[str, ...] = (
    "01_identity",
    "02_structure",
    "03_modules",
    "04_dependencies",
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



def _prune_stale_modules(codesense_dir: Path, active_keys: set[str]) -> None:
    """Remove ``.md`` files and hash entries for modules no longer in *active_keys*.

    Preserves ``.hashes.json`` and any ``.md`` whose stem is still active.
    """
    modules_dir = codesense_dir / _MODULES_DIR
    if not modules_dir.is_dir():
        return
    for child in modules_dir.iterdir():
        if child.name == _MODULE_HASHES_FILE:
            continue
        if child.suffix == ".md" and child.stem not in active_keys:
            try:
                child.unlink()
            except OSError:
                pass
    # Prune stale entries from .hashes.json
    hashes = read_module_hashes(codesense_dir)
    stale = [k for k in hashes if k not in active_keys]
    if stale:
        for k in stale:
            del hashes[k]
        (modules_dir / _MODULE_HASHES_FILE).write_text(
            json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
