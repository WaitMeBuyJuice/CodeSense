# 任务拆解 - data 模块

> 详细设计：`doc/design/data.md`
> 目标文件：`src/codesense_v1/data/`、`scripts/validate_dir_deps.py`、`tests/test_data_*.py`

---

## T-D-1：迁移 db.py（SQLite 边界）

- **目标文件**：`src/codesense_v1/data/db.py`
- **验收**：
  - `CodeGraphDB` 能 open 真实 `codegraph.db`；`stats()` 返回正确计数
  - `FileRow` / `NodeRow` / `EdgeRow` 均为 `frozen=True` dataclass
  - 无 `Optional`、`List` 等旧式类型注解；`__exit__` 有完整参数注解
  - `mypy strict` 通过；`ruff` 零警告
- **测试**：`tests/test_data_db.py` 全绿
- **状态**：✅ 完成

---

## T-D-2：迁移 files.py

- **目标文件**：`src/codesense_v1/data/files.py`
- **验收**：
  - `list_files(db)` → `list[FileRow]`
  - `directory_tree(db)` → `DirectoryNode`，层级正确
  - 无旧式类型注解
  - `mypy strict` 通过；`ruff` 零警告
- **状态**：✅ 完成

---

## T-D-3：迁移 modules.py（核心）

- **目标文件**：`src/codesense_v1/data/modules.py`
- **验收**：
  - `list_modules` / `module_dependencies` / `to_file_dependency_dict` / `to_package_dependency_dict` 全部输出与源项目一致
  - `_resolve_id` / `_resolve_internal_import` 算法 1:1 复刻
  - 无旧式类型注解；`Set[str]` → `set[str]`，`Tuple` → `tuple`
  - `mypy strict` 通过；`ruff` 零警告
- **测试**：`tests/test_data_modules.py` 全绿
- **状态**：✅ 完成

---

## T-D-4：迁移 aggregate.py

- **目标文件**：`src/codesense_v1/data/aggregate.py`
- **验收**：
  - `directory_dependencies` / `directory_edges` 输出与源项目一致
  - `_module_to_dir` 的 `max_depth` 截断逻辑正确
  - `mypy strict` 通过（含 `str | None` type narrowing）
- **测试**：`tests/test_data_aggregate.py` 全绿
- **状态**：✅ 完成

---

## T-D-5：迁移 scripts/validate_dir_deps.py

- **目标文件**：`scripts/validate_dir_deps.py`
- **验收**：
  - import 全部改为 `from codesense_v1.data import ...`
  - `DEFAULT_PROJECT` 指向 `E:\Python_Project\CodeSense\codegraph`
  - `--out` 默认值为 V1 项目根的 `out/` 目录
  - `_compute_dep_facts` 函数完整保留，参数补齐类型注解
  - 跑 `uv run python scripts/validate_dir_deps.py <real-project>` 能产出 4 个文件
- **状态**：✅ 完成

---

## T-D-6：补单测 + 文档

- **单测**：
  - `tests/test_data_db.py`：7 个用例（open、missing、iter_files、kind_filter、iter_edges、get_node、context_manager）✅
  - `tests/test_data_modules.py`：8 个用例（list_modules、internal/external deps、dict 排序、包聚合、resolve_id、external prefix）✅
  - `tests/test_data_aggregate.py`：4 个用例（basic、max_depth、external passthrough、flat list）✅
  - `tests/conftest.py`：共享 `minimal_db_root` fixture ✅
- **文档**：
  - `doc/design/data.md` ✅
  - `doc/tasks/data.md`（本文件）✅

---

## T-D-7：质量门禁

- `uv run mypy src tests` — 零错误 ✅
- `uv run ruff check src tests scripts` — 零警告 ✅
- `uv run pytest` — 57 passed ✅
