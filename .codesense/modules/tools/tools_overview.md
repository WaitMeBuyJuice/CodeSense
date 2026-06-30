## 一句话定位
MCP 工具实现层，承载 project_map / explore_module / explore_submodule / save_* / submit_* 等工具的请求处理与缓存协调。

## 架构简析
模块按「入口注册 → 项目根解析 → 读类工具 → 写回工具」分层。`__init__.py` 导入所有工具子模块触发 `@tool` 注册；`_project_root.py` 提供共享的项目根三级回退解析；读类工具（project_map / explore_module / explore_submodule）负责缓存命中判断与 prompt 内嵌返回；写回工具（save_* / submit_*）负责将 Agent 生成的摘要持久化到 cache。所有工具均通过 `@tool` 装饰器注册到 registry，对外接口由 MCP 协议定义而非 Python import 暴露。

## 子模块列表

| 子模块名 | 职责 | 包含文件 |
|---------|------|----------|
| tools_read | 读类 MCP 工具：缓存命中判断、miss 时内嵌 prompt 返回引导 Agent 生成 | src/codesense_v1/tools/project_map.py, src/codesense_v1/tools/explore_module.py, src/codesense_v1/tools/explore_submodule.py |
| tools_write | 写回 MCP 工具：将 Agent 生成的摘要/段落/模块划分持久化到 cache | src/codesense_v1/tools/save_module_summary.py, src/codesense_v1/tools/save_project_map_segment.py, src/codesense_v1/tools/save_submodule_summary.py, src/codesense_v1/tools/submit_project_map.py |
| tools_root | 共享辅助：项目根目录三级回退解析（env var → MCP roots → CWD 搜索） | src/codesense_v1/tools/_project_root.py |
| tools_init | 注册入口：导入所有工具子模块触发 @tool 注册 | src/codesense_v1/tools/__init__.py |

## 上下游关系

- **上游**（依赖此模块）：无（tools 是顶层协调者，由 server/registry 经 MCP 协议调用，无项目内模块 import tools）
- **下游**（此模块依赖）：cache、data、summarizer、registry、errors

## 实现约束清单

- 所有工具函数必须用 `@tool(name=..., description=..., input_schema=...)` 装饰器注册，name 与文件名/函数名解耦（如 `save_module_summary_tool` 注册名为 `save_module_summary`）
- 工具函数均为 `async`，首步统一调用 `resolve_project_root()`，返回 None 时返回 `project_root_not_found_error()` 错误文案
- DB 不存在时返回引导文案（提示运行 `codegraph init -i`），不抛异常
- 读类工具的缓存判断逻辑：`auto_expire=True` 时对比 `cache.is_segment_valid`/`is_cache_valid` 的 hash；`auto_expire=False` 时仅判断缓存文件是否存在
- `save_project_map_segment` 的 `segment_id` 受枚举约束：仅 `01_identity`/`03_modules`/`04_constraints`/`05_flows`/`06_concepts` 合法（02_structure/07_dependencies 由 project_map 程序化生成，不接受 Agent 写入）
- `save_project_map_segment` 保存时需重新计算对应 segment 的 source_hash 并随内容写入，保证后续缓存校验一致
- `explore_submodule` 支持 subgroup 模式（优先）与 file_path 模式（向后兼容）二选一，subgroup_name 优先级高于 file_path
- `explore_module`/`explore_submodule` 在 modules_index 缺失时返回引导先调 `project_map`，不直接报错
- 参数校验失败抛 `InvalidArgumentError`（语义级），非 `ValidationError`（schema 级，由 registry.dispatch 处理）
- `submit_project_map` 解析失败抛 `LLMError`（因 response 文本解析属 LLM 输出处理范畴）
- `__init__.py` 的 `__all__` 为空列表，工具通过注册而非导出对外暴露

## subgroups（JSON）

[{"name":"tools_read","description":"读类 MCP 工具：缓存命中判断、miss 时内嵌 prompt 返回引导 Agent 生成","files":["src/codesense_v1/tools/project_map.py","src/codesense_v1/tools/explore_module.py","src/codesense_v1/tools/explore_submodule.py"]},{"name":"tools_write","description":"写回 MCP 工具：将 Agent 生成的摘要/段落/模块划分持久化到 cache","files":["src/codesense_v1/tools/save_module_summary.py","src/codesense_v1/tools/save_project_map_segment.py","src/codesense_v1/tools/save_submodule_summary.py","src/codesense_v1/tools/submit_project_map.py"]},{"name":"tools_root","description":"共享辅助：项目根目录三级回退解析（env var → MCP roots → CWD 搜索）","files":["src/codesense_v1/tools/_project_root.py"]},{"name":"tools_init","description":"注册入口：导入所有工具子模块触发 @tool 注册","files":["src/codesense_v1/tools/__init__.py"]}]