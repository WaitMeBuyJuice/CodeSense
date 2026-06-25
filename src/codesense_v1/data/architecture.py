"""Language-agnostic architecture features derived from the dependency graph.

All outputs are pure graph metrics or symbol reachability, so they apply
uniformly across Python, TypeScript/JavaScript, Go, Rust, Java, Erlang, etc.
No language-specific export rules (e.g. `__all__`, `pub`, capitalized names)
are consulted; "public API" is inferred from cross-directory import edges.

Provided signals (per directory):
  - Centrality:       fan_in / fan_out / external fan-out counts.
  - Layering:         topological layers (0 = foundation) over the
                      directory DAG, with cycles contracted to SCCs.
  - Cycles:           strongly connected components of size > 1.
  - Public API:       symbols imported by code outside the directory.
  - External deps:    per-directory list of `external::` import targets.
"""

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.modules import Module, ModuleEdge


@dataclass(frozen=True)
class DirCentrality:
    """Per-directory connectivity metrics (internal + external)."""

    directory: str
    fan_in: int             # distinct internal directories that depend on this one
    fan_out: int            # distinct internal directories this one depends on
    fan_out_external: int   # distinct external modules this one depends on


@dataclass(frozen=True)
class ArchitectureFeatures:
    """Bundle of all language-agnostic architecture signals."""

    centrality: dict[str, DirCentrality]
    layers: list[list[str]]                  # layers[0] = foundation
    cycles: list[list[str]]                  # SCCs with > 1 member
    public_api: dict[str, list[str]]         # dir → externally-imported symbols
    external_by_dir: dict[str, list[str]]    # dir → external module names


# ---------- helpers ---------------------------------------------------------


def _dir_of(file_path: str, max_depth: int | None) -> str:
    parts = PurePosixPath(file_path.replace("\\", "/")).parts[:-1]
    if max_depth is not None:
        parts = parts[:max_depth]
    return "/".join(parts) if parts else "."


def _build_dir_adj(
    edges: Iterable[ModuleEdge],
    dir_by_module: dict[str, str],
) -> dict[str, set[str]]:
    """Directory-level adjacency (src_dir → set of tgt_dirs), internal edges only."""
    adj: dict[str, set[str]] = {d: set() for d in set(dir_by_module.values())}
    for e in edges:
        if e.is_external:
            continue
        src = dir_by_module.get(e.source)
        tgt = dir_by_module.get(e.target)
        if src is None or tgt is None or src == tgt:
            continue
        adj.setdefault(src, set()).add(tgt)
        adj.setdefault(tgt, set())
    return adj


def _tarjan_sccs(adj: dict[str, set[str]]) -> list[list[str]]:
    """Return all SCCs of `adj` (each SCC is a list of node ids)."""
    # Iterative Tarjan to avoid Python recursion limit on large graphs.
    index_counter = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(adj) * 4 + 100))

    for start in adj:
        if start in indices:
            continue
        # DFS frame: (node, iterator over its successors)
        work: list[tuple[str, list[str]]] = [(start, sorted(adj[start]))]
        indices[start] = index_counter
        lowlink[start] = index_counter
        index_counter += 1
        stack.append(start)
        on_stack.add(start)

        while work:
            v, succs = work[-1]
            if succs:
                w = succs.pop()
                if w not in indices:
                    indices[w] = index_counter
                    lowlink[w] = index_counter
                    index_counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, sorted(adj.get(w, set()))))
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])
            else:
                # Finished v: propagate lowlink to parent, possibly emit SCC.
                if lowlink[v] == indices[v]:
                    comp: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    sccs.append(sorted(comp))
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])

    return sccs


# ---------- public API: centrality -----------------------------------------


def compute_centrality(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
) -> dict[str, DirCentrality]:
    """Per-directory fan-in / fan-out (internal) and external fan-out counts.

    A directory's fan-in is the number of *distinct* other directories that
    have at least one edge into it. Cross-language safe.
    """
    dir_by_module = {m.id: _dir_of(m.file_path, max_depth) for m in modules}
    all_dirs: set[str] = set(dir_by_module.values())

    fan_in: dict[str, set[str]] = {d: set() for d in all_dirs}
    fan_out: dict[str, set[str]] = {d: set() for d in all_dirs}
    fan_out_ext: dict[str, set[str]] = {d: set() for d in all_dirs}

    for e in edges:
        src_dir = dir_by_module.get(e.source)
        if src_dir is None:
            continue
        if e.is_external:
            fan_out_ext.setdefault(src_dir, set()).add(e.target)
            continue
        tgt_dir = dir_by_module.get(e.target)
        if tgt_dir is None or src_dir == tgt_dir:
            continue
        fan_out.setdefault(src_dir, set()).add(tgt_dir)
        fan_in.setdefault(tgt_dir, set()).add(src_dir)

    return {
        d: DirCentrality(
            directory=d,
            fan_in=len(fan_in.get(d, set())),
            fan_out=len(fan_out.get(d, set())),
            fan_out_external=len(fan_out_ext.get(d, set())),
        )
        for d in sorted(all_dirs)
    }


# ---------- public API: cycles & layering ----------------------------------


def find_cycles(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
) -> list[list[str]]:
    """Strongly connected components of size > 1 (i.e. real cycles)."""
    dir_by_module = {m.id: _dir_of(m.file_path, max_depth) for m in modules}
    adj = _build_dir_adj(edges, dir_by_module)
    return [comp for comp in _tarjan_sccs(adj) if len(comp) > 1]


def topological_layers(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
) -> list[list[str]]:
    """Stratify directories from foundation (layer 0) upward.

    Layer 0 contains directories with no outgoing internal dependencies
    (graph leaves). Cycles are contracted to a single super-node so the
    result is well-defined even with cyclic codebases.
    """
    dir_by_module = {m.id: _dir_of(m.file_path, max_depth) for m in modules}
    adj = _build_dir_adj(edges, dir_by_module)

    sccs = _tarjan_sccs(adj)
    scc_of: dict[str, int] = {}
    scc_members: dict[int, list[str]] = {}
    for sid, comp in enumerate(sccs):
        scc_members[sid] = comp
        for d in comp:
            scc_of[d] = sid

    # Condensed DAG over SCC ids.
    cdag: dict[int, set[int]] = {sid: set() for sid in scc_members}
    for src, tgts in adj.items():
        s = scc_of[src]
        for t in tgts:
            ts = scc_of[t]
            if ts != s:
                cdag[s].add(ts)

    # layer(s) = 0 if no outgoing in cdag, else 1 + max(layer of successors).
    layer_of: dict[int, int] = {}
    # Iterative post-order DFS to avoid recursion limits.
    order: list[int] = []
    seen: set[int] = set()
    for start in cdag:
        if start in seen:
            continue
        stack: list[tuple[int, list[int]]] = [(start, sorted(cdag[start]))]
        seen.add(start)
        while stack:
            node, succs = stack[-1]
            if succs:
                nxt = succs.pop()
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append((nxt, sorted(cdag[nxt])))
            else:
                order.append(node)
                stack.pop()
    for node in order:  # reverse topo: successors first
        succs = cdag[node]
        layer_of[node] = 1 + max((layer_of[s] for s in succs), default=-1)

    max_layer = max(layer_of.values(), default=0)
    layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for sid, lvl in layer_of.items():
        layers[lvl].extend(scc_members[sid])
    for lst in layers:
        lst.sort()
    return layers


# ---------- public API: cross-directory public surface ---------------------


def cross_dir_public_api(
    db: CodeGraphDB,
    *,
    max_depth: int | None = None,
    max_per_dir: int | None = 30,
    symbol_kinds: tuple[str, ...] = ("function", "class", "method", "variable"),
) -> dict[str, list[str]]:
    """For each directory, list symbols imported by code *outside* that directory.

    Pure graph derivation — works the same for any language CodeGraph indexes.
    Returns qualified names where available, otherwise plain names.
    """
    nodes_by_id = {n.id: n for n in db.iter_nodes()}
    out: dict[str, set[str]] = {}
    for e in db.iter_edges(kinds=("imports",)):
        src = nodes_by_id.get(e.source)
        tgt = nodes_by_id.get(e.target)
        if src is None or tgt is None:
            continue
        if tgt.kind == "import":
            # External placeholder; not a project symbol.
            continue
        if tgt.kind not in symbol_kinds and tgt.kind != "file":
            continue
        src_dir = _dir_of(src.file_path, max_depth)
        tgt_dir = _dir_of(tgt.file_path, max_depth)
        if src_dir == tgt_dir:
            continue
        label = tgt.qualified_name or tgt.name
        out.setdefault(tgt_dir, set()).add(label)

    return {
        d: (sorted(syms)[:max_per_dir] if max_per_dir is not None else sorted(syms))
        for d, syms in sorted(out.items())
    }


# ---------- public API: external dependency aggregation --------------------


def external_dependencies_by_dir(
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
    max_per_dir: int | None = 20,
) -> dict[str, list[str]]:
    """Aggregate external (`external::`) import targets per directory."""
    dir_by_module = {m.id: _dir_of(m.file_path, max_depth) for m in modules}
    out: dict[str, set[str]] = {}
    for e in edges:
        if not e.is_external:
            continue
        src_dir = dir_by_module.get(e.source)
        if src_dir is None:
            continue
        out.setdefault(src_dir, set()).add(e.target)
    return {
        d: (sorted(deps)[:max_per_dir] if max_per_dir is not None else sorted(deps))
        for d, deps in sorted(out.items())
    }


# ---------- bundle ---------------------------------------------------------


def architecture_features(
    db: CodeGraphDB,
    edges: list[ModuleEdge],
    modules: list[Module],
    *,
    max_depth: int | None = None,
) -> ArchitectureFeatures:
    """One-shot computation of all language-agnostic architecture signals."""
    return ArchitectureFeatures(
        centrality=compute_centrality(edges, modules, max_depth=max_depth),
        layers=topological_layers(edges, modules, max_depth=max_depth),
        cycles=find_cycles(edges, modules, max_depth=max_depth),
        public_api=cross_dir_public_api(db, max_depth=max_depth),
        external_by_dir=external_dependencies_by_dir(edges, modules, max_depth=max_depth),
    )
