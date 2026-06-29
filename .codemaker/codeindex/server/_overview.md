---
module_id: server
architectural_role: "MCP 入口层"
world_model_hints:
  - "L1 入口层：构造 mcp Server、绑定 stdio 传输、把 list_tools/call_tool 协议回调委派给 registry"
upstream_modules: []
downstream_modules:
  - module: registry
    confidence: extracted
  - module: tools
    confidence: extracted
  - module: cache
    confidence: inferred
  - module: errors
    confidence: inferred
---

## Files
### 源代码路径
- `src/codesense_v1/server/server.py`（核心：build_server / run_stdio / main / _init_codesenseignore / SERVER_INSTRUCTIONS）
- `src/codesense_v1/server/__main__.py`（`python -m codesense_v1.server` 入口，调 main）
- `src/codesense_v1/server/__init__.py`（导出 SERVER_NAME/SERVER_VERSION/build_server/run_stdio/main）

### 知识库文档
- `.codemaker/codeindex/server/_overview.md`（本文件）
- `.codemaker/codeindex/server/server_core.md`

### 符号索引
- 由 Codemap MCP 实时提供（find_symbol / search_code / get_symbol_detail）

## 子文档速览
| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `server_core.md` | 对外接口、跨模块依赖、调用链、实现约束、内置文档摘要 | build_server, run_stdio, main, _init_codesenseignore, SERVER_INSTRUCTIONS, SERVER_NAME, SERVER_VERSION |

## 模块概述
CodeSense_V1 的进程入口与协议桥接层：构造官方 `mcp.server.Server` 实例，绑定 stdio 传输，把 `tools/list`、`tools/call` 协议回调委派给 registry 层。上游由 CodeMaker Agent 通过 stdio spawn 拉起本进程，生命周期跟随客户端。下游改动影响：server 回调签名变化会破坏 MCP 协议握手；`SERVER_INSTRUCTIONS` 措辞变化直接影响 Agent 的工具调用决策。

## 架构简析
**分层结构（单行）：** CodeMaker Agent ─stdio─► server(build_server 绑定回调) ─► registry(list_tools/dispatch) ─► tools handler

核心文件 `server.py` 三段式：
1. 常量区：`SERVER_NAME`/`SERVER_VERSION`/`SERVER_INSTRUCTIONS`（握手元数据 + Agent 用法引导）
2. `build_server()`：构造 Server，注册 `_list_tools`/`_call_tool` 两个闭包回调，返回未运行实例（便于测试注入 mock transport）
3. `run_stdio()`/`main()`/`_init_codesenseignore()`：传输启动 + 同步入口 + `.codesenseignore` 模板初始化

数据流：import 时 `import tools` 触发 `@tool` 注册（副作用）→ build_server 绑定回调 → stdio_server 建立传输 → server.run 阻塞 → 回调委派 registry。

状态机：无（无状态进程，每次 tools/call 独立）。

## 上下游关系
> extracted=静态可信；inferred=推断待复核

**上游（谁触发本模块）：**
- 无内部模块上游。外部触发方：CodeMaker Agent 通过 stdio spawn 拉起进程（`codesense` 命令 / `python -m codesense_v1.server`）。

**下游（本模块依赖）：**
| 下游模块 | 依赖原因 | confidence |
|---------|---------|-----------|
| `registry` | build_server 回调委派 `registry.list_tools()` / `await registry.dispatch()` | extracted |
| `tools` | `import tools as _tools`（noqa F401）仅触发 `@tool` 注册副作用，不调用任何符号 | extracted |
| `cache` | `_init_codesenseignore` 写 `.codesense/` 目录（与 cache 共用目录，非直接 import） | inferred |
| `errors` | 经 registry 间接依赖（registry import ToolError），server 自身不直接 import | inferred |
