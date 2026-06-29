## 模块边界规则

### 层次约束

- **依赖方向严格自上而下**：第2层（server/tools/tests）→ 第1层（registry/summarizer）→ 第0层（cache/data/errors）。反向依赖禁止。
- **第0层模块不可依赖上层**：`cache`、`data`、`errors` 不得 import registry、summarizer、server、tools 中的任何符号。
- **第1层模块不可依赖第2层**：`registry`、`summarizer` 不得 import server、tools 中的任何符号。
- **同层模块隔离**：同一层次内的模块应保持松耦合，禁止循环引用。`summarizer` ↔ `registry` 之间当前无直接静态依赖，若未来需要通信应通过上层编排（由 tools 桥接），不可直接互相 import。
- **server 仅为薄入口**：`server` 模块职责限定为：拼接 registry + 导入 tools 触发注册 + 构造 `mcp.Server` 实例并启动 stdio 传输。不得在 server 内实现业务逻辑、直接操作数据库或缓存。

### 访问禁忌

- **tools 不可直接访问 CodeGraphDB**：工具实现（`tools/` 下各模块）不得直接 `from codesense_v1.data.db import CodeGraphDB`。数据库访问应由 `summarizer` 或 `data` 层提供的封装函数完成；若 `project_map.py` 中已有 `CodeGraphDB` 引用则视为遗留技术债务，待重构。
- **tools 不可直接操作文件系统缓存**：工具不得直接调用 `cache.write_*` / `cache.read_*`。缓存读写由 `summarizer` 层编排。当前 `tools/project_map.py` 中存在与 cache 的直接耦合，后续应收敛到 summarizer。
- **交叉依赖的 data 子模块必须通过 data/__init__.py**：其他模块引用 data 层符号时，必须通过 `from codesense_v1.data import X`，禁止直接 `from codesense_v1.data.db import CodeGraphDB`（data 内部子模块间的交叉引用除外）。
- **禁止在非 server 模块中引用 mcp SDK**：只有 `server` 和 `registry` 模块允许 `import mcp`。tools、summarizer、data、cache 均不得直接依赖 `mcp` 包。
- **errors 为唯一异常层级**：所有业务/校验错误必须继承 `ToolError`（定义于 `codesense_v1.errors`）。禁止在 tools/summarizer 中抛出裸 `Exception` 或内置异常（`ValueError`、`RuntimeError` 等）直接暴露给上层。

### 职责边界

- **data 层**：纯数据访问。提供 CodeGraph SQLite 查询、目录树分析、拓扑排序、哈希计算、模块发现。不包含缓存逻辑、不生成 Markdown、不感知 MCP 协议。
- **cache 层**：纯缓存 I/O。提供 `.codesense/` 目录下 JSON/Markdown 文件的读写、校验（基于数据库哈希）、失效。不包含业务判断、不调用 data 层、不进行格式渲染。
- **summarizer 层**：协调 data + cache，生成面向 LLM 的 Markdown 提示词/摘要。所有 segment prompt 生成、模块摘要模板渲染、项目地图拼装逻辑集中于此。不可直接写入缓存（应通过 cache 层 write 函数）。
- **registry 层**：工具元数据中心。管理 `ToolSpec` 注册表、JSON Schema 校验、`tool` 装饰器、`dispatch` 分发。不包含任何业务逻辑或数据查询。
- **tools 层**：MCP 工具实现。每个模块对应一个 MCP tool，负责解析参数 → 调用 summarizer/data 获取数据 → 组装结果。不自行生成 Markdown、不做缓存有效性判断（应由 summarizer 提供的 is_auto_expire_enabled 等函数处理）。
- **server 层**：仅启动入口。`build_server()` 构造 Server 对象、注册 `list_tools`/`call_tool` handler，`main()`/`run_stdio()` 启动 asyncio 事件循环。不得包含工具实现或数据处理逻辑。
- **scripts 层**：开发者辅助脚本。依赖 data 层完成批量任务（如数据库导出）。不得被任何生产代码路径依赖。
- **tests 层**：测试代码。依赖 src/codesense_v1、data、registry。不得被任何生产代码 import。

### 新增代码约束

- **新增 MCP 工具**：在 `src/codesense_v1/tools/` 下新建模块，使用 `@tool` 装饰器注册；在 `tools/__init__.py` 中添加 `from . import new_tool  # noqa: F401` 以触发注册。
- **新增数据查询**：在 `src/codesense_v1/data/` 下新增函数/类，并在 `data/__init__.py` 中导出。如需跨 data 子模块调用，优先在 data 层内完成聚合。
- **新增缓存操作**：在 `src/codesense_v1/cache/cache.py` 中新增 `read_*`/`write_*` 函数，保持「读失败返回 None、写失败传播 OSError」的约定。
- **新增异常类型**：在 `src/codesense_v1/errors.py` 中新增 `ToolError` 子类，明确其抛出场景（校验层/业务层/LLM层）。
- **依赖限制**：新增代码必须遵循层次约束。如需跨层引入新依赖，必须先更新本文档的拓扑层次声明，并经架构评审确认不会引入循环依赖。
- **Python 版本**：目标 Python 3.14，允许使用 `from __future__ import annotations`、`Final` 等新特性。
- **包管理**：使用 uv + `pyproject.toml`，第三方依赖仅限 `mcp`、`jsonschema`、`pytest`（及其异步插件）。新增依赖需在 `pyproject.toml` 中声明。
- **暂不开放插件/扩展点**：当前 registry 的 `@tool` 装饰器和 ToolSpec 机制仅供内部使用，不对外暴露为稳定 API。新增模块如需注册自定义处理器应通过现有 tools 层模式实现。（待人工补充：未来若需支持第三方工具注册，需定义正式的插件接口协议）