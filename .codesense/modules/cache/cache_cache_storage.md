## 子模块概述
`cache_storage` 是 `cache` 模块的唯一构成（单文件），负责 `.codesense/` 目录下五类缓存实体的读写、哈希校验与失效：`meta.json`（全局元信息与 db_hash）、`project_map.md`（拼接后整体产物）、`modules_index.json`（模块清单）、`modules/<mkey>/`（模块摘要 + `.hashes.json` + 子模块文件）、`segments/`（project_map 分段缓存）。所有 API 均以 `codesense_dir` 为根，按四种实体（project_map / module 摘要 / segment / submodule）组织读写、哈希校验与剪枝逻辑。

## 对外能力

- **元信息与整体校验**：`db_hash` 计算 SQLite db 的 SHA-256；`is_cache_valid` 比对 `meta.json` 中的 db_hash；`invalidate` 清空整个 `modules/` 目录；`_write_meta` / `_clear_modules_dir` 为内部辅助。
- **project_map 读写**：`read_project_map` / `write_project_map` 读写整体 `project_map.md` 并更新 meta；`render_project_map` 拼接所有 segment Markdown 形成最终产物。
- **modules_index 读写**：`read_modules_index` / `write_modules_index` 读写模块清单 + aux_dirs，写时触发 `_prune_stale_modules` 清理不在 active_keys 中的模块目录。
- **module 摘要读写**：`module_key` / `safe_key` 把 `module_path`/`module_name` 转文件名安全 key；`read_module_hashes` 聚合各 `<mkey>/.hashes.json`；`write_module_hash` / `read_module` / `write_module` 读写 `modules/<mkey>/<mkey>_overview.md`；`write_module` 的 `module_name` 参数保留仅为 API 兼容（`# noqa: ARG001`），不参与写入路径计算。
- **segment 读写**：`_segment_dir` / `_segment_md_path` / `_segment_hash_path` 定位路径；`read_segment` / `read_segment_hash` / `is_segment_valid` / `write_segment` 分段读写与校验；`invalidate_segments` 单独清空 `segments/`。
- **submodule 读写**：`submodule_dir` / `read_submodule_hashes` / `write_submodule_hash` / `read_submodule` / `write_submodule` 处理模块下子模块文档。

## 跨模块依赖
- 下游：无
- 上游：cache（同模块，子模块与父模块同体）

## 典型调用链

### project_map 整体刷新
`db_hash(db_path)` → `is_cache_valid(codesense_dir, current_hash)` → 失效时 `invalidate(codesense_dir)` + `write_modules_index` + 各 `write_module` + `render_project_map`

### module 摘要增量更新
`module_key(module_path)` → `read_module_hashes(codesense_dir)` → 比对 `module_hash` → `write_module`（同步 `write_module_hash` + 触发 `_prune_stale_modules`）

### segment 缓存命中判定
`is_segment_valid(codesense_dir, segment_id, current_hash)` → 命中走 `read_segment`；未命中走 `write_segment` → `render_project_map` 拼接最终产物

### submodule 增量刷新
`submodule_dir(codesense_dir, module_key)` → `read_submodule_hashes` → 比对哈希 → `write_submodule`（同步 `write_submodule_hash`）