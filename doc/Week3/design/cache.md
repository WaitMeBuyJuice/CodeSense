# 详细设计 — `cache` 模块

> 对应文件：`src/codesense_v1/cache.py`
> 层级：L7 基础设施层
> 依赖：`codesense_v1.errors`、标准库（`hashlib`、`json`、`pathlib`、`datetime`）

---

## 1. 模块功能说明

管理 `.codesense/` 目录的读写，包括：DB hash 计算、缓存有效性判断、`project_map.md` 读写、`modules/<key>.json` 读写、`meta.json` 读写、缓存全量失效（删除旧内容）。

---

## 2. 对外暴露的接口签名

```python
def db_hash(db_path: Path) -> str:
    """Compute SHA-256 hex digest of the CodeGraph DB file."""

def is_cache_valid(codesense_dir: Path, current_hash: str) -> bool:
    """Return True iff meta.json exists and its db_hash == current_hash."""

def read_project_map(codesense_dir: Path) -> str | None:
    """Return cached project_map.md content, or None if not found."""

def write_project_map(codesense_dir: Path, content: str, current_hash: str) -> None:
    """Write project_map.md and update meta.json with current_hash."""

def read_module(codesense_dir: Path, module_key: str) -> str | None:
    """Return cached module summary Markdown, or None if not found."""

def write_module(
    codesense_dir: Path, module_key: str, module_path: str,
    summary: str, current_hash: str
) -> None:
    """Write modules/<module_key>.json and update meta.json with current_hash."""

def invalidate(codesense_dir: Path) -> None:
    """Delete all cached files under codesense_dir (keep directory itself)."""

def module_key(module_path: str) -> str:
    """Convert a module path to a safe filename key.

    Example: 'src/auth' -> 'src_auth', 'src\\auth' -> 'src_auth'
    """
```

---

## 3. 核心数据结构定义

**`meta.json` 文件结构**（Python dict 对应）：
```python
@dataclass
class MetaJson:
    db_hash: str
    generated_at: str  # ISO 8601, e.g. "2026-06-15T10:00:00+08:00"
```

**`modules/<key>.json` 文件结构**：
```python
@dataclass
class ModuleCache:
    module_path: str
    summary: str        # LLM 生成的 Markdown 文本
    generated_at: str   # ISO 8601
```

> 这两个 dataclass 仅用于内部序列化/反序列化，不对外暴露。

---

## 4. 错误码与异常处理规范

`cache.py` 的公开函数均**不抛自定义异常**——底层文件 IO 异常（`OSError`、`json.JSONDecodeError`）视为"缓存损坏/不存在"，采用以下策略：
- `read_*` 函数：捕获所有异常，返回 `None`（等价于缓存未命中）。
- `write_*` 函数：允许 `OSError` 向上传播（磁盘满等真实错误）；`codesense_dir` 不存在时自动 `mkdir`。
- `invalidate`：捕获 `OSError`，静默忽略（目录不存在 = 已失效）。
- `db_hash`：`FileNotFoundError` 向上传播（DB 不存在是上层应处理的问题）。
- `is_cache_valid`：所有异常 → 返回 `False`（等价于缓存无效）。

---

## 5. 关键算法或业务逻辑说明

### `db_hash(db_path)`
用 `hashlib.sha256` 分块读取 DB 文件（chunk_size=65536），返回 hexdigest。

### `is_cache_valid(codesense_dir, current_hash)`
1. 读取 `codesense_dir / "meta.json"`。
2. 解析 JSON，取 `db_hash` 字段。
3. 返回 `db_hash == current_hash`。
4. 任何异常 → 返回 `False`。

### `invalidate(codesense_dir)`
1. 删除 `codesense_dir / "project_map.md"`（若存在）。
2. 删除 `codesense_dir / "modules/"` 目录下所有 `*.json` 文件。
3. 删除 `codesense_dir / "meta.json"`（若存在）。
> 保留目录本身和目录结构，只清空内容文件。

### `module_key(module_path)`
将 `module_path` 中的 `/` 和 `\` 统一替换为 `_`，并去掉首尾空白。

### `write_project_map(codesense_dir, content, current_hash)`
1. 确保 `codesense_dir` 存在（`mkdir(parents=True, exist_ok=True)`）。
2. 写入 `codesense_dir / "project_map.md"`。
3. 写入 `codesense_dir / "meta.json"`（`{"db_hash": current_hash, "generated_at": now_iso()}`）。

### `write_module(codesense_dir, module_key, module_path, summary)`
1. 确保 `codesense_dir / "modules"` 存在。
2. 写入 `modules/<module_key>.json`：`{"module_path": ..., "summary": ..., "generated_at": ...}`。
3. 同时更新 `meta.json`（若已存在则覆盖 `db_hash` 字段）——需调用方传入 `current_hash`。

> **签名更新**：`write_module` 需额外接收 `current_hash: str` 参数：
> ```python
> def write_module(
>     codesense_dir: Path, module_key: str, module_path: str,
>     summary: str, current_hash: str
> ) -> None: ...
> ```

---

## 6. 与其他模块的交互契约

| 调用方 | 使用方式 |
|--------|---------|
| `summarizer.py` | 读缓存（`read_*`）、写缓存（`write_*`）、失效判断（`is_cache_valid`）、失效清除（`invalidate`） |
| `resources/project_map.py` | 通过 `summarizer` 间接使用（不直接 import cache） |
| `tools/explore_module.py` | 通过 `summarizer` 间接使用（不直接 import cache） |

`cache.py` 不 import 任何其他内部模块（除 `errors.py` 中的 `LLMError`，实际上 cache 不用 LLMError，完全无内部依赖）。
