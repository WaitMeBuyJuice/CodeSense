## 文件概述
该文件是 CodeSense 的图分析层，基于依赖图（ModuleEdge）和图数据库（CodeGraphDB）计算语言无关的架构信号。它提供目录级中心度（扇入/扇出）、基于 SCC 收缩的拓扑分层、Tarjan SCC 循环检测、跨目录公开 API 提取及外部依赖聚合，所有分析结果可通过 `architecture_features()` 一站式打包获取。

## 对外接口
- `DirCentrality` — 数据类，存储目录的扇入/扇出计数及外部扇出计数
- `ArchitectureFeatures` — 数据类，打包所有架构分析结果（中心度、拓扑层、循环、公开API、外部依赖）
- `compute_centrality(edges, modules, *, max_depth=None) -> dict[str, DirCentrality]` — 按目录维度计算扇入/扇出中心度，包含内部扇入、内部扇出和外部扇出
- `find_cycles(edges, modules, *, max_depth=None) -> list[list[str]]` — 使用迭代 Tarjan SCC 检测目录间循环依赖，返回大小 > 1 的强连通分量
- `topological_layers(edges, modules, *, max_depth=None) -> list[list[str]]` — SCC 收缩后计算拓扑分层（0层 = 无出边的基础设施层，层数从小到大递增）
- `cross_dir_public_api(db, *, max_depth=None, max_per_dir=30, symbol_kinds=...) -> dict[str, list[str]]` — 基于跨目录 imports 边提取各目录的公开API符号（被外部目录导入的 function/class/method/variable）
- `external_dependencies_by_dir(edges, modules, *, max_depth=None, max_per_dir=20) -> dict[str, list[str]]` — 按目录聚合外部依赖（`external::` 前缀的导入目标）
- `architecture_features(db, edges, modules, *, max_depth=None) -> ArchitectureFeatures` — 一次性打包所有架构分析结果

## 跨模块依赖
- **出向**：`db.py`、`modules.py`
- **入向**：`__init__.py`、`summarizer/summarizer.py`、`tools/project_map.py`、`tests/test_data_architecture.py`

## 典型调用链
- `summarizer` → `architecture_features()` → `compute_centrality()` + `topological_layers()` + `find_cycles()` + `cross_dir_public_api()` + `external_dependencies_by_dir()`
- `project_map` → `find_cycles()` → `_tarjan_sccs()` — 检测循环依赖后在输出中标记警告
- `compute_centrality` 内部：`_dir_of()` → 扇入/扇出计数集合 → `DirCentrality` 数据类
- `topological_layers` 内部：`_dir_of()` → `_build_dir_adj()` → `_tarjan_sccs()` → SCC 收缩 DAG → 后序遍历分层
- `cross_dir_public_api` 内部：遍历 db imports 边 → 检查 symbol_kinds → 按目标目录聚合被外部引用的符号