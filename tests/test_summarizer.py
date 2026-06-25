"""Tests for codesense_v1.summarizer."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codesense_v1 import summarizer
from codesense_v1.errors import InvalidArgumentError

_SUM = "codesense_v1.summarizer.summarizer"
_CG_DB = f"{_SUM}.CodeGraphDB"

# ---- helpers ----------------------------------------------------------------

_VALID_TEXT_RESPONSE = "缓存层|管理缓存文件|src/cache"
_MULTI_MODULE_RESPONSE = (
    "缓存层|管理缓存文件|src/cache\n"
    "数据层|封装数据库操作|src/data\n"
)


def _make_db_mock(files: list[str] | None = None) -> MagicMock:
    """Return a mock CodeGraphDB context manager."""
    db = MagicMock()
    file_rows = []
    for fp in (files or []):
        row = MagicMock()
        row.path = fp
        row.language = "python"
        file_rows.append(row)
    db.iter_files.return_value = file_rows
    db.iter_nodes.return_value = []
    db.iter_edges.return_value = []
    db.stats.return_value = {"files": 0, "nodes": 0, "edges": 0}
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _setup_project(tmp_path: Path, with_db: bool = True) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    if with_db:
        db_dir = project_root / ".codegraph"
        db_dir.mkdir()
        (db_dir / "codegraph.db").write_bytes(b"fake")
    return project_root


def _write_valid_index(project_root: Path, current_hash: str) -> None:
    """Write a valid modules_index.json + meta.json to .codesense/."""
    from codesense_v1 import cache as _cache

    modules = [
        {
            "name": "缓存层",
            "description": "管理缓存文件",
            "directories": ["src/cache"],
            "files": ["src/cache/cache.py"],
        }
    ]
    cs_dir = project_root / ".codesense"
    _cache.write_modules_index(cs_dir, modules, current_hash)  # type: ignore[arg-type]


# ---- _parse_modules_text ----------------------------------------------------


def test_parse_modules_text_basic() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("缓存层|管理缓存文件|src/cache")
    assert len(result) == 1
    assert result[0]["name"] == "缓存层"
    assert result[0]["description"] == "管理缓存文件"
    assert result[0]["directories"] == ["src/cache"]


def test_parse_modules_text_multiple_dirs() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("数据层|封装DB操作|src/data,src/models")
    assert result[0]["directories"] == ["src/data", "src/models"]


def test_parse_modules_text_skips_no_pipe_lines() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("这是标题行\n缓存层|管理缓存|src/cache\n另一行没管道")
    assert len(result) == 1
    assert result[0]["name"] == "缓存层"


def test_parse_modules_text_deduplicates_names() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("AA|desc|src/a\naa|desc2|src/b")
    assert len(result) == 1
    assert result[0]["name"] == "AA"


def test_parse_modules_text_allows_parent_child_dirs() -> None:
    """Parent dir and child dir can both be registered; no overlap blocking."""
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("AA|desc|src\nBB|desc|src/sub")
    assert len(result) == 2
    assert result[0]["name"] == "AA"
    assert result[1]["name"] == "BB"


def test_parse_modules_text_blocks_exact_duplicate_dirs() -> None:
    """Exact same directory should only be claimed once."""
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("AA|desc|src/cache\nBB|desc|src/cache")
    assert len(result) == 1
    assert result[0]["name"] == "AA"


def test_parse_modules_text_empty_returns_empty() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    assert _parse_modules_text("") == []
    assert _parse_modules_text("no pipes at all\nstill nothing") == []


def test_parse_modules_text_strips_backticks_from_dirs() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("Cache|desc|`src/cache`")
    assert result[0]["directories"] == ["src/cache"]


def test_parse_modules_text_multi_module(tmp_path: Any) -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text(_MULTI_MODULE_RESPONSE)
    assert len(result) == 2
    names = [r["name"] for r in result]
    assert "缓存层" in names
    assert "数据层" in names


# ---- _parse_modules_text validation (valid_dirs) ----------------------------


def test_parse_modules_text_filters_invalid_dirs() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    valid = {"src/a", "src/b"}
    result = _parse_modules_text("MM|desc|src/a,src/typo_xyz", valid_dirs=valid)
    assert len(result) == 1
    assert result[0]["directories"] == ["src/a"]


def test_parse_modules_text_drops_row_when_all_dirs_invalid() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    valid = {"src/a"}
    result = _parse_modules_text("Junk|desc|completely_wrong_xyz", valid_dirs=valid)
    assert result == []


def test_parse_modules_text_fuzzy_corrects_typo() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    valid = {"src/codesense_v1/errors"}
    # 缺少斜杠的常见 LLM 拼写错
    result = _parse_modules_text(
        "Errors|desc|src/codesense_v1/erorrs", valid_dirs=valid
    )
    assert len(result) == 1
    assert result[0]["directories"] == ["src/codesense_v1/errors"]


def test_parse_modules_text_dedups_description() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("工具层|add、explore、add、list|src/tools")
    assert result[0]["description"] == "add、explore、list"


def test_parse_modules_text_truncates_long_description() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text, _DESC_MAX_LEN

    long_desc = "x" * 200
    result = _parse_modules_text(f"MM|{long_desc}|src/a")
    assert len(result[0]["description"]) <= _DESC_MAX_LEN


def test_parse_modules_text_rejects_too_short_name() -> None:
    """单字模块名（LLM 截断产物，如'层'）应被丢弃。"""
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("层|desc|src/a\n工具层|desc|src/b")
    names = [m["name"] for m in result]
    assert "层" not in names
    assert "工具层" in names


def test_parse_modules_text_rejects_too_long_name() -> None:
    """过长模块名（LLM 把描述串到名称列）应被丢弃。"""
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    long_name = "资源" * 20  # 40 chars
    result = _parse_modules_text(f"{long_name}|desc|src/a")
    assert result == []


# ---- _leaf_dirs_from_files --------------------------------------------------


def test_leaf_dirs_from_files_returns_only_leaves() -> None:
    from codesense_v1.summarizer.summarizer import _leaf_dirs_from_files

    files = [
        "src/codesense_v1/__init__.py",
        "src/codesense_v1/cache/cache.py",
        "src/codesense_v1/schemas/schemas.py",
    ]
    result = _leaf_dirs_from_files(files)
    # src/codesense_v1 是 cache/schemas 的父目录，应被剔除
    assert result == {"src/codesense_v1/cache", "src/codesense_v1/schemas"}


def test_leaf_dirs_from_files_handles_windows_separator() -> None:
    from codesense_v1.summarizer.summarizer import _leaf_dirs_from_files

    files = ["src\\codesense_v1\\schemas\\schemas.py"]
    result = _leaf_dirs_from_files(files)
    assert result == {"src/codesense_v1/schemas"}


def test_leaf_dirs_from_files_ignores_top_level_files() -> None:
    from codesense_v1.summarizer.summarizer import _leaf_dirs_from_files

    assert _leaf_dirs_from_files(["README.md"]) == set()


# ---- include-roots filter (CODESENSE_INCLUDE_DIRS) --------------------------


def test_get_include_roots_default(monkeypatch: Any) -> None:
    from codesense_v1.summarizer.summarizer import _get_include_roots

    monkeypatch.delenv("CODESENSE_INCLUDE_DIRS", raising=False)
    assert _get_include_roots() is None


def test_get_include_roots_from_env(monkeypatch: Any) -> None:
    from codesense_v1.summarizer.summarizer import _get_include_roots

    monkeypatch.setenv("CODESENSE_INCLUDE_DIRS", "src, scripts , app/")
    assert _get_include_roots() == ("src", "scripts", "app")


def test_get_include_roots_empty_env_falls_back(monkeypatch: Any) -> None:
    from codesense_v1.summarizer.summarizer import _get_include_roots

    monkeypatch.setenv("CODESENSE_INCLUDE_DIRS", "   ,  ")
    assert _get_include_roots() is None


def test_is_under_roots_matches_root_and_nested() -> None:
    from codesense_v1.summarizer.summarizer import _is_under_roots

    roots = ("src", "scripts")
    assert _is_under_roots("src", roots)
    assert _is_under_roots("src/foo", roots)
    assert _is_under_roots("src/foo/bar", roots)
    assert _is_under_roots("scripts", roots)
    assert not _is_under_roots("tests", roots)
    assert not _is_under_roots("docs/api", roots)
    # 前缀错配陷阱：src_extra 不应匹配 src
    assert not _is_under_roots("src_extra", roots)


def test_filter_dir_deps_drops_outside_edges() -> None:
    from codesense_v1.summarizer.summarizer import _filter_dir_deps

    deps = {
        "src/a": {"imports": ["src/b", "tests/x"]},
        "tests/x": {"imports": ["src/a"]},
        "src/b": {"imports": ["src/a"]},
    }
    result = _filter_dir_deps(deps, ("src",))
    assert "tests/x" not in result
    assert result["src/a"]["imports"] == ["src/b"]
    assert result["src/b"]["imports"] == ["src/a"]


def test_filter_dir_deps_removes_empty_buckets() -> None:
    """所有目标都被过滤掉的源目录应整体消失。"""
    from codesense_v1.summarizer.summarizer import _filter_dir_deps

    deps = {"src/a": {"imports": ["tests/x"]}}
    assert _filter_dir_deps(deps, ("src",)) == {}


# ---- _build_project_map_prompt hints (anti "all-in-one" hallucination) ------


def test_build_project_map_prompt_forbids_single_module() -> None:
    """Prompt 必须明确禁止把所有目录归到单一模块（防一锅烩）。"""
    from codesense_v1.summarizer.summarizer import _build_project_map_prompt

    dir_syms = {f"src/d{i}": [] for i in range(9)}
    prompt = _build_project_map_prompt({}, dir_syms, roots=("src",))
    assert "禁止把所有目录归到单一模块" in prompt
    assert "至少 2 个模块" in prompt


def test_build_project_map_prompt_marks_roots_in_context() -> None:
    """Prompt 应明示目录来源（白名单根），并强调每目录独立。"""
    from codesense_v1.summarizer.summarizer import _build_project_map_prompt

    prompt = _build_project_map_prompt({}, {"src/a": []}, roots=("src", "scripts"))
    assert "`src`" in prompt and "`scripts`" in prompt
    assert "每个目录代表一个独立模块" in prompt


def test_build_project_map_prompt_default_roots() -> None:
    """不传 roots 时默认使用 src（保持向后兼容）。"""
    from codesense_v1.summarizer.summarizer import _build_project_map_prompt

    prompt = _build_project_map_prompt({}, {"src/a": []})
    assert "`src`" in prompt


# ---- dummy to satisfy Any annotation ---------------------------------------


def test_unused_any_import(tmp_path: Any) -> None:
    assert tmp_path is not None
