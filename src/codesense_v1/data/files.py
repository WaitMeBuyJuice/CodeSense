"""File listing and directory tree from the CodeGraph index."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pathspec

from codesense_v1.data.db import CodeGraphDB, FileRow


@dataclass
class DirectoryNode:
    name: str
    path: str
    files: list[FileRow] = field(default_factory=list)
    subdirs: dict[str, DirectoryNode] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "files": [
                {
                    "path": f.path,
                    "language": f.language,
                    "size": f.size,
                    "node_count": f.node_count,
                }
                for f in self.files
            ],
            "subdirs": {name: child.to_dict() for name, child in sorted(self.subdirs.items())},
        }


def _load_gitignore_spec(project_root: Path) -> pathspec.PathSpec | None:
    """Load .gitignore from *project_root* and return a PathSpec, or None if absent."""
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        return None
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def list_files(db: CodeGraphDB) -> list[FileRow]:
    """Return every indexed file as a flat list, excluding .gitignore-matched paths."""
    spec = _load_gitignore_spec(db.project_root)
    files = list(db.iter_files())
    if spec is None:
        return files
    return [f for f in files if not spec.match_file(f.path)]


def directory_tree(db: CodeGraphDB) -> DirectoryNode:
    """Build a hierarchical directory tree of indexed files (root has empty path)."""
    spec = _load_gitignore_spec(db.project_root)
    root = DirectoryNode(name="", path="")
    for f in db.iter_files():
        if spec is not None and spec.match_file(f.path):
            continue
        parts = PurePosixPath(f.path.replace("\\", "/")).parts
        # parts[-1] is the filename; parts[:-1] are directories
        cursor = root
        for i, part in enumerate(parts[:-1]):
            if part not in cursor.subdirs:
                sub_path = "/".join(parts[: i + 1])
                cursor.subdirs[part] = DirectoryNode(name=part, path=sub_path)
            cursor = cursor.subdirs[part]
        cursor.files.append(f)
    return root
