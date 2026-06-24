"""Read/write cache for the `.codesense/` directory.

All `read_*` functions return ``None`` on any error (treat as cache miss).
All `write_*` functions propagate ``OSError`` on genuine I/O failure.
``invalidate`` silently ignores missing files/dirs; clears entire cache:
project_map, modules_index, meta, and all module files.
``db_hash`` propagates ``FileNotFoundError`` when the DB is absent.
``is_cache_valid`` returns ``False`` on any error.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

_CHUNK = 65536
_META_FILE = "meta.json"
_PROJECT_MAP_FILE = "project_map.md"
_MODULES_INDEX_FILE = "modules_index.json"
_MODULES_DIR = "modules"


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
    """Return ``True`` iff ``meta.json`` exists and its ``db_hash`` matches *current_hash*."""
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
) -> None:
    """Write ``modules_index.json``, clear ``modules/`` sub-cache, update ``meta.json``.

    Clears ``modules/`` sub-cache first (D7: prevents stale module summaries
    when module names change across LLM regenerations).

    Creates *codesense_dir* if it does not exist.
    """
    _clear_modules_dir(codesense_dir)
    codesense_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "generated_at": _now_iso(),
        "modules": modules,
    }
    (codesense_dir / _MODULES_INDEX_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_meta(codesense_dir, current_hash)


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
) -> None:
    """Write ``modules/<module_key>.md`` and update ``meta.json`` with *current_hash*.

    Creates ``codesense_dir/modules/`` if needed.
    """
    modules_dir = codesense_dir / _MODULES_DIR
    modules_dir.mkdir(parents=True, exist_ok=True)
    (modules_dir / f"{module_key_str}.md").write_text(summary, encoding="utf-8")
    _write_meta(codesense_dir, current_hash)


def invalidate(codesense_dir: Path) -> None:
    """Delete ``project_map.md``, ``modules_index.json``, ``meta.json`` and all
    ``modules/*.json`` files.

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
    """Delete all ``modules/*.json`` files and the directory itself if empty."""
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
