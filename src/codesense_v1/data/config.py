"""CodeSense 配置文件读取工具。

读取 .codesense/.codesense_config（JSON），提供各配置项的访问函数。
配置文件不存在或字段缺失时返回默认值，不抛异常。
env 变量作为回退（向后兼容）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_CONFIG_FILE = ".codesense/.codesense_config"

# env 变量名（回退用）
_ENV_CACHE_AUTO_EXPIRE = "CODESENSE_CACHE_AUTO_EXPIRE"
_ENV_EXTRACT_DOCSTRINGS = "CODESENSE_EXTRACT_DOCSTRINGS"
_ENV_INCLUDE_DIRS = "CODESENSE_INCLUDE_DIRS"
_ENV_REF_DOCS_DIR = "CODESENSE_REF_DOCS_DIR"
_ENV_REF_DOCS_RECURSIVE = "CODESENSE_REF_DOCS_RECURSIVE"


def load_config(project_root: Path) -> dict[str, object]:
    """读取并返回配置 dict，失败时返回 {}"""
    config_path = project_root / _CONFIG_FILE
    try:
        text = config_path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def get_cache_auto_expire(project_root: Path) -> bool:
    """返回 cache_auto_expire 配置，默认 True。

    优先级：配置文件 > env CODESENSE_CACHE_AUTO_EXPIRE > 默认值 True。
    设置为 false 时禁用自动过期（始终使用缓存）。
    """
    cfg = load_config(project_root)
    if "cache_auto_expire" in cfg:
        val = cfg["cache_auto_expire"]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() != "false"
    # env 回退
    env_val = os.environ.get(_ENV_CACHE_AUTO_EXPIRE, "")
    if env_val:
        return env_val.strip().lower() != "false"
    return True


def get_extract_docstrings(project_root: Path) -> bool:
    """返回 extract_docstrings 配置，默认 True。

    优先级：配置文件 > env CODESENSE_EXTRACT_DOCSTRINGS > 默认值 True。
    设置为 false 时禁用 docstring 提取。
    """
    cfg = load_config(project_root)
    if "extract_docstrings" in cfg:
        val = cfg["extract_docstrings"]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() != "false"
    # env 回退
    env_val = os.environ.get(_ENV_EXTRACT_DOCSTRINGS, "")
    if env_val:
        return env_val.strip().lower() != "false"
    return True


def get_include_dirs(project_root: Path) -> list[str]:
    """返回 include_dirs 配置，默认 []。

    优先级：配置文件 > env CODESENSE_INCLUDE_DIRS（逗号分隔）> 默认值 []。
    """
    cfg = load_config(project_root)
    if "include_dirs" in cfg:
        val = cfg["include_dirs"]
        if isinstance(val, list):
            return [str(v).strip().replace("\\", "/").rstrip("/") for v in val if str(v).strip()]
    # env 回退（逗号分隔）
    raw = os.environ.get(_ENV_INCLUDE_DIRS, "")
    parts = [r.strip().replace("\\", "/").rstrip("/") for r in raw.split(",") if r.strip()]
    return [p for p in parts if p]


def get_ref_docs_paths(project_root: Path) -> list[str]:
    """返回 ref_docs.paths 配置，默认 []。

    优先级：配置文件 ref_docs.paths > env CODESENSE_REF_DOCS_DIR（单目录，回退）> []。
    """
    cfg = load_config(project_root)
    ref_docs = cfg.get("ref_docs")
    if isinstance(ref_docs, dict):
        val = ref_docs.get("paths")
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
    # env 回退（单目录）
    raw = os.environ.get(_ENV_REF_DOCS_DIR, "").strip()
    if raw:
        return [raw]
    return []


def get_ref_docs_recursive(project_root: Path) -> bool:
    """返回 ref_docs.recursive 配置，默认 False。

    优先级：配置文件 ref_docs.recursive > env CODESENSE_REF_DOCS_RECURSIVE > False。
    """
    cfg = load_config(project_root)
    ref_docs = cfg.get("ref_docs")
    if isinstance(ref_docs, dict) and "recursive" in ref_docs:
        val = ref_docs["recursive"]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() == "true"
    # env 回退
    env_val = os.environ.get(_ENV_REF_DOCS_RECURSIVE, "").strip().lower()
    return env_val == "true"


def get_ignore_paths(project_root: Path) -> list[str]:
    """返回 ignore_docs.paths 配置，默认 []。

    这些是精确路径（文件或目录），不是 gitignore 语法。
    """
    cfg = load_config(project_root)
    ignore_docs = cfg.get("ignore_docs")
    if isinstance(ignore_docs, dict):
        val = ignore_docs.get("paths")
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
    return []
