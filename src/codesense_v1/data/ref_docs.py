"""Reference document discovery for CodeSense.

Scans a user-configured directory for project reference documents (requirements,
design specs, feature docs, etc.) and returns their paths so that prompts can
instruct the Agent to read them as supplementary context.

Control via environment variable
---------------------------------
``CODESENSE_REF_DOCS_DIR``
    Absolute or project-relative path to the reference documents folder.
    When unset or pointing to a non-existent directory, discovery returns an
    empty list and no reference-docs section is added to prompts.

Supported file types
---------------------
- Plain text:  ``.md`` ``.txt`` ``.rst`` ``.adoc`` ``.markdown``
- Word:        ``.docx``  (path only — content not extracted)
- PDF:         ``.pdf``   (path only — content not extracted)

Only regular files are collected (symlinks and directories are skipped).
The scan is non-recursive by default; set ``CODESENSE_REF_DOCS_RECURSIVE=true``
to include sub-directories.
"""

from __future__ import annotations

import os
from pathlib import Path

_REF_DOCS_DIR_ENV = "CODESENSE_REF_DOCS_DIR"
_REF_DOCS_RECURSIVE_ENV = "CODESENSE_REF_DOCS_RECURSIVE"

_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".txt", ".rst", ".adoc", ".markdown"}
)
_BINARY_EXTENSIONS: frozenset[str] = frozenset({".docx", ".pdf"})
_ALL_EXTENSIONS: frozenset[str] = _TEXT_EXTENSIONS | _BINARY_EXTENSIONS


def _ref_docs_dir(project_root: Path) -> Path | None:
    """Return the resolved reference-docs directory, or ``None`` if not configured."""
    raw = os.environ.get(_REF_DOCS_DIR_ENV, "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    p = p.resolve()
    return p if p.is_dir() else None


def _is_recursive() -> bool:
    return os.environ.get(_REF_DOCS_RECURSIVE_ENV, "").strip().lower() == "true"


def discover_ref_docs(project_root: Path) -> list[Path]:
    """Return a sorted list of reference-document paths under the configured directory.

    Returns an empty list when ``CODESENSE_REF_DOCS_DIR`` is unset or the
    directory does not exist.  Each returned path is an absolute ``Path``.
    """
    docs_dir = _ref_docs_dir(project_root)
    if docs_dir is None:
        return []

    recursive = _is_recursive()
    pattern = "**/*" if recursive else "*"
    files: list[Path] = []
    for p in sorted(docs_dir.glob(pattern)):
        if p.is_file() and p.suffix.lower() in _ALL_EXTENSIONS:
            files.append(p.resolve())
    return files


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
