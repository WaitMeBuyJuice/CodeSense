"""Tests for codesense_v1.data.modules."""

import sqlite3
from pathlib import Path

from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.modules import (
    EXTERNAL_PREFIX,
    _resolve_id,
    list_modules,
    module_dependencies,
    to_file_dependency_dict,
    to_package_dependency_dict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_external_edge(db_path: Path) -> None:
    """Add an edge where target is an import node in the same file (external dep)."""
    conn = sqlite3.connect(str(db_path))
    # b.py imports 'os' — n-b-import is already in DB with name='os', kind='import'
    conn.execute(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        ("n-b-import", "n-b-import", "imports", 3),
    )
    # Add a proper external import edge: n-b-file imports n-b-import (os)
    conn.execute(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        ("n-b-file", "n-b-import", "imports", 3),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_modules_python(minimal_db_root: Path) -> None:
    with CodeGraphDB(minimal_db_root) as db:
        modules = list_modules(db)
    assert len(modules) == 2
    ids = {m.id for m in modules}
    assert "a.py" in ids
    assert "b.py" in ids
    # Python files: package_id is dotted parent dir (empty for top-level)
    for m in modules:
        assert m.language == "python"
        assert m.package_id == ""  # top-level files, no parent dir


def test_module_dependencies_internal(minimal_db_root: Path) -> None:
    # minimal DB has: n-a-import (kind=import, name='b', file_path='a.py')
    # → n-b-file (kind=file, file_path='b.py')
    # Since tgt_node.kind != 'import' and tgt_path in file_id_by_path → internal edge
    with CodeGraphDB(minimal_db_root) as db:
        edges = module_dependencies(db)
    internal = [e for e in edges if not e.is_external]
    assert len(internal) == 1
    assert internal[0].source == "a.py"
    assert internal[0].target == "b.py"
    assert internal[0].kind == "imports"


def test_module_dependencies_external(minimal_db_root: Path) -> None:
    # Add external import: b.py's file node imports b.py's import node (os)
    # tgt_node.kind == 'import' and tgt_path == src_path → falls back to name match → external
    db_path = minimal_db_root / ".codegraph" / "codegraph.db"
    _add_external_edge(db_path)
    with CodeGraphDB(minimal_db_root) as db:
        edges = module_dependencies(db)
    external = [e for e in edges if e.is_external]
    assert len(external) >= 1
    ext_targets = {e.target for e in external}
    assert "os" in ext_targets


def test_to_file_dependency_dict_sorted(minimal_db_root: Path) -> None:
    with CodeGraphDB(minimal_db_root) as db:
        edges = module_dependencies(db)
    result = to_file_dependency_dict(edges)
    keys = list(result.keys())
    assert keys == sorted(keys)
    for v in result.values():
        assert v["imports"] == sorted(v["imports"])
        assert v["calls"] == sorted(v["calls"])


def test_to_package_dependency_dict_aggregates(minimal_db_root: Path) -> None:
    with CodeGraphDB(minimal_db_root) as db:
        edges = module_dependencies(db)
        modules = list_modules(db)
    result = to_package_dependency_dict(edges, modules)
    # top-level files → package_id == "" → self-loop "" → "" suppressed by default
    # so result should be empty (a.py→b.py both in package "")
    assert isinstance(result, dict)
    # No self-loops: source pkg "" depends on target pkg "" — omitted
    for src, buckets in result.items():
        for _kind, targets in buckets.items():
            assert src not in targets


def test_resolve_id_python_init() -> None:
    assert _resolve_id("a/b/__init__.py", "python") == "a.b"


def test_resolve_id_ts() -> None:
    assert _resolve_id("src/foo.ts", "typescript") == "src/foo"


def test_external_prefix(minimal_db_root: Path) -> None:
    db_path = minimal_db_root / ".codegraph" / "codegraph.db"
    _add_external_edge(db_path)
    with CodeGraphDB(minimal_db_root) as db:
        edges = module_dependencies(db)
    result = to_file_dependency_dict(edges)
    all_targets = [t for v in result.values() for t in v["imports"]]
    external_targets = [t for t in all_targets if t.startswith(EXTERNAL_PREFIX)]
    assert len(external_targets) >= 1
