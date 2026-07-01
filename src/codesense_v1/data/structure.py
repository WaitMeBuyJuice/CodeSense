"""Top-level directory classification (shared by summarizer and segment renderers).

Moved from summarizer/summarizer.py so multiple layers can reuse without circular imports.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from typing import Final

AUXILIARY_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "test", "tests", "testing", "__tests__", "spec", "specs",
        "script", "scripts",
        "doc", "docs", "documentation", "dev-docs", "devdocs",
        "example", "examples", "sample", "samples", "demo", "demos",
    }
)

AUXILIARY_CATEGORY: Final[dict[str, str]] = {
    "test": "测试代码", "tests": "测试代码", "testing": "测试代码",
    "__tests__": "测试代码", "spec": "测试代码", "specs": "测试代码",
    "script": "辅助脚本", "scripts": "辅助脚本",
    "doc": "文档", "docs": "文档", "documentation": "文档",
    "dev-docs": "文档", "devdocs": "文档",
    "example": "示例代码", "examples": "示例代码",
    "sample": "示例代码", "samples": "示例代码",
    "demo": "示例代码", "demos": "示例代码",
}

_HAS_EXTENSION_RE: Final[re.Pattern[str]] = re.compile(r"\.[a-zA-Z0-9]+$")


@dataclass(frozen=True)
class TopLevelDir:
    """Metadata for a single top-level directory."""

    name: str
    file_count: int
    is_auxiliary: bool
    category: str | None  # human-readable label for auxiliary dirs; None for L1


def auxiliary_category(name: str) -> str | None:
    """Return the category label if *name* is an auxiliary directory, else None.

    Matches exact names and compound names whose tokens (split by ``_`` or ``-``)
    include a known auxiliary pattern, e.g. ``js_tests`` → "测试代码".
    """
    name_lower = name.lower()
    if name_lower in AUXILIARY_DIR_NAMES:
        return AUXILIARY_CATEGORY.get(name_lower, "辅助代码")
    for token in re.split(r"[_\-]", name_lower):
        if token in AUXILIARY_DIR_NAMES:
            return AUXILIARY_CATEGORY.get(token, "辅助代码")
    return None


def classify_top_dirs(all_file_paths: list[str]) -> list[TopLevelDir]:
    """Classify top-level directories from *all_file_paths*.

    Returns a list of TopLevelDir sorted by file count (descending).

    Rules:
    - L1 (primary): directories not matching any auxiliary pattern
    - L2 (auxiliary): matches AUXILIARY_DIR_NAMES or compound token
    - L3 (noise): starts with '.' or looks like a filename → silently dropped
    """
    counts: dict[str, int] = collections.Counter()
    for fp in all_file_paths:
        top = fp.split("/")[0] if "/" in fp else ""
        if top:
            counts[top] += 1

    result: list[TopLevelDir] = []
    for name, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        if name.startswith(".") or _HAS_EXTENSION_RE.search(name):
            continue
        cat = auxiliary_category(name)
        result.append(TopLevelDir(
            name=name,
            file_count=cnt,
            is_auxiliary=cat is not None,
            category=cat,
        ))
    return result


def compute_tree_max_depth(
    file_paths: list[str],
    aux_dir_names: frozenset[str] | None = None,
    floor: int = 3,
) -> int:
    """Compute the adaptive max depth needed to show all leaf source directories.

    Algorithm:
    1. Find leaf dirs (dirs that directly contain files, with no child dirs).
    2. Filter out auxiliary top-level dirs (tests/, docs/, scripts/ etc.).
    3. Return 75th percentile of leaf_dir_depth clamped to *floor*.

    Examples:
        Python (src/codesense_v1/cache/):  leaf depth 3 → max_depth = max(3, 3) = 3
        Java  (src/main/java/com/example/controller/): leaf depth 6 → max_depth = 6
        Go    (cmd/api/):                  leaf depth 2 → max_depth = max(3, 2) = 3
    """
    if aux_dir_names is None:
        aux_dir_names = AUXILIARY_DIR_NAMES

    # Collect parent dirs of all files
    all_parent_dirs: set[str] = set()
    for fp in file_paths:
        fp_norm = fp.replace("\\", "/")
        if "/" in fp_norm:
            all_parent_dirs.add(fp_norm.rsplit("/", 1)[0])

    # Leaf dirs = dirs that have no child dir in the set
    leaf_dirs = {
        d for d in all_parent_dirs
        if not any(other != d and other.startswith(d + "/") for other in all_parent_dirs)
    }

    # For intermediate path segments, only filter clear test/script patterns.
    # Docs/example dirs are only filtered at the top level to avoid
    # false-positive matches against package names (e.g. com.example).
    _INTERMEDIATE_AUX: frozenset[str] = frozenset({
        "test", "tests", "testing", "__tests__",
        "spec", "specs", "script", "scripts",
    })

    def _is_aux_path(d: str) -> bool:
        parts = [p.lower() for p in d.split("/")]
        # Top-level dir: use the full auxiliary set
        if parts[0] in aux_dir_names:
            return True
        # Intermediate dirs: only use the narrower test/script set
        return any(p in _INTERMEDIATE_AUX for p in parts[1:])

    source_leaf_dirs = [d for d in leaf_dirs if not _is_aux_path(d)]

    if not source_leaf_dirs:
        return floor

    # Depth = number of path segments (e.g. "src/pkg/cache" → 3)
    sorted_depths = sorted(len(d.split("/")) for d in source_leaf_dirs)
    # 取 75 分位深度，让浅层叶子目录（如 resources/mapper）不再拉低整体展开深度
    percentile_idx = max(0, int(len(sorted_depths) * 0.75) - 1)
    target_depth = sorted_depths[min(percentile_idx, len(sorted_depths) - 1)]
    return max(floor, target_depth)
