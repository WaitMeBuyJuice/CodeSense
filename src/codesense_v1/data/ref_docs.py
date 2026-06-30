"""Reference document discovery for CodeSense.

Scans user-configured paths for project reference documents (requirements,
design specs, feature docs, etc.) and returns their paths so that prompts can
instruct the Agent to read them as supplementary context.

Control via .codesense/.codesense_config
-----------------------------------------
``ref_docs.paths``
    List of absolute or project-relative paths (files or directories).
    When a path is a directory, its files are scanned (recursive depending on
    ``ref_docs.recursive``).  When a path is a file, it is added directly.

``ref_docs.recursive``
    Boolean (default ``false``).  When ``true``, directory entries are scanned
    recursively.

Fallback: env ``CODESENSE_REF_DOCS_DIR`` (single directory, backward compat).

Supported file types
---------------------
- Plain text:  ``.md`` ``.txt`` ``.rst`` ``.adoc`` ``.markdown``
- Word:        ``.docx``  (path only — content not extracted)
- PDF:         ``.pdf``   (path only — content not extracted)

Only regular files are collected (symlinks and directories are skipped).
"""

from __future__ import annotations

from pathlib import Path

from codesense_v1.data.config import get_ref_docs_paths, get_ref_docs_recursive

_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".txt", ".rst", ".adoc", ".markdown"}
)
_BINARY_EXTENSIONS: frozenset[str] = frozenset({".docx", ".pdf"})
_ALL_EXTENSIONS: frozenset[str] = _TEXT_EXTENSIONS | _BINARY_EXTENSIONS


def discover_ref_docs(project_root: Path) -> list[Path]:
    """Return a sorted list of reference-document paths under the configured paths.

    Returns an empty list when no paths are configured or none resolve to
    existing files/directories.  Each returned path is an absolute ``Path``.
    """
    raw_paths = get_ref_docs_paths(project_root)
    if not raw_paths:
        return []

    recursive = get_ref_docs_recursive(project_root)
    pattern = "**/*" if recursive else "*"

    files: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = project_root / p
        p = p.resolve()

        if p.is_file():
            if p.suffix.lower() in _ALL_EXTENSIONS:
                files.append(p)
        elif p.is_dir():
            for child in sorted(p.glob(pattern)):
                if child.is_file() and child.suffix.lower() in _ALL_EXTENSIONS:
                    files.append(child.resolve())

    # Deduplicate while preserving order
    seen: set[Path] = set()
    result: list[Path] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def ref_docs_prompt_section(project_root: Path) -> str:
    """Return a prompt section listing reference documents, or an empty string.

    When no documents are found the function returns ``""`` so callers can
    cheaply skip the section with a truthiness check.

    The returned section instructs the Agent to read each document and extract
    relevant information rather than embedding raw content in the prompt.
    """
    docs = discover_ref_docs(project_root)
    if not docs:
        return ""

    lines: list[str] = [
        "### 项目参考文档",
        "",
        "以下文档为项目配套的需求/设计/功能说明文档，可辅助理解模块职责和业务背景。",
        "**建议**：根据分析需要，使用 `read_file` 读取相关文档，自行提炼与当前模块/架构相关的内容。",
        "",
    ]
    for p in docs:
        suffix = p.suffix.lower()
        if suffix in _BINARY_EXTENSIONS:
            fmt_hint = f"  （{suffix.lstrip('.')} 格式，需使用对应工具读取）"
        else:
            fmt_hint = ""
        lines.append(f"- `{p}`{fmt_hint}")

    lines.append("")
    return "\n".join(lines)
