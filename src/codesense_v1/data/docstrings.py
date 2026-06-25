"""Docstring extraction from source files.

This is the **only module in the data layer that performs file I/O** (reading
source files).  All other data layer modules are strictly read-only against
the CodeGraph SQLite database.

Extraction is best-effort: every public function returns ``None`` / an empty
dict whenever a docstring cannot be located (unsupported language, missing
file, encoding error, no docstring present).  Callers must treat ``None`` as
"no docstring available" and degrade gracefully.

Supported languages and their docstring conventions
----------------------------------------------------
- **Python**:          triple-quote string ``\"\"\"...\"\"\"`` / ``\'\'\'...\'\'\'``
                       immediately inside the function/class/module body.
- **TypeScript/JS**:   JSDoc ``/** ... */`` block *before* the declaration;
                       falls back to consecutive ``//`` line comments.
- **Go**:              consecutive ``//`` line comments *before* the declaration.
- **Rust**:            ``///`` (item-level) or ``//!`` (module-level) line comments.
- **Erlang**:          consecutive ``%%`` line comments.
- **Ruby / Shell**:    consecutive ``#`` line comments.

Control via environment variable
---------------------------------
Set ``CODESENSE_EXTRACT_DOCSTRINGS=false`` to disable all extraction (e.g.
for projects whose source files are not accessible at summary time).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from codesense_v1.data.db import NodeRow

_DOCSTRING_ENV = "CODESENSE_EXTRACT_DOCSTRINGS"
_MAX_LEN = 200            # maximum characters per docstring (first line only)
_LOOKAHEAD = 10           # lines after start_line to search (Python body)
_LOOKBEHIND = 20          # lines before start_line to search (comment-before langs)
_FILE_SCAN = 30           # max lines to scan for file-level docstring

# ---------------------------------------------------------------------------
# Public control
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Return True unless ``CODESENSE_EXTRACT_DOCSTRINGS`` is set to ``false``."""
    return os.environ.get(_DOCSTRING_ENV, "true").strip().lower() != "false"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_lines(path: str | Path) -> list[str] | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _first_line(text: str) -> str | None:
    """Return the first non-empty stripped line of *text*, capped at _MAX_LEN."""
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s[:_MAX_LEN]
    return None


# ---------------------------------------------------------------------------
# Extractors: Python (docstring AFTER the declaration)
# ---------------------------------------------------------------------------

_TRIPLE = ('"""', "'''")


def _python_triple_quote(lines: list[str], start: int) -> str | None:
    """Search for a triple-quote docstring in ``lines[start:]``."""
    for i in range(start, min(start + _LOOKAHEAD, len(lines))):
        s = lines[i].strip()
        for q in _TRIPLE:
            if s.startswith(q):
                body = s[len(q):]
                close = body.find(q)
                text = body[:close] if close >= 0 else body
                return _first_line(text)
    return None


# ---------------------------------------------------------------------------
# Extractors: JSDoc /** ... */ (BEFORE the declaration)
# ---------------------------------------------------------------------------


def _jsdoc_backward(lines: list[str], end: int) -> str | None:
    """Find a ``/** ... */`` block immediately before ``lines[end]``."""
    close = -1
    for i in range(end - 1, max(end - _LOOKBEHIND, -1), -1):
        s = lines[i].strip()
        if s.endswith("*/"):
            close = i
            break
        # Stop if we hit real code (not part of a comment)
        if s and not s.startswith("*") and not s.startswith("//") and not s.startswith("/*"):
            return None
    if close < 0:
        return None
    for i in range(close, max(close - _LOOKBEHIND, -1), -1):
        s = lines[i].strip()
        if s.startswith("/**") or s.startswith("/*"):
            for k in range(i + 1, close):  # exclude the closing */ line
                content = lines[k].strip().lstrip("*").strip()
                if content and not content.startswith("@"):
                    return _first_line(content)
            return None
    return None


def _jsdoc_forward(lines: list[str]) -> str | None:
    """Find a leading ``/** ... */`` block at the top of the file."""
    for i, line in enumerate(lines[:5]):
        s = line.strip()
        if s.startswith("/**") or s.startswith("/*"):
            for j in range(i, min(i + _LOOKBEHIND, len(lines))):
                if lines[j].rstrip().endswith("*/"):
                    for k in range(i + 1, j + 1):
                        content = lines[k].strip().lstrip("*").strip()
                        if content and not content.startswith("@"):
                            return _first_line(content)
                    return None
            return None
        if s and not s.startswith("//"):
            break
    return _line_comment_forward(lines, "//")


# ---------------------------------------------------------------------------
# Extractors: single-line comment blocks
# ---------------------------------------------------------------------------


def _line_comment_backward(lines: list[str], end: int, prefix: str) -> str | None:
    """Find contiguous ``prefix`` comment lines immediately before ``lines[end]``."""
    block: list[str] = []
    for i in range(end - 1, max(end - _LOOKBEHIND, -1), -1):
        s = lines[i].strip()
        if s.startswith(prefix):
            content = s[len(prefix):].strip()
            block.insert(0, content)
        else:
            break
    for line in block:
        if line:
            return _first_line(line)
    return None


def _line_comment_forward(lines: list[str], prefix: str) -> str | None:
    """Find the first content line in a leading ``prefix`` comment block."""
    for line in lines[:_FILE_SCAN]:
        s = line.strip()
        if s.startswith(prefix):
            content = s[len(prefix):].strip()
            if content:
                return _first_line(content)
        elif s:
            break
    return None


# ---------------------------------------------------------------------------
# File-level dispatch
# ---------------------------------------------------------------------------

_PYTHON_SKIP_RE = re.compile(r"^(\s*#.*|\s*)$")


def _file_docstring_python(lines: list[str]) -> str | None:
    """Find the module-level triple-quote docstring, skipping shebang/encoding/blanks."""
    start = 0
    for i, line in enumerate(lines[:15]):
        s = line.strip()
        if s == "" or s.startswith("#"):
            start = i + 1
        else:
            break
    return _python_triple_quote(lines, start)


def _file_docstring_for_lang(lines: list[str], lang: str) -> str | None:
    l = lang.lower()
    if l == "python":
        return _file_docstring_python(lines)
    if l in ("typescript", "javascript", "typescriptreact", "javascriptreact", "tsx", "jsx"):
        return _jsdoc_forward(lines)
    if l == "go":
        return _line_comment_forward(lines, "//")
    if l == "rust":
        return _line_comment_forward(lines, "//!") or _line_comment_forward(lines, "//")
    if l == "erlang":
        return _line_comment_forward(lines, "%%")
    if l in ("ruby", "shell", "bash"):
        return _line_comment_forward(lines, "#")
    return None


# ---------------------------------------------------------------------------
# Symbol-level dispatch
# ---------------------------------------------------------------------------


def _symbol_docstring_for_lang(lines: list[str], lang: str, start_line: int) -> str | None:
    idx = start_line - 1  # 1-based → 0-based
    if not (0 <= idx < len(lines)):
        return None
    l = lang.lower()
    if l == "python":
        # Docstring is INSIDE the function body (after the def/class line)
        return _python_triple_quote(lines, idx + 1)
    if l in ("typescript", "javascript", "typescriptreact", "javascriptreact", "tsx", "jsx"):
        return _jsdoc_backward(lines, idx) or _line_comment_backward(lines, idx, "//")
    if l == "go":
        return _line_comment_backward(lines, idx, "//")
    if l == "rust":
        return _line_comment_backward(lines, idx, "///") or _line_comment_backward(lines, idx, "//")
    if l == "erlang":
        return _line_comment_backward(lines, idx, "%%")
    if l in ("ruby", "shell", "bash"):
        return _line_comment_backward(lines, idx, "#")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_file_docstring(file_path: str | Path, language: str) -> str | None:
    """Return the module/file-level docstring for *file_path*, or ``None``.

    Reads only the first :data:`_FILE_SCAN` lines.  Returns ``None`` for
    unsupported languages, missing files, or files without a docstring.
    """
    if not is_enabled():
        return None
    lines = _read_lines(file_path)
    if lines is None:
        return None
    return _file_docstring_for_lang(lines, language)


def extract_symbol_docstrings(
    file_path: str | Path,
    language: str,
    nodes: list[NodeRow],
) -> dict[str, str]:
    """Return ``{node.id: docstring}`` for nodes that have a docstring.

    Reads *file_path* exactly once regardless of how many nodes are passed.
    Nodes without a docstring are omitted from the result.
    """
    if not is_enabled() or not nodes:
        return {}
    lines = _read_lines(file_path)
    if lines is None:
        return {}
    result: dict[str, str] = {}
    for node in nodes:
        doc = _symbol_docstring_for_lang(lines, language, node.start_line)
        if doc:
            result[node.id] = doc
    return result
