## 模块边界规则

### 层次约束
- 依赖单向流向：`server` → `registry` → `tools` → `summarizer` / `cache` / `data`
- `cache` 和 `data` 是第 0 层基础模块，不依赖任何上层模块
- `tools` 层是上层协调者，可以调用 `cache`、`data`、`registry`、`summarizer`，但反向禁止

### 访问禁忌
- `cache` 模块禁止调用 `data`、`summarizer`、`tools`、`registry`、`server`
- `data` 模块禁止调用 `cache`、`summarizer`、`tools`、`registry`、`server`
- `summarizer` 禁止调用 `tools`、`registry`、`server`
- `registry` 禁止调用 `tools`、`summarizer`

### 职责边界
- `cache` 层：只负责 `.codesense/` 目录下文件的读/写/校验/失效，不做任何业务逻辑
- `data` 层：只做 CodeGraph 数据库查询与目录依赖聚合，不写任何缓存文件
- `summarizer` 层：只负责生成 Prompt 和渲染 Markdown，不直接注册 MCP 工具
- `registry` 层：只负责工具元数据管理和参数校验，不执行工具逻辑
- `tools` 层：MCP 工具的唯一实现层，负责协调各层完成工具请求
- `server` 层：只负责 stdio 服务器启动与 MCP 协议桥接

### 新增代码约束
- 新增 MCP 工具必须在 `registry` 注册元数据，在 `tools` 层实现逻辑
- 缓存文件结构变更需同步更新 `cache.py` 中的常量与对应 `read_*/write_*` 函数
- 所有 `read_*` 函数须在任何异常时返回 `None`（静默 miss），`write_*` 函数可传播 `OSError`
- 禁止在 `cache` 层之外直接操作 `.codesense/` 目录