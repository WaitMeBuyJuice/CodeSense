## 子模块概述
共享辅助子模块，提供项目根目录的三级回退解析。所有 tools 层工具函数首步均调用此处的 `resolve_project_root()`，解析失败时返回统一的错误引导文案。是 tools 层的基础设施，解耦了项目根探测逻辑与工具业务逻辑。

## 对外能力

- `resolve_project_root()`：异步，按优先级三级回退返回项目根 Path 或 None
  1. 环境变量 `CODESENSE_PROJECT_ROOT`（显式指定，最高优先级）
  2. MCP `roots/list`（IDE 工作区根，经 `request_ctx` 获取会话）
  3. 从 CWD 向上查找 `.codegraph/codegraph.db`（最多 10 层）
- `project_root_not_found_error()`：返回固定的中文错误引导文案，提示设置环境变量或运行 `codegraph init -i`
- `_root_from_mcp()` / `_root_from_cwd()`：内部实现，异常静默返回 None

## 跨模块依赖

- 下游：无（仅依赖标准库 os/pathlib/urllib）
- 上游：tools（被 explore_module / explore_submodule / project_map / save_* / submit_* 全部导入）

## 典型调用链

### 标准解析路径
`<任意工具函数>` → `resolve_project_root()` → 读 `CODESENSE_PROJECT_ROOT` env → 命中返回 / 未命中 → `_root_from_mcp()`（MCP 会话 roots/list）→ 命中返回 / 异常或未命中 → `_root_from_cwd()`（向上找 .codegraph/codegraph.db）→ 返回 Path 或 None

### 解析失败路径
`resolve_project_root()` 返回 None → 调用方 `return project_root_not_found_error()` → 返回错误引导文案给 Agent