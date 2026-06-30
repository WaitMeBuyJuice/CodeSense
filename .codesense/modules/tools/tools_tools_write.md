## 子模块概述
写回 MCP 工具集合，负责将 Agent 生成的自然语言摘要持久化到 cache 层。涵盖模块摘要、子模块文档、project_map 段落、模块划分四种写回场景，是「Agent 即 LLM」协作模式中数据回写的唯一入口。

## 对外能力

| MCP 工具名 | 能力 |
|-----------|------|
| save_module_summary | 写入模块摘要 Markdown + 可选 subgroups 划分；委托 `summarizer.save_module_summary` 落盘 |
| save_project_map_segment | 写入指定 segment_id 的段落内容；保存前重算对应 source_hash 保证后续校验一致 |
| save_submodule_summary | 写入子模块文档；支持 subgroup 模式与 file_path 模式，返回写入路径 |
| submit_project_map | 解析模块划分文本（`名称|职责|目录` 格式）写入 modules_index.json 并返回渲染后架构 Markdown |

## 跨模块依赖

- 下游：data、errors、registry、tools（_project_root）；间接经 summarizer 调 cache
- 上游：无（由 Agent 主动调用，无项目内模块 import）

## 典型调用链

### save_project_map_segment 写回路径
`save_project_map_segment_tool` → `resolve_project_root` → DB 存在性检查 → `CodeGraphDB` 查询对应 segment 的源数据 → 计算 source_hash（01=identity_hash / 03=architecture_hash / 04,07=dependencies_hash / 05=calls_edges sha256 / 06=symbol_map+modules_desc sha256）→ `cache.write_segment` 落盘 → 返回确认

### save_module_summary 写回路径
`save_module_summary_tool` → 参数校验（module_name/summary 非空）→ `resolve_project_root` → `summarizer.save_module_summary`（内部写 module.md + 更新 modules_index 的 subgroups）→ 返回字符数确认

### submit_project_map 解析路径
`submit_project_map_tool` → `resolve_project_root` → `summarizer.submit_project_map`（解析 `名称|职责|目录` 文本 → 写 modules_index.json → 渲染架构 Markdown）→ 返回渲染结果；解析失败抛 `LLMError`