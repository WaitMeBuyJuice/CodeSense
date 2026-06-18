"""Tests for codesense_v1.summarizer."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codesense_v1 import summarizer
from codesense_v1.errors import InvalidArgumentError, LLMError

_SUM = "codesense_v1.summarizer.summarizer"
_LLM_CALL = f"{_SUM}.llm.call_llm"
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


# ---- project_map_summary: cache hit -----------------------------------------


async def test_project_map_cache_hit(tmp_path: Path) -> None:
    """Cache valid + content present → no LLM call."""
    project_root = _setup_project(tmp_path)
    cs_dir = project_root / ".codesense"

    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    db_path = project_root / DB_RELATIVE_PATH
    h = _cache.db_hash(db_path)
    _cache.write_project_map(cs_dir, "# cached map", h)

    with patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm:
        result = await summarizer.project_map_summary(project_root)

    assert result == "# cached map"
    mock_llm.assert_not_called()


# ---- project_map_summary: cache miss ----------------------------------------


async def test_project_map_cache_miss_calls_llm(tmp_path: Path) -> None:
    """Cache invalid → call LLM (text), write modules_index + project_map."""
    project_root = _setup_project(tmp_path)

    db_ctx = _make_db_mock()
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = _VALID_TEXT_RESPONSE
        result = await summarizer.project_map_summary(project_root)

    mock_llm.assert_called_once()
    assert "项目架构概览" in result
    assert "缓存层" in result


async def test_project_map_writes_modules_index(tmp_path: Path) -> None:
    """After cache miss, modules_index.json should be written."""
    project_root = _setup_project(tmp_path)

    db_ctx = _make_db_mock(files=["src/cache/cache.py"])
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = _VALID_TEXT_RESPONSE
        await summarizer.project_map_summary(project_root)

    from codesense_v1 import cache as _cache

    cs_dir = project_root / ".codesense"
    index = _cache.read_modules_index(cs_dir)
    assert index is not None
    modules = index["modules"]
    assert isinstance(modules, list)
    assert modules[0]["name"] == "缓存层"  # type: ignore[index]


async def test_project_map_parse_retry_on_empty(tmp_path: Path) -> None:
    """First LLM response has no valid lines → retry → second succeeds."""
    project_root = _setup_project(tmp_path)

    db_ctx = _make_db_mock()
    responses = ["这不是合法格式", _VALID_TEXT_RESPONSE]
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.side_effect = responses
        result = await summarizer.project_map_summary(project_root)

    assert mock_llm.call_count == 2
    assert "缓存层" in result


async def test_project_map_both_empty_raises(tmp_path: Path) -> None:
    """Both LLM responses parse to empty → LLMError raised."""
    project_root = _setup_project(tmp_path)

    db_ctx = _make_db_mock()
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.side_effect = ["no pipes here", "still nothing"]
        with pytest.raises(LLMError, match="有效的模块列表"):
            await summarizer.project_map_summary(project_root)


async def test_project_map_db_not_found(tmp_path: Path) -> None:
    """Missing CodeGraph DB → FileNotFoundError propagates."""
    project_root = _setup_project(tmp_path, with_db=False)

    with pytest.raises(FileNotFoundError):
        await summarizer.project_map_summary(project_root)


# ---- module_summary: index missing ------------------------------------------


async def test_module_summary_index_missing_raises(tmp_path: Path) -> None:
    """No modules_index.json → InvalidArgumentError asking to call project_map."""
    project_root = _setup_project(tmp_path)

    with pytest.raises(InvalidArgumentError, match="codesense://project_map"):
        await summarizer.module_summary(project_root, "缓存层")


# ---- module_summary: module name not found ----------------------------------


async def test_module_summary_name_not_found_lists_available(tmp_path: Path) -> None:
    """Module name absent from index → error message lists available names."""
    project_root = _setup_project(tmp_path)
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    h = _cache.db_hash(project_root / DB_RELATIVE_PATH)
    _write_valid_index(project_root, h)

    with pytest.raises(InvalidArgumentError, match="缓存层"):
        await summarizer.module_summary(project_root, "不存在的模块")


# ---- module_summary: case/trim normalisation --------------------------------


async def test_module_summary_name_case_insensitive(tmp_path: Path) -> None:
    """Module lookup is case-insensitive and trim-tolerant."""
    project_root = _setup_project(tmp_path)
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    h = _cache.db_hash(project_root / DB_RELATIVE_PATH)
    _write_valid_index(project_root, h)

    db_ctx = _make_db_mock()
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = "# module content"
        result = await summarizer.module_summary(project_root, " 缓存层 ")

    assert result == "# module content"


# ---- module_summary: cache hit ----------------------------------------------


async def test_module_summary_cache_hit(tmp_path: Path) -> None:
    """Cache valid + module cache present → no LLM call."""
    project_root = _setup_project(tmp_path)
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    db_path = project_root / DB_RELATIVE_PATH
    h = _cache.db_hash(db_path)
    _write_valid_index(project_root, h)

    cs_dir = project_root / ".codesense"
    mkey = _cache.safe_key("缓存层")
    _cache.write_module(cs_dir, mkey, "缓存层", "# cached module", h)

    with patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm:
        result = await summarizer.module_summary(project_root, "缓存层")

    assert result == "# cached module"
    mock_llm.assert_not_called()


# ---- module_summary: cache miss → LLM call ----------------------------------


async def test_module_summary_cache_miss_calls_llm(tmp_path: Path) -> None:
    """Cache invalid → call LLM, write module cache, return result."""
    project_root = _setup_project(tmp_path)
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    h = _cache.db_hash(project_root / DB_RELATIVE_PATH)
    _write_valid_index(project_root, h)

    db_ctx = _make_db_mock()
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = "# fresh module"
        result = await summarizer.module_summary(project_root, "缓存层")

    assert result == "# fresh module"
    mock_llm.assert_called_once()


async def test_module_summary_writes_cache(tmp_path: Path) -> None:
    """After cache miss, module cache should be written."""
    project_root = _setup_project(tmp_path)
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    h = _cache.db_hash(project_root / DB_RELATIVE_PATH)
    _write_valid_index(project_root, h)

    db_ctx = _make_db_mock()
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = "summary text"
        await summarizer.module_summary(project_root, "缓存层")

    cs_dir = project_root / ".codesense"
    mkey = _cache.safe_key("缓存层")
    assert _cache.read_module(cs_dir, mkey) == "summary text"


async def test_module_summary_llm_error_propagates(tmp_path: Path) -> None:
    """LLMError from call_llm propagates out of module_summary."""
    project_root = _setup_project(tmp_path)
    from codesense_v1 import cache as _cache
    from codesense_v1.data.db import DB_RELATIVE_PATH

    h = _cache.db_hash(project_root / DB_RELATIVE_PATH)
    _write_valid_index(project_root, h)

    db_ctx = _make_db_mock()
    with (
        patch(_CG_DB, return_value=db_ctx),
        patch(_LLM_CALL, new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.side_effect = LLMError("fail")
        with pytest.raises(LLMError, match="fail"):
            await summarizer.module_summary(project_root, "缓存层")


async def test_module_summary_db_not_found(tmp_path: Path) -> None:
    """Missing DB → FileNotFoundError propagates."""
    project_root = _setup_project(tmp_path, with_db=False)

    with pytest.raises(FileNotFoundError):
        await summarizer.module_summary(project_root, "缓存层")


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


def test_parse_modules_text_skips_overlapping_dirs() -> None:
    from codesense_v1.summarizer.summarizer import _parse_modules_text

    result = _parse_modules_text("AA|desc|src\nBB|desc|src/sub")
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


# ---- _call_llm_for_modules coverage repair ----------------------------------


@pytest.mark.asyncio
async def test_call_llm_for_modules_fills_missing_dirs() -> None:
    from codesense_v1.summarizer.summarizer import _call_llm_for_modules

    valid = {"src/a", "src/b", "src/schemas"}
    # 首轮漏 src/schemas；补齐轮把它归到新模块"Schemas"
    responses = iter(
        [
            "ModA|desc|src/a\nModB|desc|src/b",
            "Schemas|描述|src/schemas",
        ]
    )

    async def fake_call(_prompt: str) -> str:
        return next(responses)

    with patch(_LLM_CALL, side_effect=fake_call):
        result = await _call_llm_for_modules("init prompt", valid_dirs=valid)

    covered = {d for m in result for d in m["directories"]}
    assert covered == valid


@pytest.mark.asyncio
async def test_call_llm_for_modules_appends_fallback_when_repair_fails() -> None:
    from codesense_v1.summarizer.summarizer import (
        _FALLBACK_MODULE_NAME,
        _call_llm_for_modules,
    )

    valid = {"src/a", "src/orphan"}
    responses = iter(
        [
            "ModA|desc|src/a",
            "",  # 补齐轮 LLM 不配合，仍漏 src/orphan
        ]
    )

    async def fake_call(_prompt: str) -> str:
        return next(responses)

    with patch(_LLM_CALL, side_effect=fake_call):
        result = await _call_llm_for_modules("init prompt", valid_dirs=valid)

    names = [m["name"] for m in result]
    assert _FALLBACK_MODULE_NAME in names
    fallback = next(m for m in result if m["name"] == _FALLBACK_MODULE_NAME)
    assert "src/orphan" in fallback["directories"]


@pytest.mark.asyncio
async def test_call_llm_for_modules_repair_extends_existing_module() -> None:
    """补齐轮若复用已有模块名，新目录应合并进该模块，不创建重复模块。"""
    from codesense_v1.summarizer.summarizer import _call_llm_for_modules

    valid = {"src/a", "src/extra"}
    responses = iter(
        [
            "ModA|desc|src/a",
            "ModA|desc|src/extra",
        ]
    )

    async def fake_call(_prompt: str) -> str:
        return next(responses)

    with patch(_LLM_CALL, side_effect=fake_call):
        result = await _call_llm_for_modules("init prompt", valid_dirs=valid)

    mod_a = [m for m in result if m["name"] == "ModA"]
    assert len(mod_a) == 1
    assert set(mod_a[0]["directories"]) == {"src/a", "src/extra"}


# ---- dummy to satisfy Any annotation ---------------------------------------


def test_unused_any_import(tmp_path: Any) -> None:
    assert tmp_path is not None
