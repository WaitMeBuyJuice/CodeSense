"""Tests for codesense_v1.data.aggregate."""

from unittest.mock import MagicMock

from codesense_v1.data.aggregate import directory_dependencies, directory_edges, directory_symbols
from codesense_v1.data.modules import EXTERNAL_PREFIX, Module, ModuleEdge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_modules() -> list[Module]:
    return [
        Module(id="src/a.py", file_path="src/a.py", language="python", package_id="src"),
        Module(id="src/b.py", file_path="src/b.py", language="python", package_id="src"),
        Module(id="lib/c.py", file_path="lib/c.py", language="python", package_id="lib"),
        Module(id="top.py", file_path="top.py", language="python", package_id=""),
    ]


def _make_edges() -> list[ModuleEdge]:
    return [
        ModuleEdge(source="src/a.py", target="lib/c.py", kind="imports", is_external=False),
        ModuleEdge(source="src/b.py", target="lib/c.py", kind="imports", is_external=False),
        ModuleEdge(source="lib/c.py", target="requests", kind="imports", is_external=True),
        ModuleEdge(source="top.py", target="src/a.py", kind="calls", is_external=False),
    ]


def _make_db_with_nodes(nodes: list[dict[str, str]]) -> MagicMock:
    """Return a mock CodeGraphDB whose iter_nodes yields the given dicts."""
    db = MagicMock()

    def _iter_nodes(kinds: tuple[str, ...] | None = None) -> list[MagicMock]:
        out = []
        for n in nodes:
            if kinds is None or n["kind"] in kinds:
                mock_node = MagicMock()
                mock_node.name = n["name"]
                mock_node.kind = n["kind"]
                mock_node.file_path = n["file_path"]
                out.append(mock_node)
        return out

    db.iter_nodes.side_effect = _iter_nodes
    return db


# ---------------------------------------------------------------------------
# Tests: directory_dependencies
# ---------------------------------------------------------------------------


def test_directory_dependencies_basic() -> None:
    modules = _make_modules()
    edges = _make_edges()
    result = directory_dependencies(edges, modules)
    # src/* → lib/*
    assert "src" in result
    assert "lib" in result["src"]["imports"]
    # lib/* → external::requests
    assert "lib" in result
    assert f"{EXTERNAL_PREFIX}requests" in result["lib"]["imports"]


def test_directory_dependencies_max_depth() -> None:
    modules = [
        Module(id="a/b/c.py", file_path="a/b/c.py", language="python", package_id="a.b"),
        Module(id="a/d/e.py", file_path="a/d/e.py", language="python", package_id="a.d"),
    ]
    edges = [
        ModuleEdge(source="a/b/c.py", target="a/d/e.py", kind="imports", is_external=False),
    ]
    result = directory_dependencies(edges, modules, max_depth=1)
    # With max_depth=1, both files belong to "a" → self-loop suppressed
    assert "a" not in result  # src==tgt=="a", self-loop dropped


def test_directory_dependencies_external_passthrough() -> None:
    modules = [
        Module(id="pkg/x.py", file_path="pkg/x.py", language="python", package_id="pkg"),
    ]
    edges = [
        ModuleEdge(source="pkg/x.py", target="numpy", kind="imports", is_external=True),
    ]
    result = directory_dependencies(edges, modules)
    assert "pkg" in result
    assert f"{EXTERNAL_PREFIX}numpy" in result["pkg"]["imports"]


def test_directory_edges_flat_list() -> None:
    modules = _make_modules()
    edges = _make_edges()
    flat = directory_edges(edges, modules)
    assert isinstance(flat, list)
    # each element is a 3-tuple
    for item in flat:
        assert len(item) == 3
        src, tgt, kind = item
        assert isinstance(src, str)
        assert isinstance(tgt, str)
        assert kind in ("imports", "calls")
    # src→lib should appear
    assert ("src", "lib", "imports") in flat


# ---------------------------------------------------------------------------
# Tests: directory_symbols
# ---------------------------------------------------------------------------


def test_directory_symbols_basic() -> None:
    nodes = [
        {"name": "foo", "kind": "function", "file_path": "src/a.py"},
        {"name": "Bar", "kind": "class", "file_path": "src/b.py"},
        {"name": "baz", "kind": "method", "file_path": "lib/c.py"},
    ]
    db = _make_db_with_nodes(nodes)
    result = directory_symbols(db)
    assert "src" in result
    assert "lib" in result
    src_names = [s["name"] for s in result["src"]]
    assert "foo" in src_names
    assert "Bar" in src_names
    lib_names = [s["name"] for s in result["lib"]]
    assert "baz" in lib_names


def test_directory_symbols_entry_fields() -> None:
    nodes = [{"name": "my_func", "kind": "function", "file_path": "pkg/mod.py"}]
    db = _make_db_with_nodes(nodes)
    result = directory_symbols(db)
    entry = result["pkg"][0]
    assert entry["name"] == "my_func"
    assert entry["kind"] == "function"
    assert entry["file"] == "pkg/mod.py"


def test_directory_symbols_max_per_dir() -> None:
    nodes = [
        {"name": f"fn{i}", "kind": "function", "file_path": "src/a.py"}
        for i in range(10)
    ]
    db = _make_db_with_nodes(nodes)
    result = directory_symbols(db, max_per_dir=3)
    assert len(result["src"]) == 3


def test_directory_symbols_max_depth() -> None:
    nodes = [
        {"name": "deep_fn", "kind": "function", "file_path": "a/b/c/mod.py"},
    ]
    db = _make_db_with_nodes(nodes)
    # max_depth=1 → dir = "a"
    result = directory_symbols(db, max_depth=1)
    assert "a" in result
    assert "a/b" not in result
    assert "a/b/c" not in result


def test_directory_symbols_top_level_file() -> None:
    nodes = [{"name": "top_fn", "kind": "function", "file_path": "top.py"}]
    db = _make_db_with_nodes(nodes)
    result = directory_symbols(db)
    assert "." in result
    assert result["."][0]["name"] == "top_fn"


def test_directory_symbols_backslash_normalised() -> None:
    nodes = [{"name": "win_fn", "kind": "function", "file_path": "src\\mod.py"}]
    db = _make_db_with_nodes(nodes)
    result = directory_symbols(db)
    assert "src" in result


def test_directory_symbols_returns_sorted_dirs() -> None:
    nodes = [
        {"name": "z", "kind": "function", "file_path": "z/a.py"},
        {"name": "a", "kind": "function", "file_path": "a/b.py"},
    ]
    db = _make_db_with_nodes(nodes)
    result = directory_symbols(db)
    keys = list(result.keys())
    assert keys == sorted(keys)
