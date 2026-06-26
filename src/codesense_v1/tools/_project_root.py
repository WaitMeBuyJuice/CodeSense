"""Shared helper: resolve project root via env var, MCP roots, or CWD search."""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from pathlib import Path


async def resolve_project_root() -> Path | None:
    """Return the project root via three-tier fallback:

    1. ``CODESENSE_PROJECT_ROOT`` env var (explicit, highest priority)
    2. MCP ``roots/list`` from the client (IDE workspace root)
    3. Search CWD upward for ``.codegraph/codegraph.db``

    Returns ``None`` if all three fail.
    """
    # 1. Explicit env var
    env_val = os.environ.get("CODESENSE_PROJECT_ROOT", "").strip()
    if env_val:
        return Path(env_val)

    # 2. MCP roots/list
    root = await _root_from_mcp()
    if root is not None:
        return root

    # 3. CWD upward search
    return _root_from_cwd()


async def _root_from_mcp() -> Path | None:
    try:
        from mcp.server.lowlevel.server import request_ctx  # type: ignore[import-untyped]

        ctx = request_ctx.get()
        result = await ctx.session.list_roots()
        if result.roots:
            uri_str = str(result.roots[0].uri)
            path_str = urllib.request.url2pathname(urllib.parse.urlparse(uri_str).path)
            candidate = Path(path_str)
            if candidate.exists():
                return candidate
    except Exception:  # noqa: BLE001
        pass
    return None


def _root_from_cwd() -> Path | None:
    candidate = Path.cwd()
    for _ in range(10):
        if (candidate / ".codegraph" / "codegraph.db").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def project_root_not_found_error() -> str:
    return (
        "# 错误\n\n"
        "无法自动检测项目根目录。请通过以下任一方式指定：\n\n"
        "**方式 1（推荐）**：在 MCP 配置的 `env` 字段中设置：\n"
        "```json\n"
        '"CODESENSE_PROJECT_ROOT": "/path/to/your/project"\n'
        "```\n\n"
        "**方式 2**：确保已在项目根目录运行 `codegraph init -i`，"
        "CodeSense 将自动从当前工作目录向上查找 `.codegraph/codegraph.db`。"
    )
