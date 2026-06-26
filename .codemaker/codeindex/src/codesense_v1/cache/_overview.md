---
module_id: cache
architectural_role: "缓存读写层"
world_model_hints:
  - "位于 summarizer 和 tools 之下，封装 .codesense/ 目录的读写"
upstream_modules:
  - module: summarizer
    confidence: extracted
  - module: tools
    confidence: extracted
downstream_modules: []
---

## Files

### 源代码路径
- `src/codesense_v1/cache/`

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/cache/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/cache/cache_core.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `cache_core.md` | 缓存文件读写、有效性校验 | db_hash, is_cache_valid, read_project_map, read_modules_index, read_module, read_module_hashes, write_module |

## 模块概述

本模块封装 `.codesense/` 缓存目录的全部文件 I/O 操作，为 summarizer 和 tools 层提供统一的缓存读写接口，实现项目架构概览和模块摘要的持久化与增量更新。

上游：summarizer（提交/保存时写入缓存）、tools（explore_module/project_map 读取缓存判断是否命中）。

下游：无，本模块仅做文件系统 I/O，不调用其他业务模块。

## 架构简析

单文件模块 `cache.py`，核心概念：`db_hash`（CodeGraph DB 的 SHA256 哈希，用于 project_map 缓存失效判断）+ `module_hashes`（各模块内容哈希，用于模块级缓存失效）。读接口为纯查询，写接口仅 summarizer 调用。

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：summarizer（写入 project_map/module_summary）、tools（读取缓存判断命中/未命中）
- **下游**：无
