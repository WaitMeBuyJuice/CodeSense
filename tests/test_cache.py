"""Tests for codesense_v1.cache."""

import json
from pathlib import Path

import pytest

from codesense_v1 import cache

# ---- helpers ----------------------------------------------------------------


def _make_db(tmp_path: Path, content: bytes = b"fake-db-content") -> Path:
    db = tmp_path / "codegraph.db"
    db.write_bytes(content)
    return db


def _cs_dir(tmp_path: Path) -> Path:
    return tmp_path / ".codesense"


# ---- db_hash ----------------------------------------------------------------


def test_db_hash_returns_hex_string(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    result = cache.db_hash(db)
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_db_hash_deterministic(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    assert cache.db_hash(db) == cache.db_hash(db)


def test_db_hash_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cache.db_hash(tmp_path / "missing.db")


# ---- is_cache_valid ---------------------------------------------------------


def test_is_cache_valid_true(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    h = "abc123"
    cache.write_project_map(cs, "content", h)
    assert cache.is_cache_valid(cs, h) is True


def test_is_cache_valid_wrong_hash(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_project_map(cs, "content", "hash-a")
    assert cache.is_cache_valid(cs, "hash-b") is False


def test_is_cache_valid_no_meta(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    assert cache.is_cache_valid(cs, "any") is False


# ---- project_map ------------------------------------------------------------


def test_read_write_project_map(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_project_map(cs, "# Hello", "hash1")
    assert cache.read_project_map(cs) == "# Hello"


def test_write_project_map_creates_dir(tmp_path: Path) -> None:
    cs = tmp_path / "does" / "not" / "exist"
    cache.write_project_map(cs, "x", "h")
    assert cs.exists()


def test_write_project_map_updates_meta(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_project_map(cs, "x", "hash42")
    meta = json.loads((cs / "meta.json").read_text(encoding="utf-8"))
    assert meta["db_hash"] == "hash42"
    assert "generated_at" in meta


def test_read_project_map_none_if_missing(tmp_path: Path) -> None:
    assert cache.read_project_map(_cs_dir(tmp_path)) is None


# ---- modules_index ----------------------------------------------------------


def test_read_modules_index_none_if_missing(tmp_path: Path) -> None:
    assert cache.read_modules_index(_cs_dir(tmp_path)) is None


def test_write_read_modules_index(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    modules = [
        {"name": "缓存层", "description": "管理缓存", "directories": ["src/cache"], "files": []}
    ]
    cache.write_modules_index(cs, modules, "h1")  # type: ignore[arg-type]
    result = cache.read_modules_index(cs)
    assert result is not None
    assert "modules" in result
    assert "generated_at" in result
    loaded_modules = result["modules"]
    assert isinstance(loaded_modules, list)
    assert loaded_modules[0]["name"] == "缓存层"  # type: ignore[index]


def test_write_modules_index_updates_meta(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_modules_index(cs, [], "hash-idx")  # type: ignore[arg-type]
    meta = json.loads((cs / "meta.json").read_text(encoding="utf-8"))
    assert meta["db_hash"] == "hash-idx"


def test_write_modules_index_clears_module_sub_cache(tmp_path: Path) -> None:
    """D7: write_modules_index must clear modules/ sub-cache."""
    cs = _cs_dir(tmp_path)
    # Write a module cache entry first
    cache.write_module(cs, "abc123", "旧模块", "old summary", "h0")
    assert cache.read_module(cs, "abc123") == "old summary"
    # Now write new modules_index → should wipe modules/
    cache.write_modules_index(cs, [], "h1")  # type: ignore[arg-type]
    assert cache.read_module(cs, "abc123") is None


def test_write_modules_index_creates_dir(tmp_path: Path) -> None:
    cs = tmp_path / "deep" / "path"
    cache.write_modules_index(cs, [], "h")  # type: ignore[arg-type]
    assert cs.exists()


# ---- module -----------------------------------------------------------------


def test_read_module_none_if_missing(tmp_path: Path) -> None:
    assert cache.read_module(_cs_dir(tmp_path), "src_auth") is None


def test_read_write_module(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_module(cs, "src_auth", "Auth 模块", "# Auth module", "hashX")
    assert cache.read_module(cs, "src_auth") == "# Auth module"


def test_write_module_updates_meta(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_module(cs, "src_auth", "Auth 模块", "summary", "hash99")
    meta = json.loads((cs / "meta.json").read_text(encoding="utf-8"))
    assert meta["db_hash"] == "hash99"


def test_write_module_json_structure(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_module(cs, "src_auth", "Auth 模块", "my summary", "h1")
    content = (cs / "modules" / "src_auth.md").read_text(encoding="utf-8")
    assert content == "my summary"


# ---- invalidate -------------------------------------------------------------


def test_invalidate_clears_all(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_project_map(cs, "pm", "h1")
    cache.write_modules_index(cs, [{"name": "X", "directories": []}], "h1")  # type: ignore[list-item]
    cache.write_module(cs, "src_auth", "Auth", "mod", "h1")

    cache.invalidate(cs)

    assert cache.read_project_map(cs) is None
    assert cache.read_modules_index(cs) is None
    assert cache.read_module(cs, "src_auth") is None
    assert cache.is_cache_valid(cs, "h1") is False


def test_invalidate_clears_modules_index(tmp_path: Path) -> None:
    cs = _cs_dir(tmp_path)
    cache.write_modules_index(cs, [], "h1")  # type: ignore[arg-type]
    cache.invalidate(cs)
    assert cache.read_modules_index(cs) is None


def test_invalidate_noop_on_empty(tmp_path: Path) -> None:
    cache.invalidate(_cs_dir(tmp_path))  # should not raise


# ---- module_key -------------------------------------------------------------


def test_module_key_slash(tmp_path: Path) -> None:
    assert cache.module_key("src/auth") == "src_auth"


def test_module_key_backslash(tmp_path: Path) -> None:
    assert cache.module_key("src\\auth") == "src_auth"


def test_module_key_strips_whitespace(tmp_path: Path) -> None:
    assert cache.module_key("  src/auth  ") == "src_auth"


def test_module_key_nested(tmp_path: Path) -> None:
    assert cache.module_key("a/b/c") == "a_b_c"


# ---- safe_key ---------------------------------------------------------------


def test_safe_key_returns_module_name(tmp_path: Path) -> None:
    assert cache.safe_key("缓存层") == "缓存层"


def test_safe_key_trim_invariant(tmp_path: Path) -> None:
    assert cache.safe_key("缓存层") == cache.safe_key(" 缓存层 ")


def test_safe_key_case_preserved(tmp_path: Path) -> None:
    assert cache.safe_key("Cache") == "Cache"
    assert cache.safe_key("CACHE") == "CACHE"


def test_safe_key_different_names_differ(tmp_path: Path) -> None:
    assert cache.safe_key("缓存层") != cache.safe_key("数据层")


def test_safe_key_special_chars(tmp_path: Path) -> None:
    key = cache.safe_key("模块 A/B (核心)")
    assert key == "模块 A_B (核心)"
    assert "/" not in key
    assert "\\" not in key


def test_safe_key_truncates_long_name(tmp_path: Path) -> None:
    long_name = "a" * 200
    assert len(cache.safe_key(long_name)) == 100
