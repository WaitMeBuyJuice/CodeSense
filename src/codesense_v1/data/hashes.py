"""Hash functions for project_map segment cache invalidation.

Each hash is based on structural data (file manifests, directory lists, edge sets),
NOT on Agent-generated text content — so regenerating with different wording
does NOT cause spurious cache invalidations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codesense_v1.data.modules import ModuleEdge
from codesense_v1.data.project_info import IdentitySource
from codesense_v1.data.structure import TopLevelDir


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_identity_hash(sources: list[IdentitySource]) -> str:
    """Hash based on the manifest of available identity source files.

    Manifest: sorted [(path, sha256(content)), ...]
    Stable when no sources exist (produces hash of empty list).
    Invalidates when: a source file is added/removed/modified.
    """
    manifest = sorted(
        (s.path, _sha256(s.content))
        for s in sources
    )
    return _sha256(json.dumps(manifest))


def compute_structure_hash(top_dirs: list[TopLevelDir]) -> str:
    """Hash based on sorted [(dir_name, file_count, is_auxiliary)] tuples.

    Invalidates when: top-level directories are added/removed, or file counts change.
    """
    entries = sorted(
        (d.name, d.file_count, d.is_auxiliary)
        for d in top_dirs
    )
    return _sha256(json.dumps(entries))


def compute_architecture_hash(module_dir_groups: list[list[str]]) -> str:
    """Hash based on the SET of module directory paths (not names/descriptions).

    Input: list of directory lists per module.
    Example: [["src/data"], ["src/tools", "src/handlers"]]

    Invariant: changing module names or descriptions does NOT change this hash.
    Invalidates when: module directory assignments change.
    """
    sorted_groups = sorted(sorted(dirs) for dirs in module_dir_groups)
    return _sha256(json.dumps(sorted_groups))


def compute_dependencies_hash(edges: list[ModuleEdge]) -> str:
    """Hash based on sorted set of module-level directed edges.

    Only internal edges (is_external=False) are included.
    Invalidates when: import relationships between modules change.
    Does NOT invalidate on: function body changes, internal refactoring.
    """
    edge_pairs = sorted(
        (e.source, e.target)
        for e in edges
        if not e.is_external
    )
    return _sha256(json.dumps(edge_pairs))
