## 一句话定位
.codesense 缓存读写、哈希校验与失效管理。

## 架构简析
单文件模块（`cache.py`），围绕 `.codesense/` 目录下的五类缓存实体组织 API：`meta.json`（全局元信息与 db_hash）、`project_map.md`（拼接后整体产物）、`modules_index.json`（模块清单）、`modules/<mkey>/`（模块摘要 + `.hashes.json` + 子模块文件）、`segments/`（project_map 分段缓存）。同一文件内按四种实体（project_map / module 摘要 / segment / submodule）组织读写、哈希校验与剪枝逻辑，模块级与子模块级共享 `module_key`/`safe_key` 路径转义规则。

## 子模块列表

| 子模块名 | 职责 | 包含文件 |
|---|---|---|
| cache_storage | .codesense 缓存读写、哈希校验与失效 | `src/codesense_v1/cache/cache.py` |

## 上下游关系
- 上游（cache 依赖的模块）：无
- 下游（依赖 cache 的模块）：summarizer, tools

## 实现约束清单
1. 所有缓存写入同步更新 `meta.json` 的 `db_hash`，作为整体失效判定基准（`is_cache_valid` 比对此值）。
2. `write_modules_index` / `write_module` 会触发 `_prune_stale_modules` 清理不在 active_keys 中的模块目录。
3. segment 与 module/submodule 各有独立 hash 文件（`<mkey>/.hashes.json`、`segments/<id>.hash`），校验粒度独立互不耦合。
4. `invalidate` 清空 `modules/` 但不清 `segments/`；后者由 `invalidate_segments` 单独清。
5. `module_key`/`safe_key` 把 module_path/name 转文件名安全 key，避免路径分隔符与非法字符问题。
6. `write_module` 的 `module_name` 参数保留仅为 API 兼容（`# noqa: ARG001`），实际不参与写入路径计算。