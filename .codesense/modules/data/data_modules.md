## 文件概述
该文件负责从 CodeGraph 数据库中提取模块（文件）列表和文件级依赖边。它处理 `imports` 和 `calls` 两类边，对内部分辨导入路径以匹配项目内文件，对外部依赖则标记 `is_external=True` 并以 `external::` 前缀区分。

## 对外接口
- `Module` — 数据类，代表一个代码模块（文件），含 `id`（POSIX 文件路径）、`file_path`、`language`、`package_id`（所属包/目录）字段
- `ModuleEdge` — 数据类，代表代码模块间的有向依赖边，含 `source`、`target`、`kind`（"imports" | "calls"）、`is_external` 字段
- `list_modules(db: CodeGraphDB) -> list[Module]` — 遍历 DB 中所有文件，构建 Module 列表
- `module_dependencies(db, *, include_external=True, include_calls=True, include_imports=True) -> list[ModuleEdge]` — 提取模块间依赖边。calls 边含严格过滤规则：目标必须是 callable（function/method/class），非 callable 源仅信任同文件调用，跨文件 calls 仅当源文件已有对应 imports 边时保留
- `to_file_dependency_dict(edges) -> dict[str, dict[str, list[str]]]` — 将边列表转为 `{源文件: {"imports": [...], "calls": [...]}}` 的嵌套字典，外部目标加 `external::` 前缀
- `to_package_dependency_dict(edges, modules, *, include_self_loops=False) -> dict[str, dict[str, list[str]]]` — 将边列表按包（目录）聚合，Python 用点分名、其他语言用斜杠路径，默认排除自环

## 跨模块依赖
- **出向**：`db.py`
- **入向**：`__init__.py`、`aggregate.py`、`architecture.py`、`hashes.py`、`summarizer/summarizer.py`、`tools/project_map.py`、`tools/save_project_map_segment.py`、`scripts/validate_dir_deps.py`、`tests/test_data_modules.py`、`tests/test_data_aggregate.py`、`tests/test_data_architecture.py`

## 典型调用链
- `summarizer` → `list_modules()` + `module_dependencies()` → `CodeGraphDB.iter_files/nodes/edges` → 构建 Module/ModuleEdge 列表
- `aggregate.py` → `module_dependencies()` → `to_file_dependency_dict()` / `to_package_dependency_dict()` — 聚合为目录级依赖
- `architecture.py` → `module_dependencies()` 获取边 → `compute_centrality` / `topological_layers` 分析架构特征
- `module_dependencies` 内部：遍历 imports 边 → `_resolve_relative_path` / `_resolve_internal_import` 解析导入路径 → 判定 external/internal