"""Tests for codesense_v1.data.db (CodeGraphDB + row dataclasses)."""

import sqlite3
from pathlib import Path

import pytest

from codesense_v1.data.db import CodeGraphDB, EdgeRow, FileRow, NodeRow

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    """Create a minimal codegraph.db under tmp_path/.codegraph/."""
    db_dir = tmp_path / ".codegraph"
    db_dir.mkdir()
    db_path = db_dir / "codegraph.db"

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            language TEXT,
            size INTEGER,
            node_count INTEGER
        );
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT,
            name TEXT,
            qualified_name TEXT,
            file_path TEXT,
            language TEXT,
            start_line INTEGER,
            end_line INTEGER,
            signature TEXT
        );
        CREATE TABLE edges (
            source TEXT,
            target TEXT,
            kind TEXT,
            line INTEGER
        );
        """
    )
    # 2 files
    conn.executemany(
        "INSERT INTO files VALUES (?, ?, ?, ?)",
        [
            ("a.py", "python", 100, 2),
            ("b.py", "python", 200, 2),
        ],
    )
    # 4 nodes: 1 file node + 1 import node per file
    conn.executemany(
        "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("n-a-file", "file", "a", "a", "a.py", "python", 1, 10, None),
            ("n-a-import", "import", "b", "b", "a.py", "python", 2, 2, None),
            ("n-b-file", "file", "b", "b", "b.py", "python", 1, 10, None),
            ("n-b-import", "import", "os", "os", "b.py", "python", 2, 2, None),
        ],
    )
    # 1 imports edge: a.py's import node → b.py's file node
    conn.execute(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        ("n-a-import", "n-b-file", "imports", 2),
    )
    conn.commit()
    conn.close()
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_db_open_ok(tmp_path: Path) -> None:
    root = _make_db(tmp_path)
    with CodeGraphDB(root) as db:
        s = db.stats()
    assert s["files"] == 2
    assert s["nodes"] == 4
    assert s["edges"] == 1


def test_db_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        CodeGraphDB(tmp_path / "nonexistent")


def test_iter_files(tmp_path: Path) -> None:
    root = _make_db(tmp_path)
    with CodeGraphDB(root) as db:
        files = list(db.iter_files())
    assert len(files) == 2
    assert all(isinstance(f, FileRow) for f in files)
    assert {f.path for f in files} == {"a.py", "b.py"}


def test_iter_nodes_with_kind_filter(tmp_path: Path) -> None:
    root = _make_db(tmp_path)
    with CodeGraphDB(root) as db:
        import_nodes = list(db.iter_nodes(kinds=("import",)))
    assert len(import_nodes) == 2
    assert all(n.kind == "import" for n in import_nodes)


def test_iter_edges(tmp_path: Path) -> None:
    root = _make_db(tmp_path)
    with CodeGraphDB(root) as db:
        edges = list(db.iter_edges())
    assert len(edges) == 1
    e = edges[0]
    assert isinstance(e, EdgeRow)
    assert e.source == "n-a-import"
    assert e.target == "n-b-file"
    assert e.kind == "imports"


def test_get_node(tmp_path: Path) -> None:
    root = _make_db(tmp_path)
    with CodeGraphDB(root) as db:
        node = db.get_node("n-a-file")
        missing = db.get_node("does-not-exist")
    assert isinstance(node, NodeRow)
    assert node.kind == "file"
    assert missing is None


def test_context_manager(tmp_path: Path) -> None:
    root = _make_db(tmp_path)
    db = CodeGraphDB(root)
    with db:
        pass
    # connection closed — any query should raise
    with pytest.raises(Exception):  # noqa: B017  sqlite3 raises ProgrammingError on closed conn
        list(db.iter_files())
