## 子模块概述
读类 MCP 工具集合，负责 project_map / explore_module / explore_submodule 三个工具的请求处理。统一执行「项目根解析 → DB 存在性检查 → 缓存命中判断 → miss 时内嵌 prompt 返回引导 Agent 生成」流程，是 Agent 获取架构认知的主入口。

## 对外能力

| MCP 工具名 | 能力 |
|-----------|------|
| project_map | 返回项目级架构概览（仓库定位、模块列表、依赖关系、概念索引）；缓存全段就绪时返回拼接 Markdown，否则返回缺失段落列表 + 内嵌生成 prompt |
| explore_module | 返回单模块深度架构（职责、接口、文件、依赖）；缓存命中返回 Markdown，miss 返回生成引导 |
| explore_submodule | 返回子模块/文件级文档；支持 subgroup 模式（优先）与 file_path 模式（向后兼容） |

关键内部函数：`_seg_valid`（project_map 私有，按 auto_expire 决定是仅判存在还是校验 hash）。

## 跨模块依赖

- 下游：cache、data、errors、registry、summarizer、tools（_project_root）
- 上游：tools（被 __init__ 导入触发注册；由 server 经 registry.dispatch 调用）

## 典型调用链

### project_map 缓存命中路径
`server._call_tool` → `registry.dispatch` → `project_map` → `resolve_project_root` → `cache.read_modules_index` / `cache.is_segment_valid` → 全段有效 → `cache.render_project_map` 返回拼接 Markdown

### project_map 缓存 miss 路径
`project_map` → 各段 `_seg_valid` 判定缺失 → 程序化段（02_structure/07_dependencies）立即 `cache.write_segment` → Agent 段（01/03/04/05/06）调 `summarizer.get_*_segment_prompt` 取 prompt → 内嵌缺失列表返回 → Agent 生成后调 `save_project_map_segment` → 重调 `project_map` 命中

### explore_module 缓存 miss 路径
`explore_module` → `resolve_project_root` → `cache.read_modules_index` 校验模块存在 → `_compute_module_hash` 计算当前 hash → `cache.read_module` 对比 stored_hashes → miss → `summarizer.get_module_prompt` 取 prompt → 内嵌返回 → Agent 调 `save_module_summary` → 重调命中