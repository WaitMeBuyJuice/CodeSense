"""Read-only access to CodeGraph's SQLite database (`.codegraph/codegraph.db`).

This module is the single boundary against CodeGraph's internal storage. If the
schema ever changes, only this file should need updates.
"""

import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

DB_RELATIVE_PATH = Path(".codegraph") / "codegraph.db"


@dataclass(frozen=True)
class FileRow:
    path: str
    language: str
    size: int
    node_count: int


@dataclass(frozen=True)
class NodeRow:
    id: str
    kind: str          # file | import | function | class | method | variable | ...
    name: str
    qualified_name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    signature: str | None


@dataclass(frozen=True)
class EdgeRow:
    source: str        # node id
    target: str        # node id
    kind: str          # contains | imports | calls | ...
    line: int | None


class CodeGraphDB:
    """Thin read-only wrapper around `<project>/.codegraph/codegraph.db`.

    Use as a context manager to ensure the connection is closed:

        with CodeGraphDB(project_root) as db:
            for f in db.iter_files():
                ...
    """

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.db_path = self.project_root / DB_RELATIVE_PATH
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"CodeGraph database not found at {self.db_path}. "
                f"Run `codegraph init -i` in {self.project_root} first."
            )
        # `mode=ro` forces read-only; `uri=True` lets us pass it as a URI.
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CodeGraphDB:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    # ---- raw queries -------------------------------------------------------

    def iter_files(self) -> Iterator[FileRow]:
        cur = self._conn.execute(
            "SELECT path, language, size, node_count FROM files ORDER BY path"
        )
        for row in cur:
            yield FileRow(
                path=row["path"],
                language=row["language"],
                size=row["size"],
                node_count=row["node_count"],
            )

    def iter_nodes(self, kinds: Iterable[str] | None = None) -> Iterator[NodeRow]:
        sql = (
            "SELECT id, kind, name, qualified_name, file_path, language,"
            " start_line, end_line, signature FROM nodes"
        )
        params: tuple[str, ...] = ()
        if kinds is not None:
            kinds = tuple(kinds)
            placeholders = ",".join("?" * len(kinds))
            sql += f" WHERE kind IN ({placeholders})"
            params = kinds
        sql += " ORDER BY file_path, start_line"
        cur = self._conn.execute(sql, params)
        for row in cur:
            yield NodeRow(
                id=row["id"],
                kind=row["kind"],
                name=row["name"],
                qualified_name=row["qualified_name"],
                file_path=row["file_path"],
                language=row["language"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                signature=row["signature"],
            )

    def iter_edges(self, kinds: Iterable[str] | None = None) -> Iterator[EdgeRow]:
        sql = "SELECT source, target, kind, line FROM edges"
        params: tuple[str, ...] = ()
        if kinds is not None:
            kinds = tuple(kinds)
            placeholders = ",".join("?" * len(kinds))
            sql += f" WHERE kind IN ({placeholders})"
            params = kinds
        cur = self._conn.execute(sql, params)
        for row in cur:
            yield EdgeRow(
                source=row["source"],
                target=row["target"],
                kind=row["kind"],
                line=row["line"],
            )

    def get_node(self, node_id: str) -> NodeRow | None:
        cur = self._conn.execute(
            "SELECT id, kind, name, qualified_name, file_path, language,"
            " start_line, end_line, signature FROM nodes WHERE id = ?",
            (node_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return NodeRow(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            file_path=row["file_path"],
            language=row["language"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            signature=row["signature"],
        )

    def stats(self) -> dict[str, object]:
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM files")
        files: int = cur.fetchone()["n"]
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM nodes")
        nodes: int = cur.fetchone()["n"]
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM edges")
        edges: int = cur.fetchone()["n"]
        cur = self._conn.execute(
            "SELECT kind, COUNT(*) AS n FROM nodes GROUP BY kind ORDER BY n DESC"
        )
        by_kind = {r["kind"]: r["n"] for r in cur}
        cur = self._conn.execute(
            "SELECT kind, COUNT(*) AS n FROM edges GROUP BY kind ORDER BY n DESC"
        )
        edge_kinds = {r["kind"]: r["n"] for r in cur}
        return {
            "files": files,
            "nodes": nodes,
            "edges": edges,
            "nodes_by_kind": by_kind,
            "edges_by_kind": edge_kinds,
        }
