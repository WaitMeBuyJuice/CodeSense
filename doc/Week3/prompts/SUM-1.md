# Prompt — SUM-1：实现 `summarizer.py`

## 任务背景

`summarizer.py` 是 Week 3 的核心协调层，将 Data Layer 的结构数据拼装成 Markdown prompt，调用 LLM 获取摘要，并管理缓存（Lazy 策略）。

**前置条件**：
- `LLMError` 已在 `errors.py` 中定义（ERR-W3-1）
- `llm.call_llm` 已实现（LLM-1）
- `cache.*` 已实现（CACHE-1）

## 实现目标

新建 `src/codesense_v1/summarizer.py`，实现 `project_map_summary` 和 `module_summary` 两个公开异步函数。
新建 `tests/test_summarizer.py` 覆盖缓存命中/失效、参数校验、错误传播。

## 接口契约

```python
from pathlib import Path

async def project_map_summary(project_root: Path) -> str:
    """Return project-level architecture summary as Markdown.

    Lazy cache: if DB hash unchanged → return cached project_map.md content.
    Otherwise: invalidate cache, regenerate via LLM, write cache, return.

    Raises:
        FileNotFoundError: if CodeGraph DB (.codegraph/codegraph.db) does not exist.
        LLMError: if LLM call fails.
    """

async def module_summary(project_root: Path, module_path: str) -> str:
    """Return module-level summary as Markdown.

    module_path is relative to project_root (e.g. 'src/auth').
    Module boundary: directory must contain __init__.py.

    Lazy cache: if DB hash unchanged and module cache exists → return cached.
    Otherwise: invalidate cache, regenerate via LLM, write module cache + meta.json.

    Raises:
        InvalidArgumentError: if module_path dir lacks __init__.py or doesn't exist.
        FileNotFoundError: if CodeGraph DB does not exist.
        LLMError: if LLM call fails.
    """
```

### Lazy 缓存流程

**`project_map_summary(project_root)`**：
1. `codesense_dir = project_root / ".codesense"`
2. `db_path = project_root / ".codegraph" / "codegraph.db"`
3. `current_hash = cache.db_hash(db_path)` （FileNotFoundError if missing）
4. 若 `cache.is_cache_valid(codesense_dir, current_hash)` 为 True：
   - `cached = cache.read_project_map(codesense_dir)`
   - 若 `cached is not None`，直接返回
5. `cache.invalidate(codesense_dir)`
6. 用 `CodeGraphDB(project_root)` 提取结构数据，拼 prompt
7. `summary = await llm.call_llm(prompt)`
8. `cache.write_project_map(codesense_dir, summary, current_hash)`
9. 返回 `summary`

**`module_summary(project_root, module_path)`**：
1. 校验 `(project_root / module_path).is_dir()` 且含 `__init__.py`，否则 `InvalidArgumentError`
2. `codesense_dir = project_root / ".codesense"`
3. `db_path = project_root / ".codegraph" / "codegraph.db"`
4. `current_hash = cache.db_hash(db_path)`
5. `mkey = cache.module_key(module_path)`
6. 若 `cache.is_cache_valid(codesense_dir, current_hash)` 且 `cache.read_module(codesense_dir, mkey) is not None`：
   - 返回缓存内容
7. `cache.invalidate(codesense_dir)`
8. 用 `CodeGraphDB(project_root)` 提取模块数据，拼 prompt
9. `summary = await llm.call_llm(prompt)`
10. `cache.write_module(codesense_dir, mkey, module_path, summary, current_hash)`
11. 返回 `summary`

### Prompt 构建

**`_build_project_map_prompt(db)`**（私有函数）：

使用 `data.modules.list_modules`、`data.modules.module_dependencies`、`data.modules.to_package_dependency_dict`、`data.db.CodeGraphDB.stats` 提取数据，拼装以下 Markdown prompt：

```markdown
# 项目架构分析请求

你是一位软件架构师，请根据以下项目结构数据，生成一份**精简的项目架构概览**。

## 要求

输出为 Markdown 格式，包含：
1. **模块列表**：列出所有顶层模块（目录/包），每个模块一句话描述其职责
2. **模块依赖关系**：用表格或列表说明哪些模块依赖哪些模块（忽略 external:: 依赖）

字数控制在 300-500 字，语言简洁专业，面向 AI 编程助手阅读。

## 项目结构数据

### 统计
- 文件总数：{n_files}
- 代码节点数：{n_nodes}

### 包/模块列表
{package_list}

### 包间依赖关系（仅内部依赖）
{package_deps}
```

其中 `package_list` 列出每个 `package_id`（非 external），`package_deps` 展示 `to_package_dependency_dict` 的结果（过滤掉 `external::` 前缀的目标）。

**`_build_module_prompt(db, module_path)`**（私有函数）：

使用 `data.files.list_files`、`data.db.CodeGraphDB.iter_nodes`（kinds=["function","class"]）、`data.modules.module_dependencies` 提取模块内数据，拼装以下 Markdown prompt：

```markdown
# 模块详细分析请求

你是一位软件架构师，请根据以下模块结构数据，生成一份**模块理解文档**。

## 要求

输出为 Markdown 格式，包含：
1. **一句话描述**：该模块的核心职责（不超过 30 字）
2. **对外接口**：列出所有公开函数/类（名称不以 `_` 开头），格式：`函数名(参数签名)`
3. **内部文件**：该模块包含的文件列表
4. **依赖的模块**：该模块依赖的其他内部模块（忽略 external:: 依赖）

## 模块数据

### 模块路径
{module_path}

### 包含文件
{files_list}

### 公开符号（函数/类，名称不以 _ 开头）
{public_symbols}

### 依赖的模块（内部）
{internal_deps}
```

`files_list`：该模块路径下的文件（用 `list_files(db)` 过滤 `file_path.startswith(module_path)`）。
`public_symbols`：`iter_nodes(kinds=["function","class"])` 中 `file_path` 属于该模块且 `name` 不以 `_` 开头的符号，格式 `name: signature or name(no sig)`。
`internal_deps`：`module_dependencies(db, include_external=False)` 中源文件属于该模块的目标文件列表（去重、去自身）。

## 需要实现的文件

- `src/codesense_v1/summarizer.py`
- `tests/test_summarizer.py`

## 测试用例要求

使用 `tmp_path` fixture 和 `unittest.mock.patch` / `AsyncMock` mock `llm.call_llm` 及 `CodeGraphDB`。
**不依赖真实 CodeGraph DB**。

| 测试用例 | 场景 |
|---------|------|
| `test_project_map_cache_hit` | is_cache_valid=True 且 read_project_map 返回内容 → 不调用 LLM，直接返回缓存 |
| `test_project_map_cache_miss_calls_llm` | is_cache_valid=False → 调用 LLM，写缓存，返回 LLM 结果 |
| `test_project_map_db_not_found` | db_hash 抛 FileNotFoundError → 向上传播 |
| `test_module_summary_no_init_py` | 目录存在但无 `__init__.py` → InvalidArgumentError |
| `test_module_summary_dir_not_exist` | 目录不存在 → InvalidArgumentError |
| `test_module_summary_cache_hit` | is_cache_valid=True 且 read_module 返回内容 → 不调用 LLM |
| `test_module_summary_cache_miss_calls_llm` | 缓存失效 → 调用 LLM，写 module 缓存，返回 LLM 结果 |
| `test_module_summary_llm_error_propagates` | llm.call_llm 抛 LLMError → 向上传播 |

> 提示：测试中用 `tmp_path` 创建临时 `project_root`，手动创建 `module_path/__init__.py` 文件以通过包边界校验。mock `CodeGraphDB` 时用 `patch("codesense_v1.summarizer.CodeGraphDB")` 并返回一个 mock context manager。

## 验收标准

1. 所有上述测试用例通过
2. `uv run ruff check src/codesense_v1/summarizer.py tests/test_summarizer.py` 零警告
3. `uv run mypy --strict src/codesense_v1/summarizer.py tests/test_summarizer.py` 零错误
4. `uv run pytest -q` 全部通过

## 约束

- 只能创建/修改 `src/codesense_v1/summarizer.py` 和 `tests/test_summarizer.py`
- 不得修改其他任何文件
- 不依赖真实 CodeGraph DB 或真实 LLM API（全量 mock）
