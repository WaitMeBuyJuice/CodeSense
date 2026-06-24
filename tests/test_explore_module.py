"""Tests for codesense_v1.tools.explore_module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codesense_v1 import registry

# Import tools package to trigger registration
from codesense_v1 import tools as _tools  # noqa: F401
from codesense_v1.errors import LLMError

_SUM = "codesense_v1.summarizer.summarizer"

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
    db.stats.return_value = {"files": 0, "nodes": 0, "edges": 0}
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
    _cache.write_modules_index(
        cs_dir,
        _VALID_INDEX["modules"],  # type: ignore[arg-type]
        h,
    )
    return project_root


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
    # No .codegraph/codegraph.db → FileNotFoundError → wrapped
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert not result.isError
    assert "数据库不存在" in str(result.content)
    assert "codegraph init" in str(result.content)


async def test_explore_module_index_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No modules_index.json → error message asks to read project_map."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    db_dir = project_root / ".codegraph"
    db_dir.mkdir()
    (db_dir / "codegraph.db").write_bytes(b"fake")
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    result = await registry.dispatch("explore_module", {"module_name": "缓存层"})
    assert result.isError
    assert "project_map" in str(result.content)


async def test_explore_module_name_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module name absent from index → error lists available names."""
    project_root = _setup_project_with_index(tmp_path)
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))
    result = await registry.dispatch("explore_module", {"module_name": "不存在"})
    assert result.isError
    assert "缓存层" in str(result.content)


async def test_explore_module_llm_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _setup_project_with_index(tmp_path)
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))

    db_ctx = _make_db_mock()
    with (
        patch(f"{_SUM}.CodeGraphDB", return_value=db_ctx),
        patch(f"{_SUM}.llm.call_llm", new_callable=AsyncMock, side_effect=LLMError("api down")),
    ):
        result = await registry.dispatch("explore_module", {"module_name": "缓存层"})

    assert not result.isError
    assert "api down" in str(result.content)
    assert "LLM" in str(result.content)


async def test_explore_module_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _setup_project_with_index(tmp_path)
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))

    with patch(
        "codesense_v1.summarizer.module_summary",
        new_callable=AsyncMock,
        return_value="# Module summary",
    ):
        result = await registry.dispatch("explore_module", {"module_name": "缓存层"})

    assert not result.isError
    assert "Module summary" in str(result.content)


async def test_explore_module_name_case_insensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module name lookup is case/trim insensitive end-to-end."""
    project_root = _setup_project_with_index(tmp_path)
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", str(project_root))

    db_ctx = _make_db_mock()
    with (
        patch(f"{_SUM}.CodeGraphDB", return_value=db_ctx),
        patch(f"{_SUM}.llm.call_llm", new_callable=AsyncMock, return_value="# OK"),
    ):
        result = await registry.dispatch("explore_module", {"module_name": " 缓存层 "})

    assert not result.isError


def test_explore_module_registered() -> None:
    names = [t.name for t in registry.list_tools()]
    assert "explore_module" in names
