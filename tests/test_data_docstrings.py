"""Tests for codesense_v1.data.docstrings."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codesense_v1.data.docstrings import (
    _file_docstring_for_lang,
    _jsdoc_backward,
    _jsdoc_forward,
    _line_comment_backward,
    _line_comment_forward,
    _python_triple_quote,
    extract_file_docstring,
    extract_symbol_docstrings,
    is_enabled,
)


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------


def test_is_enabled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODESENSE_EXTRACT_DOCSTRINGS", raising=False)
    assert is_enabled() is True


def test_is_enabled_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_EXTRACT_DOCSTRINGS", "false")
    assert is_enabled() is False


def test_is_enabled_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_EXTRACT_DOCSTRINGS", "FALSE")
    assert is_enabled() is False


def test_is_enabled_other_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_EXTRACT_DOCSTRINGS", "0")
    assert is_enabled() is True  # only "false" disables


# ---------------------------------------------------------------------------
# _python_triple_quote
# ---------------------------------------------------------------------------


def test_python_triple_double_quote() -> None:
    lines = ['def foo():', '    """Return the answer."""', '    return 42']
    assert _python_triple_quote(lines, 1) == "Return the answer."


def test_python_triple_single_quote() -> None:
    lines = ["def foo():", "    '''Single-quote docstring.'''", "    pass"]
    assert _python_triple_quote(lines, 1) == "Single-quote docstring."


def test_python_triple_multiline_takes_first_line() -> None:
    lines = [
        "def foo():",
        '    """First line summary.',
        "    Second line detail.",
        '    """',
        "    pass",
    ]
    assert _python_triple_quote(lines, 1) == "First line summary."


def test_python_triple_skips_blank_body_lines() -> None:
    lines = ["def foo():", "    x = 1", '    """Docstring here."""']
    # Lookahead finds it within range
    assert _python_triple_quote(lines, 1) == "Docstring here."


def test_python_triple_not_found() -> None:
    lines = ["def foo():", "    return 1"]
    assert _python_triple_quote(lines, 1) is None


def test_python_triple_empty_docstring() -> None:
    lines = ['def foo():', '    """"""', '    pass']
    # Empty triple-quote → None
    assert _python_triple_quote(lines, 1) is None


# ---------------------------------------------------------------------------
# _jsdoc_backward
# ---------------------------------------------------------------------------


def test_jsdoc_backward_basic() -> None:
    lines = [
        "/**",
        " * Return the answer.",
        " * @param x - input",
        " */",
        "function foo() {}",
    ]
    # end=4 (line index of function declaration)
    assert _jsdoc_backward(lines, 4) == "Return the answer."


def test_jsdoc_backward_skips_at_params() -> None:
    lines = [
        "/**",
        " * @param x - input",
        " */",
        "function foo() {}",
    ]
    # All content lines start with @, should return None
    assert _jsdoc_backward(lines, 3) is None


def test_jsdoc_backward_not_found() -> None:
    lines = ["const x = 1;", "function foo() {}"]
    assert _jsdoc_backward(lines, 1) is None


# ---------------------------------------------------------------------------
# _jsdoc_forward
# ---------------------------------------------------------------------------


def test_jsdoc_forward_basic() -> None:
    lines = [
        "/**",
        " * Module-level description.",
        " * @module mymod",
        " */",
        "import foo from './foo';",
    ]
    assert _jsdoc_forward(lines) == "Module-level description."


def test_jsdoc_forward_fallback_to_line_comments() -> None:
    lines = [
        "// This is a JS module.",
        "// Second line.",
        "import x from 'x';",
    ]
    assert _jsdoc_forward(lines) == "This is a JS module."


def test_jsdoc_forward_no_comment() -> None:
    lines = ["import x from 'x';", "export function foo() {}"]
    assert _jsdoc_forward(lines) is None


# ---------------------------------------------------------------------------
# _line_comment_backward
# ---------------------------------------------------------------------------


def test_line_comment_backward_go() -> None:
    lines = [
        "// ModuleDB wraps the database connection.",
        "// It is safe for concurrent use.",
        "type ModuleDB struct {",
    ]
    assert _line_comment_backward(lines, 2, "//") == "ModuleDB wraps the database connection."


def test_line_comment_backward_rust() -> None:
    lines = [
        "/// Returns the Fibonacci number.",
        "/// Panics if n > 40.",
        "pub fn fib(n: u64) -> u64 {",
    ]
    assert _line_comment_backward(lines, 2, "///") == "Returns the Fibonacci number."


def test_line_comment_backward_erlang() -> None:
    lines = [
        "%% @doc Handle incoming message.",
        "%% Returns ok.",
        "handle_call(Msg, _From, State) ->",
    ]
    assert _line_comment_backward(lines, 2, "%%") == "@doc Handle incoming message."


def test_line_comment_backward_stops_at_code() -> None:
    lines = [
        "const x = 1;",
        "// Only this line is a comment.",
        "function foo() {}",
    ]
    assert _line_comment_backward(lines, 2, "//") == "Only this line is a comment."


def test_line_comment_backward_not_found() -> None:
    lines = ["const x = 1;", "const y = 2;", "function foo() {}"]
    assert _line_comment_backward(lines, 2, "//") is None


# ---------------------------------------------------------------------------
# _line_comment_forward
# ---------------------------------------------------------------------------


def test_line_comment_forward_basic() -> None:
    lines = ["# This is a Ruby module.", "# Second line.", "class Foo"]
    assert _line_comment_forward(lines, "#") == "This is a Ruby module."


def test_line_comment_forward_stops_at_code() -> None:
    lines = ["class Foo", "# Not a module comment"]
    assert _line_comment_forward(lines, "#") is None


# ---------------------------------------------------------------------------
# _file_docstring_for_lang
# ---------------------------------------------------------------------------


def test_file_docstring_python() -> None:
    lines = ['"""Top-level module docstring."""', "import os"]
    assert _file_docstring_for_lang(lines, "python") == "Top-level module docstring."


def test_file_docstring_python_skips_shebang() -> None:
    lines = ["#!/usr/bin/env python3", '"""Module after shebang."""', "import os"]
    assert _file_docstring_for_lang(lines, "python") == "Module after shebang."


def test_file_docstring_python_skips_encoding() -> None:
    lines = ["# -*- coding: utf-8 -*-", '"""Module after encoding."""']
    assert _file_docstring_for_lang(lines, "python") == "Module after encoding."


def test_file_docstring_go() -> None:
    lines = ["// Package cache manages .codesense cache files.", "package cache"]
    assert _file_docstring_for_lang(lines, "go") == "Package cache manages .codesense cache files."


def test_file_docstring_rust_module_doc() -> None:
    lines = ["//! This crate provides the database layer.", "use std::path::Path;"]
    assert _file_docstring_for_lang(lines, "rust") == "This crate provides the database layer."


def test_file_docstring_erlang() -> None:
    lines = ["%% Manages connection pooling.", "-module(pool)."]
    assert _file_docstring_for_lang(lines, "erlang") == "Manages connection pooling."


def test_file_docstring_ruby() -> None:
    lines = ["# Handles HTTP requests.", "class Controller"]
    assert _file_docstring_for_lang(lines, "ruby") == "Handles HTTP requests."


def test_file_docstring_unknown_lang() -> None:
    lines = ["/* header */", "int main() {}"]
    assert _file_docstring_for_lang(lines, "cobol") is None


# ---------------------------------------------------------------------------
# extract_file_docstring (file I/O)
# ---------------------------------------------------------------------------


def test_extract_file_docstring_reads_real_file(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text('"""My module docstring."""\nimport os\n', encoding="utf-8")
    assert extract_file_docstring(src, "python") == "My module docstring."


def test_extract_file_docstring_missing_file(tmp_path: Path) -> None:
    assert extract_file_docstring(tmp_path / "nonexistent.py", "python") is None


def test_extract_file_docstring_no_docstring(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("import os\n\ndef foo(): pass\n", encoding="utf-8")
    assert extract_file_docstring(src, "python") is None


def test_extract_file_docstring_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_EXTRACT_DOCSTRINGS", "false")
    src = tmp_path / "mod.py"
    src.write_text('"""Has docstring."""\n', encoding="utf-8")
    assert extract_file_docstring(src, "python") is None


def test_extract_file_docstring_truncates_long(tmp_path: Path) -> None:
    long_doc = "A" * 300
    src = tmp_path / "mod.py"
    src.write_text(f'"""{long_doc}"""\n', encoding="utf-8")
    result = extract_file_docstring(src, "python")
    assert result is not None
    assert len(result) <= 200


# ---------------------------------------------------------------------------
# extract_symbol_docstrings (file I/O)
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    name: str,
    kind: str = "function",
    file_path: str = "mod.py",
    language: str = "python",
    start_line: int = 1,
) -> MagicMock:
    n = MagicMock()
    n.id = node_id
    n.name = name
    n.kind = kind
    n.file_path = file_path
    n.language = language
    n.start_line = start_line
    return n


def test_extract_symbol_docstrings_python(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text(
        'def foo():\n    """Return the answer."""\n    return 42\n',
        encoding="utf-8",
    )
    node = _make_node("n1", "foo", start_line=1, file_path=str(src))
    result = extract_symbol_docstrings(src, "python", [node])
    assert result == {"n1": "Return the answer."}


def test_extract_symbol_docstrings_no_docstring(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("def foo():\n    return 42\n", encoding="utf-8")
    node = _make_node("n1", "foo", start_line=1, file_path=str(src))
    result = extract_symbol_docstrings(src, "python", [node])
    assert result == {}


def test_extract_symbol_docstrings_multiple_nodes(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text(
        'def foo():\n    """Foo does something."""\n    pass\n\n'
        'def bar():\n    """Bar does something else."""\n    pass\n',
        encoding="utf-8",
    )
    nodes = [
        _make_node("n-foo", "foo", start_line=1, file_path=str(src)),
        _make_node("n-bar", "bar", start_line=5, file_path=str(src)),
    ]
    result = extract_symbol_docstrings(src, "python", nodes)
    assert result["n-foo"] == "Foo does something."
    assert result["n-bar"] == "Bar does something else."


def test_extract_symbol_docstrings_missing_file(tmp_path: Path) -> None:
    node = _make_node("n1", "foo", file_path=str(tmp_path / "missing.py"))
    assert extract_symbol_docstrings(tmp_path / "missing.py", "python", [node]) == {}


def test_extract_symbol_docstrings_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_EXTRACT_DOCSTRINGS", "false")
    src = tmp_path / "mod.py"
    src.write_text('def foo():\n    """Doc."""\n    pass\n', encoding="utf-8")
    node = _make_node("n1", "foo", start_line=1, file_path=str(src))
    assert extract_symbol_docstrings(src, "python", [node]) == {}


def test_extract_symbol_docstrings_empty_nodes_list(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("x = 1\n", encoding="utf-8")
    assert extract_symbol_docstrings(src, "python", []) == {}


def test_extract_symbol_docstrings_typescript(tmp_path: Path) -> None:
    src = tmp_path / "mod.ts"
    src.write_text(
        "/**\n * Compute checksum.\n * @param data input\n */\n"
        "function checksum(data: string): number {\n  return 0;\n}\n",
        encoding="utf-8",
    )
    node = _make_node("n1", "checksum", language="typescript", start_line=5, file_path=str(src))
    result = extract_symbol_docstrings(src, "typescript", [node])
    assert result == {"n1": "Compute checksum."}


def test_extract_symbol_docstrings_go(tmp_path: Path) -> None:
    src = tmp_path / "mod.go"
    src.write_text(
        "package main\n\n// Compute returns the result.\nfunc Compute() int {\n  return 0\n}\n",
        encoding="utf-8",
    )
    node = _make_node("n1", "Compute", language="go", start_line=4, file_path=str(src))
    result = extract_symbol_docstrings(src, "go", [node])
    assert result == {"n1": "Compute returns the result."}
