# 详细设计 — `summarizer` 模块

> 对应文件：`src/codesense_v1/summarizer.py`
> 层级：L6
> 依赖：`codesense_v1.llm`、`codesense_v1.cache`、`codesense_v1.data.*`、`codesense_v1.errors`

---

## 1. 模块功能说明

将 Data Layer 的结构数据拼装成 Markdown prompt，调用 LLM 获取摘要，并写入缓存。提供两个公开函数分别服务于 `project_map` 和 `explore_module`。缓存检查也在此层统一处理（Lazy 策略）。

---

## 2. 对外暴露的接口签名

```python
async def project_map_summary(project_root: Path) -> str:
    """Return the project-level architecture summary as Markdown.

    Implements lazy cache: returns cached content if DB hash unchanged,
    otherwise regenerates via LLM and updates the cache.

    Raises:
        FileNotFoundError: if CodeGraph DB does not exist.
        LLMError: if the LLM call fails.
    """

async def module_summary(project_root: Path, module_path: str) -> str:
    """Return the module-level summary as Markdown for the given module_path.

    module_path is relative to project_root (e.g. 'src/auth').

    Lazy cache: uses cached result if DB hash unchanged.

    Raises:
        InvalidArgumentError: if the module_path directory does not contain __init__.py.
        FileNotFoundError: if CodeGraph DB does not exist.
        LLMError: if the LLM call fails.
    """
```

---

## 3. 核心数据结构定义

无自定义数据结构。输入来自 Data Layer 的 `Module`、`ModuleEdge`、`NodeRow` 等（不重定义，直接使用）。

内部辅助常量（私有）：
```python
_CODESENSE_DIR_NAME: str = ".codesense"
```

---

## 4. 错误码与异常处理规范

- `FileNotFoundError`：DB 不存在，直接向上传播（`CodeGraphDB.__init__` 抛出）。
- `InvalidArgumentError`：`module_path` 对应目录下无 `__init__.py`；文案：`"参数错误：路径 {module_path} 不是 Python 包（缺少 __init__.py）"`。
- `LLMError`：LLM 调用失败，直接向上传播（`llm.call_llm` 抛出）。
- OSError（缓存读写失败）：`write_*` 失败时向上传播；`read_*` 失败时返回 `None`（缓存未命中，触发重新生成）。

---

## 5. 关键算法或业务逻辑说明

### `project_map_summary(project_root)` 执行流程

```
1. codesense_dir = project_root / ".codesense"
2. db_path = project_root / ".codegraph" / "codegraph.db"
3. current_hash = cache.db_hash(db_path)          # FileNotFoundError if DB missing
4. if cache.is_cache_valid(codesense_dir, current_hash):
       cached = cache.read_project_map(codesense_dir)
       if cached is not None:
           return cached
5. cache.invalidate(codesense_dir)                 # 清除所有旧缓存
6. with CodeGraphDB(project_root) as db:
       prompt = _build_project_map_prompt(db)
7. summary = await llm.call_llm(prompt)            # LLMError on failure
8. cache.write_project_map(codesense_dir, summary, current_hash)
9. return summary
```

### `module_summary(project_root, module_path)` 执行流程

```
1. 校验 (project_root / module_path / "__init__.py").exists() → InvalidArgumentError if not
2. codesense_dir = project_root / ".codesense"
3. db_path = project_root / ".codegraph" / "codegraph.db"
4. current_hash = cache.db_hash(db_path)
5. mkey = cache.module_key(module_path)
6. if cache.is_cache_valid(codesense_dir, current_hash):
       cached = cache.read_module(codesense_dir, mkey)
       if cached is not None:
           return cached
7. cache.invalidate(codesense_dir)                 # project-level invalidation
8. with CodeGraphDB(project_root) as db:
       prompt = _build_module_prompt(db, module_path)
9. summary = await llm.call_llm(prompt)
10. cache.write_project_map 不在此调用（仅写当前模块的缓存）
    cache.write_module(codesense_dir, mkey, module_path, summary)
    # 同时更新 meta.json（通过 write_project_map 或独立写 meta）
    _write_meta(codesense_dir, current_hash)
11. return summary
```

> **注意**：步骤 7 `invalidate` 会清除旧的 project_map 缓存，下次读 project_map 会重新生成。这是 project 级缓存粒度的代价，保证一致性。

### `_build_project_map_prompt(db)` — 私有

组装 Markdown prompt：

```markdown
# 项目架构分析请求

你是一位软件架构师，请根据以下项目结构数据，生成一份**精简的项目架构概览**。

## 要求

输出为 Markdown 格式，包含：
1. **模块列表**：列出所有顶层模块（目录/包），每个模块一句话描述其职责
2. **模块依赖关系**：用表格或列表说明哪些模块依赖哪些模块

字数控制在 300-500 字以内，语言简洁专业，面向 AI 编程助手阅读。

## 项目结构数据

### 文件统计
- 总文件数：{stats.files}
- 总节点数：{stats.nodes}
- 编程语言：{languages}

### 模块列表（按包/目录划分）
{module_list_markdown}

### 模块间依赖关系
{package_deps_markdown}
```

### `_build_module_prompt(db, module_path)` — 私有

组装 Markdown prompt：

```markdown
# 模块详细分析请求

你是一位软件架构师，请根据以下模块结构数据，生成一份**模块理解文档**。

## 要求

输出为 Markdown 格式，包含：
1. **一句话描述**：该模块的核心职责
2. **对外接口**：列出所有公开函数/类（不以 _ 开头），含签名
3. **内部子模块**：该模块包含的文件列表
4. **依赖的模块**：该模块依赖的其他模块

## 模块数据

### 模块路径
{module_path}

### 包含文件
{files_in_module}

### 公开符号（函数/类，不含 _ 开头）
{public_symbols}

### 依赖的模块
{module_deps}
```

---

## 6. 与其他模块的交互契约

| 依赖 | 使用方式 |
|------|---------|
| `cache` | `db_hash`、`is_cache_valid`、`read_*`、`write_*`、`invalidate`、`module_key` |
| `llm` | `await call_llm(prompt)` |
| `data.db` | `CodeGraphDB(project_root)` 上下文管理器 |
| `data.files` | `list_files(db)` 用于统计 |
| `data.modules` | `list_modules(db)`、`module_dependencies(db)` |
| `data.aggregate` | `to_package_dependency_dict` 用于 project_map prompt |
| `errors` | `InvalidArgumentError`、`LLMError` |

| 调用方 | 使用方式 |
|--------|---------|
| `resources/project_map.py` | `await summarizer.project_map_summary(project_root)` |
| `tools/explore_module.py` | `await summarizer.module_summary(project_root, module_path)` |
