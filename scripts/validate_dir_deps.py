"""Validate the Data Layer against a target project.

Usage:
    python scripts/validate_dir_deps.py [project_root] [--out out_base] [--name NAME]

Defaults:
    project_root = E:\\Python_Project\\CodeSense\\codegraph
    out_base     = ./out
    name         = basename of project_root

Outputs are written under `<out_base>/<name>/` so that running against
different projects does not overwrite each other:

    out/<project_name>/files_deps.json    # file-level edges: {file_path: {imports, calls}}
    out/<project_name>/module_deps.json   # module/package-level (aggregated): {package: {...}}
    out/<project_name>/summary.txt        # quick stats and sample edges
    out/<project_name>/dep_facts.json     # pre-computed graph facts for LLM consumption
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from codesense_v1.data import (
    CodeGraphDB,
    list_modules,
    module_dependencies,
    to_file_dependency_dict,
    to_package_dependency_dict,
)
from codesense_v1.data.modules import Module, ModuleEdge

DEFAULT_PROJECT = Path(r"E:\Python_Project\CodeSense\codegraph")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "project_root",
        nargs="?",
        default=str(DEFAULT_PROJECT),
        help="Project root containing .codegraph/ (default: E:\\Python_Project\\CodeSense\\codegraph)",  # noqa: E501
    )
    ap.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "out"),
        help="Base output directory; results land under <out>/<name>/ (default: ./out)",
    )
    ap.add_argument(
        "--name",
        default=None,
        help="Subdirectory name under --out; defaults to the basename of project_root",
    )
    ap.add_argument(
        "--no-external",
        action="store_true",
        help="Drop edges to external (non-project) modules.",
    )
    args = ap.parse_args()

    project_root = Path(args.project_root).resolve()
    out_base = Path(args.out).resolve()
    name: str = args.name or project_root.name
    out_dir = out_base / name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Project: {project_root}")
    print(f"[*] Output:  {out_dir}")

    with CodeGraphDB(project_root) as db:
        stats = db.stats()
        print(f"[*] Index stats: {stats['files']} files, {stats['nodes']} nodes,"
              f" {stats['edges']} edges")

        modules = list_modules(db)
        edges = module_dependencies(
            db,
            include_external=not args.no_external,
        )

    files_view = to_file_dependency_dict(edges)
    module_view = to_package_dependency_dict(edges, modules)

    (out_dir / "files_deps.json").write_text(
        json.dumps(files_view, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "module_deps.json").write_text(
        json.dumps(module_view, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # dep_facts.json — pre-computed graph facts for LLM consumption
    dep_facts = _compute_dep_facts(edges, modules, module_view)
    (out_dir / "dep_facts.json").write_text(
        json.dumps(dep_facts, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Summary
    n_internal = sum(1 for e in edges if not e.is_external)
    n_external = sum(1 for e in edges if e.is_external)
    by_kind = Counter(e.kind for e in edges)

    summary_lines = [
        f"project_root  : {project_root}",
        f"index files   : {stats['files']}",
        f"index nodes   : {stats['nodes']}",
        f"index edges   : {stats['edges']}",
        f"files         : {len(modules)}",
        f"file edges    : {len(edges)} (internal={n_internal}, external={n_external})",
        f"  by kind     : {dict(by_kind)}",
        f"modules (pkgs): {len(module_view)}",
        "",
        "sample file edges (first 10):",
    ]
    for e in edges[:10]:
        marker = "[ext]" if e.is_external else "[int]"
        summary_lines.append(f"  {e.source}  --{e.kind}-->  {e.target}  {marker}")

    summary_lines.append("")
    summary_lines.append("sample module (package) entries (first 10):")
    for src, buckets in list(module_view.items())[:10]:
        summary_lines.append(f"  {src}:")
        for kind, targets in buckets.items():
            if targets:
                shown = ", ".join(targets[:5])
                more = "" if len(targets) <= 5 else f" ... (+{len(targets) - 5})"
                summary_lines.append(f"    {kind}: {shown}{more}")

    summary = "\n".join(summary_lines) + "\n"
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")
    print()
    print(summary)
    print(f"[ok] Wrote {out_dir / 'files_deps.json'}")
    print(f"[ok] Wrote {out_dir / 'module_deps.json'}")
    print(f"[ok] Wrote {out_dir / 'summary.txt'}")
    print(f"[ok] Wrote {out_dir / 'dep_facts.json'}")


def _compute_dep_facts(
    edges: list[ModuleEdge],
    modules: list[Module],
    module_view: dict[str, dict[str, list[str]]],
) -> dict[str, object]:
    """Compute graph-theoretic facts about the project for LLM consumption.

    All expensive graph analysis (in-degree, out-degree, layer inference,
    transitive blast radius, isolated files, cycles) is done here in Python
    so the LLM receives ready-made conclusions rather than raw edge lists.
    """
    all_file_ids: set[str] = {m.id for m in modules}
    pkg_by_file: dict[str, str] = {m.id: m.package_id for m in modules}

    # --- file-level degree counts (internal only) ---------------------------
    in_degree: dict[str, int] = defaultdict(int)
    out_degree: dict[str, int] = defaultdict(int)
    for e in edges:
        if e.is_external:
            continue
        out_degree[e.source] += 1
        in_degree[e.target] += 1

    # ensure every file appears in both dicts
    for fid in all_file_ids:
        in_degree.setdefault(fid, 0)
        out_degree.setdefault(fid, 0)

    # --- fan-in / fan-out top lists -----------------------------------------
    fan_in_top = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:10]
    fan_out_top = sorted(out_degree.items(), key=lambda x: x[1], reverse=True)[:10]

    # --- isolated files (no internal edges at all) --------------------------
    isolated = sorted(
        fid for fid in all_file_ids
        if in_degree[fid] == 0 and out_degree[fid] == 0
    )

    # --- leaf files (no internal out-edges, i.e. pure foundation) -----------
    leaf_files = sorted(
        fid for fid in all_file_ids
        if out_degree[fid] == 0 and in_degree[fid] > 0
    )

    # --- layer inference (file level) ---------------------------------------
    # L0 leaf (foundation): out_internal==0, in>0
    # L_top entry: in_internal==0, out>0
    # isolated: in==out==0
    layer_foundation = leaf_files
    layer_entry = sorted(
        fid for fid in all_file_ids
        if in_degree[fid] == 0 and out_degree[fid] > 0
    )

    # --- transitive blast radius (reverse reachability from each file) ------
    # Build reverse adjacency (internal edges only)
    rev_adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if not e.is_external:
            rev_adj[e.target].append(e.source)

    def _reachable(start: str) -> set[str]:
        visited: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(rev_adj.get(node, []))
        visited.discard(start)
        return visited

    blast_radius_raw: dict[str, list[str]] = {}
    for fid in all_file_ids:
        affected = sorted(_reachable(fid))
        if affected:
            blast_radius_raw[fid] = affected
    blast_radius: dict[str, list[str]] = dict(sorted(blast_radius_raw.items()))

    # --- cycle detection (Tarjan SCC, report only non-trivial SCCs) ---------
    fwd_adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if not e.is_external:
            fwd_adj[e.source].append(e.target)

    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index_map: dict[str, int] = {}
    lowlink_map: dict[str, int] = {}
    sccs: list[list[str]] = []

    def _strongconnect(v: str) -> None:
        index_map[v] = lowlink_map[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in fwd_adj.get(v, []):
            if w not in index_map:
                _strongconnect(w)
                lowlink_map[v] = min(lowlink_map[v], lowlink_map[w])
            elif w in on_stack:
                lowlink_map[v] = min(lowlink_map[v], index_map[w])
        if lowlink_map[v] == index_map[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:
                sccs.append(sorted(scc))

    for fid in sorted(all_file_ids):
        if fid not in index_map:
            _strongconnect(fid)

    # --- package-level degree -----------------------------------------------
    pkg_in: dict[str, int] = defaultdict(int)
    pkg_out: dict[str, int] = defaultdict(int)
    for pkg, buckets in module_view.items():
        for tgt in buckets.get("imports", []) + buckets.get("calls", []):
            if not tgt.startswith("external::"):
                pkg_out[pkg] += 1
                pkg_in[tgt] += 1
    for pkg in module_view:
        pkg_in.setdefault(pkg, 0)
        pkg_out.setdefault(pkg, 0)

    # suppress unused variable warning — pkg_by_file is intentionally available
    # for future extensions but not referenced in current output fields
    _ = pkg_by_file

    return {
        "file_level": {
            "fan_in_top": [{"file": f, "in_degree": d} for f, d in fan_in_top if d > 0],
            "fan_out_top": [{"file": f, "out_degree": d} for f, d in fan_out_top if d > 0],
            "layer_foundation": layer_foundation,
            "layer_entry": layer_entry,
            "isolated_files": isolated,
            "blast_radius": blast_radius,
            "cycles": sccs,
        },
        "package_level": {
            "packages": sorted(module_view.keys()),
            "fan_in_top": sorted(pkg_in.items(), key=lambda x: x[1], reverse=True),
            "fan_out_top": sorted(pkg_out.items(), key=lambda x: x[1], reverse=True),
            "isolated_packages": sorted(
                pkg for pkg in module_view
                if pkg_in[pkg] == 0 and pkg_out[pkg] == 0
            ),
        },
    }


if __name__ == "__main__":
    main()
