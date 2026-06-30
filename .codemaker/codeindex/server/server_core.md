---
entity_names:
  constants:
    - name: SERVER_NAME
      value: "CodeSense"
      source: src/codesense_v1/server/server.py
    - name: SERVER_VERSION
      value: "0.1.0"
      source: src/codesense_v1/server/server.py
    - name: SERVER_INSTRUCTIONS
      value: "多段字符串常量：引导 Agent 优先用 CodeSense 工具理解架构，规定工具调用顺序 project_map→explore_module，说明与 grep/CodeGraph 分工，提示缓存未就绪与 _nonce 重复调用处理"
      source: src/codesense_v1/server/server.py
retrieval_hints:
  - "正向疑问句：MCP Server 是怎么启动的？build_server 做了什么？"
  - "正向疑问句：tools/list 和 tools/call 回调绑定在哪里？"
  - "正向疑问句：SERVER_INSTRUCTIONS 给 Agent 的工具调用顺序是什么？"
  - "⚠️ 反向排除句：本模块是 CodeSense_V1 的 MCP 入口层，不是 CodeGraph MCP Server（后者是独立进程 codegraph serve --mcp）"
  - "架构归属句：新增 MCP 工具回调绑定必须放在 server.py 的 build_server，新增工具实现放 tools/ 不放 server"
  - "架构归属句：stdio 传输启动逻辑在 run_stdio，同步入口在 main，.codesenseignore 模板初始化在 _init_codesenseignore"
  - "本模块也叫 L1 入口层 / server 层"
architectural_role: "MCP 入口层"
---

## 对外接口
本模块对外是 **MCP Server 实例 + SERVER_INSTRUCTIONS**，通过 stdio 暴露给 CodeMaker Agent。

| 接口 | 方向 | 关键说明 | 入口符号 |
|------|------|---------|---------|
| `build_server() -> Server` | 对内（测试/启动） | 构造已绑定回调的 mcp Server，返回未运行实例，便于测试注入 mock transport | `build_server` |
| `run_stdio() -> None` | 对内 | 启动 stdio 传输并阻塞运行至 stdin EOF | `run_stdio` |
| `main() -> None` | 对外（CLI） | 同步入口：`_init_codesenseignore()` + `asyncio.run(run_stdio())`，供 `codesense` 命令调用 | `main` |
| `SERVER_INSTRUCTIONS` | 对外（Agent 引导） | 握手时注入 Agent 上下文，规定工具调用顺序与分工 | 常量 |
| `tools/list` 回调 | 对外（MCP 协议） | `@server.list_tools()` → `registry.list_tools()` | `build_server._list_tools` |
| `tools/call` 回调 | 对外（MCP 协议） | `@server.call_tool(validate_input=False)` → `await registry.dispatch()` | `build_server._call_tool` |

## 跨模块依赖
### 外部依赖
| 依赖模块 | 引用原因 | 关键符号 | confidence |
|---------|---------|---------|-----------|
| `registry` | 回调委派 list_tools/dispatch | `registry.list_tools`, `registry.dispatch` | extracted |
| `tools` | import 触发 `@tool` 注册副作用（noqa F401，不调用符号） | `import tools as _tools` | extracted |
| `mcp.server` | 创建 Server、stdio_server | `Server`, `stdio_server` | extracted |
| `mcp.types` | 类型引用 | `CallToolResult`, `Tool` | extracted |

### 反向调用方
| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `__main__.py` | `python -m codesense_v1.server` 启动 | `main()` |
| 外部 CLI `codesense` | pyproject `[project.scripts]` 入口 | `main()` |

## 典型调用链
1. **启动链：** `codesense` 命令 / `python -m` → `main` ← 本模块入口 → `_init_codesenseignore` → `asyncio.run(run_stdio)` → `build_server` → `stdio_server` → `server.run`
2. **tools/list 链：** Agent tools/list → `build_server._list_tools` ← 本模块入口 → `registry.list_tools` ← 跨模块:registry
3. **tools/call 链：** Agent tools/call → `build_server._call_tool` ← 本模块入口 → `registry.dispatch` ← 跨模块:registry → jsonschema 校验 → tools handler

## 实现约束清单
### 必须定义的常量/枚举
| 标识符 | 值 | 所在文件 | 说明 |
|--------|-----|---------|------|
| `SERVER_NAME` | `"CodeSense"` | server.py | MCP 握手 name |
| `SERVER_VERSION` | `"0.1.0"` | server.py | MCP 握手 version |
| `SERVER_INSTRUCTIONS` | 多段字符串 | server.py | Agent 用法引导，注入握手 instructions |

### 必须实现的函数
| 函数名 | 所在文件 | 说明 |
|--------|---------|------|
| `build_server` | server.py | 构造 Server + 绑定两个回调，返回未运行实例 |
| `run_stdio` | server.py | stdio 传输启动，阻塞至 EOF |
| `main` | server.py | 同步入口，调 `_init_codesenseignore` + `asyncio.run` |
| `_init_codesenseignore` | server.py | 在 `.codesense/` 下创建 `.codesenseignore` 模板（若不存在） |

### 设计决策
| 决策点 | 选定方案 | 外选方案 | 选定理由 |
|--------|---------|---------|---------|
| 传输方式 | stdio + 单进程异步 | SSE/HTTP | 需求 FR-2；CodeMaker 默认拉起方式；SSE 需暴露端口超 MVP |
| 回调校验 | `@server.call_tool(validate_input=False)` | SDK 默认校验 | SDK 默认校验会拒绝自定义 schema，必须关闭；校验下沉到 registry |
| 工具注册触发 | `import tools as _tools`（noqa F401）副作用 | 手动注册/包扫描 | 装饰器自动注册，新增工具零侵入；手动易遗漏，包扫描难调试 |
| 日志输出 | 仅 stderr 保留通道，当前不写日志 | 写文件日志 | stdio 下 stdout 不可污染；无日志是需求明确项 |
| build_server 返回值 | 返回未运行 Server 实例 | 直接 run | 便于集成测试注入 mock transport |

## 附：内置文档摘要
> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/server.md`、`doc/Week2/design/overview.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）

**职责边界（server.md §1）：** 进程入口与协议桥接层。绝不出现业务逻辑、参数校验、错误文案构造、工具元数据组装。必须先 `import tools` 再 `build_server`，否则 list_tools 为空。

**回调签名（server.md §2）：** `list_tools() -> list[Tool]`、`call_tool(name, arguments) -> CallToolResult`。`SERVER_NAME`/`SERVER_VERSION` 显式类型注解用于握手元数据。

**错误处理（server.md §4）：** list_tools 回调直接返回 registry 结果（不抛）；call_tool 回调 `await registry.dispatch()`，registry 保证不抛。进程级：正常关闭 stdin EOF 退出码 0；不捕获 KeyboardInterrupt 便于调试。stdout 污染防护：严禁 `print()`、严禁 logging 输出 stdout。

**交互契约（server.md §6）：** server→tools 仅 import 触发副作用不调符号；server→registry 调 list_tools/dispatch；禁止 import errors/schemas/tools.add（保持入口纯净，依赖单向）。pyproject 必须声明 `[project.scripts] codesense = "codesense_v1.server:main"`。

**进程模型（overview.md §1.2）：** 单进程单线程异步（mcp SDK asyncio）；stdout 严格只出 JSON-RPC 帧。

**MCP SDK 陷阱（week5_handoff.md §5.3）：**
- `@server.call_tool` 必须加 `validate_input=False`（SDK 默认校验拒绝自定义 schema）
- `@server.list_tools()` 装饰器无类型注解需 `# type: ignore`（SDK 未导出 decorator 类型）
- `mcp` 版本锁定 1.27.2，升级可能破坏 SDK API

**SERVER_INSTRUCTIONS 演进（week5_handoff.md §2 Week4）：** Week4 新增该常量，内容含 CodeSense 与 CodeGraph 分工（语义层 vs 结构层）、工具调用顺序（project_map→explore_module）、与 grep/CodeGraph 分工、缓存未就绪引导、`_nonce` 重复调用处理。集成测试结论：project_map（被动注入）无论是否开 Skill 都被使用；explore_module（主动工具）高度依赖 Skill 引导。

> 📄 注：server.md 设计稿中 call_tool 返回 `result.content`（list[TextContent]），实际代码已演进为直接返回 `CallToolResult`（mcp SDK 较新版本接受），以源码为准。
