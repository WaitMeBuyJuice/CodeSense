## 一句话定位
管理 `.codesense/` 目录下的本地文件缓存，提供项目地图、模块摘要、子模块文档及段缓存的读写与校验。

## 架构简析
单文件模块 `cache.py`，约 30 个函数，分为四层：

- **元数据层**：`_meta_path`、`_write_meta`、`_now_iso`、`is_cache_valid`——通过 `project_map.json` 中的 `db_hash` 判断整个缓存是否过期。
- **项目地图层**：`read_project_map`、`write_project_map`、`render_project_map`——项目级 Markdown 地图的读写，以及从段文件拼接完整地图。
- **段缓存层**：`read_segment`、`write_segment`、`read_segment_hash`、`is_segment_valid`、`invalidate_segments`——将项目地图拆分为 7 个独立段，按段粒度校验 hash 并读写。
- **模块/子模块缓存层**：`read/write_module`、`read/write_module_hash(es)`、`read/write_submodule(hashes)`、`write_submodule_hash`、`read/write_modules_index`——模块索引、模块摘要、子模块文档的 CRUD，支持按 key 剪枝和 hash 增量校验。
- **辅助与清理层**：`db_hash`、`invalidate`、`_clear_modules_dir`、`_prune_stale_modules`、`module_key`、`safe_key`——全局失效、名-键转换、目录清理。

## 子模块列表
| 子模块名 | 作用 | 路径 |
|---|---|---|
| `cache_cache` | 所有缓存读写、校验、失效、键名转换的核心实现 | `src/codesense_v1/cache/cache.py` |

## 上下游关系
- **上游（依赖此模块）**：`src/codesense_v1/summarizer`、`src/codesense_v1/tools`
- **下游（此模块依赖）**：无（仅依赖标准库 `datetime`、`hashlib`、`json`、`pathlib`、`re`、`shutil`）

## 实现约束清单
- 所有 `read_*` 函数在任意异常时返回 `None`（视为缓存缺失），调用方不得依赖具体的异常类型。
- 所有 `write_*` 函数在真实 I/O 失败时抛出 `OSError`，调用方必须自行处理。
- `db_hash` 在文件不存在时抛出 `FileNotFoundError`，不吞没此错误。
- `is_cache_valid` 和 `is_segment_valid` 任何异常都返回 `False`，而非抛出。
- `invalidate` 静默忽略缺失文件/目录，清空整个缓存（project_map、modules_index、meta、modules/）。
- `invalidate_segments` 删除 `project_map_segments/` 下所有文件并尝试删除空目录，静默忽略错误。
- `write_modules_index` 会自动剪枝不在新索引中的模块目录（按 `safe_key` 匹配），仅删除 `.md` 和 hash 条目，不触及外部文件。
- `safe_key` 替换非法文件名字符为 `_`、去首尾 `_`、截断到 100 字符；空名返回 `"_"`。`module_key` 仅替换路径分隔符。
- `render_project_map` 要求全部 7 个段均存在，任一缺失返回 `None` 并跳过写入。
- 哈希存储分模块级（`overview` 键）和子模块级（按 file_key 键），`read_module_hashes` 和 `read_submodule_hashes` 互不重叠（子模块读取排除 `overview` 键）。
- 缓存目录结构：`project_map.md` / `project_map.json` / `modules_index.json` / `modules/<mkey>/<mkey>_overview.md` + `.hashes.json` + `<file_key>.md` / `project_map_segments/<seg_id>.md` + `.hash`。