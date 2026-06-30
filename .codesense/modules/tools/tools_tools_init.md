## 子模块概述
注册入口子模块，仅含 `__init__.py`。通过导入所有工具子模块触发各文件内的 `@tool` 装饰器执行，完成 MCP 工具向 registry 的注册。本身无业务逻辑，是 tools 包被 import 时的副作用触发点。

## 对外能力

仅供内部调用。`__all__` 为空列表，不导出任何符号。被 `server.build_server` 或包导入机制触发后，副作用是将 7 个工具（project_map / explore_module / explore_submodule / save_module_summary / save_project_map_segment / save_submodule_summary / submit_project_map）注册到 registry 的全局工具表。

## 跨模块依赖

- 下游：tools（explore_module / explore_submodule / project_map / save_module_summary / save_project_map_segment / save_submodule_summary / submit_project_map 七个子模块）
- 上游：无（由 server 层或 Python 包导入机制触发）

## 典型调用链

### 服务启动注册路径
`server.build_server` → `import codesense_v1.tools` → `__init__.py` 执行 `from . import explore_module, explore_submodule, project_map, save_module_summary, save_project_map_segment, save_submodule_summary, submit_project_map` → 各模块顶层 `@tool(...)` 装饰器执行 → 注册到 `registry` 全局工具表 → `server` 遍历 registry 注册到 MCP Server