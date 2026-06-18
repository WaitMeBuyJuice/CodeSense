# Prompt — CACHE-1：实现 `cache.py`

## 任务背景

Week 3 的 LLM 摘要结果需要持久化到 `.codesense/` 目录，以实现 Lazy 缓存（DB hash 驱动）。
`cache.py` 是基础设施叶子模块，不依赖任何其他内部模块，仅用标准库（`hashlib`、`json`、`pathlib`、`datetime`）。

## 实现目标

新建 `src/codesense_v1/cache.py`，实现以下 8 个公开函数。新建 `tests/test_cache.py` 覆盖正常路径和异常路径。

## 接口契约

```python
from pathlib import Path

def db_hash(db_path: Path) -> str:
    """Compute SHA-256 hex digest of the file at db_path.
    Raises FileNotFoundError if the file does not exist."""

def is_cache_valid(codesense_dir: Path, current_hash: str) -> bool:
    """Return True iff codesense_dir/meta.json exists and its db_hash == current_hash.
    Returns False on any error (missing file, bad JSON, etc.)."""

def read_project_map(codesense_dir: Path) -> str | None:
    """Return content of codesense_dir/project_map.md, or None if missing/unreadable."""

def write_project_map(codesense_dir: Path, content: str, current_hash: str) -> None:
    """Write content to codesense_dir/project_map.md and update meta.json.
    Creates codesense_dir if it does not exist."""

def read_module(codesense_dir: Path, module_key: str) -> str | None:
    """Return the 'summary' field from codesense_dir/modules/<module_key>.json,
    or None if missing/unreadable."""

def write_module(
    codesense_dir: Path,
    module_key: str,
    module_path: str,
    summary: str,
    current_hash: str,
) -> None:
    """Write modules/<module_key>.json and update meta.json with current_hash.
    Creates codesense_dir/modules/ if needed."""

def invalidate(codesense_dir: Path) -> None:
    """Delete project_map.md, all modules/*.json, and meta.json under codesense_dir.
    Silently ignores missing files/dirs."""

def module_key(module_path: str) -> str:
    """Convert a module path to a safe filename key.
    Replaces '/' and '\\\\' with '_', strips whitespace.
    Example: 'src/auth' -> 'src_auth'"""
```

### `.codesense/` 目录结构

```
.codesense/
├── project_map.md          # project_map 内容
├── modules/
│   └── <module_key>.json   # {"module_path": str, "summary": str, "generated_at": str}
└── meta.json               # {"db_hash": str, "generated_at": str}
```

### `meta.json` 格式

```json
{"db_hash": "<64-char hex>", "generated_at": "<ISO 8601 with timezone>"}
```

### `modules/<key>.json` 格式

```json
{"module_path": "src/auth", "summary": "<Markdown>", "generated_at": "<ISO 8601>"}
```

## 需要实现的文件

- `src/codesense_v1/cache.py`
- `tests/test_cache.py`

## 测试用例要求

使用 `tmp_path` fixture（pytest 内置），不依赖真实文件系统外部状态。

| 测试用例 | 场景 |
|---------|------|
| `test_db_hash_returns_hex_string` | 创建临时文件，验证返回 64 位 hex |
| `test_db_hash_file_not_found` | 路径不存在 → `FileNotFoundError` |
| `test_is_cache_valid_true` | write_project_map 后 is_cache_valid 同 hash → True |
| `test_is_cache_valid_wrong_hash` | 不同 hash → False |
| `test_is_cache_valid_no_meta` | meta.json 不存在 → False |
| `test_read_write_project_map` | 写后读回内容一致 |
| `test_write_project_map_creates_dir` | codesense_dir 不存在时自动创建 |
| `test_write_project_map_updates_meta` | write 后 meta.json 中 db_hash 与传入 hash 一致 |
| `test_read_module_none_if_missing` | 不存在 → None |
| `test_read_write_module` | 写后读回 summary 一致 |
| `test_write_module_updates_meta` | write_module 后 meta.json db_hash 正确 |
| `test_invalidate_clears_all` | invalidate 后 read_project_map/read_module → None，is_cache_valid → False |
| `test_module_key_slash` | `src/auth` → `src_auth` |
| `test_module_key_backslash` | `src\\auth` → `src_auth` |

## 验收标准

1. 所有上述测试用例通过
2. `uv run ruff check src/codesense_v1/cache.py tests/test_cache.py` 零警告
3. `uv run mypy --strict src/codesense_v1/cache.py tests/test_cache.py` 零错误
4. `uv run pytest -q` 全部通过（包含现有 57 个测试）

## 约束

- 只能创建/修改 `src/codesense_v1/cache.py` 和 `tests/test_cache.py`
- 不得修改其他任何文件
- 不依赖任何第三方库（仅标准库）
- `generated_at` 使用带时区的 ISO 8601 格式：`datetime.now(timezone.utc).isoformat()`
