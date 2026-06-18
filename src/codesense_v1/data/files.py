"""File listing and directory tree from the CodeGraph index."""

from dataclasses import dataclass, field
from pathlib import PurePosixPath

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


def list_files(db: CodeGraphDB) -> list[FileRow]:
    """Return every indexed file as a flat list."""
    return list(db.iter_files())


def directory_tree(db: CodeGraphDB) -> DirectoryNode:
    """Build a hierarchical directory tree of indexed files (root has empty path)."""
    root = DirectoryNode(name="", path="")
    for f in db.iter_files():
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
