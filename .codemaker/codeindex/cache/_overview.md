---
module_id: cache
architectural_role: 缓存读写层
world_model_hints:
  - CodeSense 通过 segment 化 project_map（4 段拼接）+ 模块摘要两层缓存，把 LLM 生成的架构理解持久化到 .codesense/ 目录
  - 缓存失效以 codegraph.db 的 SHA-256 为基准：hash 一致命中，不一致触发重生（auto-expire 由 summarizer 读环境变量决定，cache 只做机械比对）
  - cache 是纯 I/O 层，不含业务判断；所有 read_* 返回 None 视为 miss，write_* 传播 OSError，invalidate 静默忽略缺失
upstream_modules:
  - tools/project_map
  - tools/explore_module
  - tools/save_project_map_segment
  - summarizer
downstream_modules: []
---

## Files

- `src/codesense_v1/cache/cache.py` — 缓存读写实现（全部公开函数 + 私有 helper）
- `src/codesense_v1/cache/__init__.py` — re-export 20 个公开符号到 `codesense_v1.cache` 命名空间

## 子文档速览

- `cache_core.md` — 对外接口、跨模块依赖、典型调用链、实现约束清单、内置文档摘要

## 模块概述

cache 模块是 CodeSense 的 `.codesense/` 目录读写层，负责把 LLM 生成的架构理解（project_map 四段 + 模块摘要）持久化到磁盘，并提供基于 codegraph.db SHA-256 的失效判断。它是 leaf 模块（无内部下游依赖），只依赖标准库（`hashlib`/`json`/`re`/`datetime`/`pathlib`）。

缓存分两层：

1. **project_map 段缓存**（`project_map_segments/`）：4 段独立 `.md` + `.hash` 文件，`render_project_map` 按 `_SEGMENT_IDS` 顺序拼接为 `project_map.md`。01/03 段由 Agent 生成，02/04 段程序生成。
2. **模块摘要缓存**（`modules/`）：`<safe_key>.md` + `.hashes.json`（per-module content hash），配合 `modules_index.json` 做模块名→文件映射。

## 架构简析

cache 不做任何业务决策，只做机械的文件读写与 hash 比对：

- **失效判断分层**：`is_cache_valid` 比对 meta.json 的 `db_hash`（整库级）；`is_segment_valid` 比对单段 `.hash`（段级）；模块级失效由 summarizer 读 `modules/.hashes.json` + 环境变量 `CODESENSE_CACHE_AUTO_EXPIRE` 决定。cache 自身不读环境变量。
- **写入即清理**：`write_modules_index` 写入前调 `_prune_stale_modules`，删除不再出现在新索引中的模块 `.md` 与 `.hashes.json` 条目，避免孤儿缓存。
- **key 生成双轨**：`module_key(path)` 旧版（路径→下划线，仅替换 `/` `\`）；`safe_key(name)` 新版（替换全部非法文件名字符 + 控制字符为 `_`，strip `_`，截断 100 字符）。新代码用 `safe_key`，`module_key` 保留兼容。

## 上下游关系

**上游（谁用 cache，extracted）**：

| 调用方 | import 形式 | 用途 |
|--------|------------|------|
| `tools/project_map.py` | `from codesense_v1 import cache` | 读段缓存、判断段有效性、render |
| `tools/explore_module.py` | `from codesense_v1 import cache` | 读 modules_index、读模块摘要 |
| `tools/save_project_map_segment.py` | `from codesense_v1 import cache` | 写段缓存 |
| `summarizer/summarizer.py` | `from codesense_v1 import cache` | submit_project_map / save_module_summary / render_project_map |

**下游（cache 依赖）**：无内部依赖（leaf）。仅依赖标准库。
