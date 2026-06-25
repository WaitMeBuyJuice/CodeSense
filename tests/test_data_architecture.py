"""Tests for codesense_v1.data.architecture."""

from unittest.mock import MagicMock

import pytest

from codesense_v1.data.architecture import (
    ArchitectureFeatures,
    architecture_features,
    compute_centrality,
    cross_dir_public_api,
    external_dependencies_by_dir,
    find_cycles,
    topological_layers,
)
from codesense_v1.data.modules import Module, ModuleEdge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mod(path: str, lang: str = "python") -> Module:
    return Module(id=path, file_path=path, language=lang, package_id="")


def _edge(src: str, tgt: str, kind: str = "imports", external: bool = False) -> ModuleEdge:
    return ModuleEdge(source=src, target=tgt, kind=kind, is_external=external)


def _db_with_edges(edges: list[dict]) -> MagicMock:
    """Return a mock CodeGraphDB for cross_dir_public_api tests."""
    db = MagicMock()
    node_map: dict[str, MagicMock] = {}
    for spec in edges:
        for nid, kind, name, qname, fpath in [
            (spec["src_id"], spec["src_kind"], spec["src_name"], spec.get("src_qname", spec["src_name"]), spec["src_file"]),
            (spec["tgt_id"], spec["tgt_kind"], spec["tgt_name"], spec.get("tgt_qname", spec["tgt_name"]), spec["tgt_file"]),
        ]:
            if nid not in node_map:
                n = MagicMock()
                n.id = nid
                n.kind = kind
                n.name = name
                n.qualified_name = qname
                n.file_path = fpath
                node_map[nid] = n

    def _iter_nodes(kinds=None):
        return list(node_map.values())

    def _iter_edges(kinds=None):
        result = []
        for spec in edges:
            e = MagicMock()
            e.source = spec["src_id"]
            e.target = spec["tgt_id"]
            e.kind = spec["edge_kind"]
            result.append(e)
        return result

    db.iter_nodes.side_effect = _iter_nodes
    db.iter_edges.side_effect = _iter_edges
    return db


# ---------------------------------------------------------------------------
# compute_centrality
# ---------------------------------------------------------------------------


def test_centrality_basic() -> None:
    # lib <- src/a, src/b  (fan_in=2 for lib)
    modules = [_mod("src/a.py"), _mod("src/b.py"), _mod("lib/c.py")]
    edges = [
        _edge("src/a.py", "lib/c.py"),
        _edge("src/b.py", "lib/c.py"),
        _edge("lib/c.py", "requests", external=True),
    ]
    result = compute_centrality(edges, modules)
    assert result["lib"].fan_in == 1          # one unique source dir: "src"
    assert result["src"].fan_out == 1         # depends on one dir: "lib"
    assert result["lib"].fan_out == 0         # no internal out
    assert result["lib"].fan_out_external == 1


def test_centrality_self_loop_ignored() -> None:
    modules = [_mod("pkg/a.py"), _mod("pkg/b.py")]
    edges = [_edge("pkg/a.py", "pkg/b.py")]
    result = compute_centrality(edges, modules)
    # intra-dir edges don't count
    assert result["pkg"].fan_in == 0
    assert result["pkg"].fan_out == 0


def test_centrality_all_dirs_present() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py"), _mod("c/z.py")]
    edges: list[ModuleEdge] = []
    result = compute_centrality(edges, modules)
    assert set(result.keys()) == {"a", "b", "c"}


def test_centrality_external_counted_once() -> None:
    modules = [_mod("app/main.py")]
    edges = [
        _edge("app/main.py", "requests", external=True),
        _edge("app/main.py", "requests", external=True),  # duplicate
        _edge("app/main.py", "aiohttp", external=True),
    ]
    result = compute_centrality(edges, modules)
    assert result["app"].fan_out_external == 2


# ---------------------------------------------------------------------------
# find_cycles
# ---------------------------------------------------------------------------


def test_no_cycles_in_dag() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py"), _mod("c/z.py")]
    edges = [_edge("a/x.py", "b/y.py"), _edge("b/y.py", "c/z.py")]
    assert find_cycles(edges, modules) == []


def test_direct_cycle_detected() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py")]
    edges = [_edge("a/x.py", "b/y.py"), _edge("b/y.py", "a/x.py")]
    cycles = find_cycles(edges, modules)
    assert len(cycles) == 1
    assert sorted(cycles[0]) == ["a", "b"]


def test_self_edge_not_a_cycle() -> None:
    modules = [_mod("a/x.py")]
    edges = [_edge("a/x.py", "a/y.py")]  # intra-dir; no cross-dir edge
    assert find_cycles(edges, modules) == []


def test_three_node_cycle() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py"), _mod("c/z.py")]
    edges = [
        _edge("a/x.py", "b/y.py"),
        _edge("b/y.py", "c/z.py"),
        _edge("c/z.py", "a/x.py"),
    ]
    cycles = find_cycles(edges, modules)
    assert len(cycles) == 1
    assert sorted(cycles[0]) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# topological_layers
# ---------------------------------------------------------------------------


def test_layers_simple_chain() -> None:
    # c → b → a (a is foundation)
    modules = [_mod("a/x.py"), _mod("b/y.py"), _mod("c/z.py")]
    edges = [_edge("c/z.py", "b/y.py"), _edge("b/y.py", "a/x.py")]
    layers = topological_layers(edges, modules)
    # layer 0 = "a" (no outgoing), layer 1 = "b", layer 2 = "c"
    assert layers[0] == ["a"]
    assert layers[1] == ["b"]
    assert layers[2] == ["c"]


def test_layers_isolated_dir_in_layer_0() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py"), _mod("isolated/z.py")]
    edges = [_edge("a/x.py", "b/y.py")]
    layers = topological_layers(edges, modules)
    assert "isolated" in layers[0]
    assert "b" in layers[0]
    assert "a" in layers[1]


def test_layers_with_cycle_contracted() -> None:
    # a ↔ b (cycle), both depend on c
    modules = [_mod("a/x.py"), _mod("b/y.py"), _mod("c/z.py")]
    edges = [
        _edge("a/x.py", "b/y.py"),
        _edge("b/y.py", "a/x.py"),
        _edge("a/x.py", "c/z.py"),
        _edge("b/y.py", "c/z.py"),
    ]
    layers = topological_layers(edges, modules)
    # c at layer 0, a+b together at layer 1
    assert "c" in layers[0]
    assert "a" in layers[1]
    assert "b" in layers[1]


def test_layers_no_edges() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py")]
    layers = topological_layers([], modules)
    assert len(layers) == 1
    assert sorted(layers[0]) == ["a", "b"]


# ---------------------------------------------------------------------------
# cross_dir_public_api
# ---------------------------------------------------------------------------


def test_public_api_basic() -> None:
    edge_specs = [
        {
            "src_id": "n-src", "src_kind": "file", "src_name": "main", "src_file": "app/main.py",
            "tgt_id": "n-tgt", "tgt_kind": "function", "tgt_name": "query", "tgt_qname": "lib.db.query",
            "tgt_file": "lib/db.py",
            "edge_kind": "imports",
        }
    ]
    db = _db_with_edges(edge_specs)
    result = cross_dir_public_api(db)
    assert "lib" in result
    assert "lib.db.query" in result["lib"]


def test_public_api_intradir_excluded() -> None:
    edge_specs = [
        {
            "src_id": "n-a", "src_kind": "file", "src_name": "a", "src_file": "lib/a.py",
            "tgt_id": "n-b", "tgt_kind": "function", "tgt_name": "helper", "tgt_file": "lib/b.py",
            "edge_kind": "imports",
        }
    ]
    db = _db_with_edges(edge_specs)
    result = cross_dir_public_api(db)
    # same dir: lib → lib; should be excluded
    assert "lib" not in result


def test_public_api_external_placeholder_excluded() -> None:
    edge_specs = [
        {
            "src_id": "n-src", "src_kind": "file", "src_name": "main", "src_file": "app/main.py",
            "tgt_id": "n-ext", "tgt_kind": "import", "tgt_name": "requests", "tgt_file": "app/main.py",
            "edge_kind": "imports",
        }
    ]
    db = _db_with_edges(edge_specs)
    result = cross_dir_public_api(db)
    # import-kind placeholder = external; should not appear as public API
    assert result == {}


def test_public_api_max_per_dir() -> None:
    edge_specs = [
        {
            "src_id": f"n-src{i}", "src_kind": "file", "src_name": f"src{i}", "src_file": "app/main.py",
            "tgt_id": f"n-fn{i}", "tgt_kind": "function", "tgt_name": f"fn{i:02d}", "tgt_file": "lib/mod.py",
            "edge_kind": "imports",
        }
        for i in range(10)
    ]
    db = _db_with_edges(edge_specs)
    result = cross_dir_public_api(db, max_per_dir=3)
    assert len(result["lib"]) == 3


# ---------------------------------------------------------------------------
# external_dependencies_by_dir
# ---------------------------------------------------------------------------


def test_external_by_dir_basic() -> None:
    modules = [_mod("srv/server.py"), _mod("db/conn.py")]
    edges = [
        _edge("srv/server.py", "fastapi", external=True),
        _edge("srv/server.py", "uvicorn", external=True),
        _edge("db/conn.py", "sqlalchemy", external=True),
    ]
    result = external_dependencies_by_dir(edges, modules)
    assert sorted(result["srv"]) == ["fastapi", "uvicorn"]
    assert result["db"] == ["sqlalchemy"]


def test_external_by_dir_internal_ignored() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py")]
    edges = [_edge("a/x.py", "b/y.py", external=False)]
    result = external_dependencies_by_dir(edges, modules)
    assert result == {}


def test_external_by_dir_max_per_dir() -> None:
    modules = [_mod("app/main.py")]
    edges = [
        _edge("app/main.py", f"lib{i}", external=True)
        for i in range(10)
    ]
    result = external_dependencies_by_dir(edges, modules, max_per_dir=4)
    assert len(result["app"]) == 4


# ---------------------------------------------------------------------------
# architecture_features (smoke)
# ---------------------------------------------------------------------------


def test_architecture_features_returns_dataclass() -> None:
    modules = [_mod("a/x.py"), _mod("b/y.py")]
    edges = [_edge("a/x.py", "b/y.py")]
    edge_specs = [
        {
            "src_id": "n-ax", "src_kind": "file", "src_name": "a", "src_file": "a/x.py",
            "tgt_id": "n-by", "tgt_kind": "function", "tgt_name": "helper", "tgt_file": "b/y.py",
            "edge_kind": "imports",
        }
    ]
    db = _db_with_edges(edge_specs)
    result = architecture_features(db, edges, modules)
    assert isinstance(result, ArchitectureFeatures)
    assert "a" in result.centrality
    assert isinstance(result.layers, list)
    assert isinstance(result.cycles, list)
    assert isinstance(result.public_api, dict)
    assert isinstance(result.external_by_dir, dict)
