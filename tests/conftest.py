"""Shared fixtures for data layer tests."""

import sqlite3
from pathlib import Path

import pytest


def _build_minimal_db(tmp_path: Path) -> Path:
    """Create a minimal codegraph.db under tmp_path/.codegraph/.

    Schema:
      - 2 files: a.py (python), b.py (python)
      - 4 nodes: file+import per file
      - 1 imports edge: n-a-import → n-b-file
    """
    db_dir = tmp_path / ".codegraph"
    db_dir.mkdir(exist_ok=True)
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
    conn.executemany(
        "INSERT INTO files VALUES (?, ?, ?, ?)",
        [
            ("a.py", "python", 100, 2),
            ("b.py", "python", 200, 2),
        ],
    )
    conn.executemany(
        "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("n-a-file", "file", "a", "a", "a.py", "python", 1, 10, None),
            ("n-a-import", "import", "b", "b", "a.py", "python", 2, 2, None),
            ("n-b-file", "file", "b", "b", "b.py", "python", 1, 10, None),
            ("n-b-import", "import", "os", "os", "b.py", "python", 2, 2, None),
        ],
    )
    conn.execute(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        ("n-a-import", "n-b-file", "imports", 2),
    )
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture()
def minimal_db_root(tmp_path: Path) -> Path:
    """Return a project root Path with a minimal codegraph.db inside."""
    return _build_minimal_db(tmp_path)
