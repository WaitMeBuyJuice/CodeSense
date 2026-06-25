"""Tests for codesense_v1.tools.explore_module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codesense_v1 import registry

# Import tools package to trigger registration
from codesense_v1 import tools as _tools  # noqa: F401

_EXPLORE_CG_DB = "codesense_v1.tools.explore_module.CodeGraphDB"

_VALID_INDEX = {
    "generated_at": "2026-06-17T00:00:00+00:00",
    "modules": [
        {
            "name": "缓存层",
            "description": "管理缓存",
            "directories": ["src/cache"],
            "files": ["src/cache/cache.py"],
        }
    ],
}


def _make_db_mock() -> MagicMock:
    db = MagicMock()
    db.iter_files.return_value = []
    db.iter_nodes.return_value = []
    db.iter_edges.return_value = []
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _setup_project_with_index(tmp_path: Path) -> Path:
    """Create a minimal project with DB + valid modules_index.json."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    db_dir = project_root / ".codegraph"
    db_dir.mkdir()
    (db_dir / "codegraph.db").write_bytes(b"fake")

    cs_dir = project_root / ".codesense"
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    h = _cache.db_hash(project_root / DB_RELATIVE_PATH)
    _cache.write_modules_index(cs_dir, _VALID_INDEX["modules"], h)  # type: ignore[arg-type]
    return project_root


def _setup_cached_module(project_root: Path, content: str = "# 缓存层摘要") -> None:
    """Pre-populate cache with a module .md and matching hash."""
    from codesense_v1 import cache as _cache
    from codesense_v1.summarizer.summarizer import _compute_module_hash

    cs_dir = project_root / ".codesense"
    mkey = _cache.safe_key("缓存层")
    db_ctx = _make_db_mock()
    entry = {"name": "缓存层", "files": ["src/cache/cache.py"], "directories": ["src/cache"]}
    module_hash = _compute_module_hash(entry, db_ctx.__enter__())

    db_hash = _cache.db_hash(project_root / ".codegraph" / "codegraph.db")
    _cache.write_module(cs_dir, mkey, "缓存层", content, db_hash, module_hash)


# ---- parameter validation ---------------------------------------------------


async def test_explore_module_empty_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", "/some/path")
    result = await registry.dispatch("explore_module", {"module_name": ""})
    assert result.isError
    assert "不能为空" in str(result.content)


async def test_explore_module_no_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODESENSE_PROJECT_ROOT", raising=False)
    result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert result.isError
    assert "CODESENSE_PROJECT_ROOT" in str(result.content)


async def test_explore_module_db_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert not result.isError
    assert "数据库不存在" in str(result.content)
    assert "codegraph init" in str(result.content)


async def test_explore_module_index_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No modules_index.json → returns guide asking to run project_map first."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    db_dir = project_root / ".codegraph"
    db_dir.mkdir()
    (db_dir / "codegraph.db").write_bytes(b"fake")
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert not result.isError
    assert "project_map" in str(result.content)


async def test_explore_module_name_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module name absent from index → error lists available names."""
    project_root = _setup_project_with_index(tmp_path)
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    db_ctx = _make_db_mock()
    with patch(_EXPLORE_CG_DB, return_value=db_ctx):
        result = await registry.dispatch("explore_module", {"module_name": "不存在"})
    assert result.isError
    assert "缓存层" in str(result.content)


async def test_explore_module_cache_miss_returns_guide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache miss → returns step-by-step guide without calling LLM."""
    project_root = _setup_project_with_index(tmp_path)
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    db_ctx = _make_db_mock()
    with patch(_EXPLORE_CG_DB, return_value=db_ctx):
        result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert not result.isError
    assert "get_module_prompt" in str(result.content)
    assert "save_module_summary" in str(result.content)


async def test_explore_module_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache hit with matching hash → returns cached content directly."""
    project_root = _setup_project_with_index(tmp_path)
    _setup_cached_module(project_root, "# Module summary")
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    db_ctx = _make_db_mock()
    with patch(_EXPLORE_CG_DB, return_value=db_ctx):
        result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert not result.isError
    assert "Module summary" in str(result.content)


async def test_explore_module_name_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module name lookup is case/trim insensitive end-to-end."""
    project_root = _setup_project_with_index(tmp_path)
    _setup_cached_module(project_root, "# OK")
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    db_ctx = _make_db_mock()
    with patch(_EXPLORE_CG_DB, return_value=db_ctx):
        result = await registry.dispatch("explore_module", {"module_name": " 缓存层 "})
    assert not result.isError
    assert "OK" in str(result.content)


def test_explore_module_registered() -> None:
    names = [t.name for t in registry.list_tools()]
    assert "explore_module" in names
