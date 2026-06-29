---
module_id: registry
architectural_role: "工具注册与分发层"
world_model_hints:
  - "L2 注册分发层：@tool 装饰器 import 时注册到全局 _REGISTRY，list_tools 输出元数据，dispatch 做 jsonschema 校验+调用+异常转 isError"
upstream_modules:
  - module: server
    confidence: extracted
downstream_modules:
  - module: errors
    confidence: extracted
  - module: tools
    confidence: inferred
---

## Files
### 源代码路径
- `src/codesense_v1/registry/registry.py`（核心：tool 装饰器 / ToolSpec / list_tools / dispatch / _translate_jsonschema_error / _error）
- `src/codesense_v1/registry/__init__.py`（导出 ToolHandler/ToolSpec/tool/list_tools/dispatch）

### 知识库文档
- `.codemaker/codeindex/registry/_overview.md`（本文件）
- `.codemaker/codeindex/registry/registry_core.md`

### 符号索引
- 由 Codemap MCP 实时提供（find_symbol / search_code / get_symbol_detail）

## 子文档速览
| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `registry_core.md` | 对外接口、跨模块依赖、调用链、实现约束、内置文档摘要 | tool, ToolSpec, list_tools, dispatch, _translate_jsonschema_error, _REGISTRY, ToolHandler |

## 模块概述
CodeSense_V1 的工具注册与分发层：用 `@tool(name,description,input_schema)` 装饰器在 import 时把工具注册到全局 `_REGISTRY`，`list_tools()` 输出 `mcp.types.Tool` 元数据，`dispatch()` 用 `jsonschema.Draft202012Validator` 校验参数后调 handler 并把异常统一转成 `isError=true` 的 `CallToolResult`。上游由 server 层的 `_list_tools`/`_call_tool` 回调触发。下游改动影响：dispatch 的校验/异常转换逻辑变化会影响所有工具的错误响应格式；`@tool` 装饰器签名变化影响所有工具注册。

## 架构简析
**分层结构（单行）：** server 回调 → registry.dispatch → jsonschema 校验 → tools handler → (ToolError/Exception) → registry 兜底转 CallToolResult

核心文件 `registry.py` 四段式：
1. 类型与数据结构：`ToolHandler` 类型别名、`ToolSpec` dataclass（frozen）、`_REGISTRY` 全局 dict
2. `tool()` 装饰器：import 时注册，重复注册抛 RuntimeError，原样返回 fn（不包装，便于单测）
3. `list_tools()`：遍历 `_REGISTRY` 输出 `mcp.types.Tool`
4. `dispatch()` + `_translate_jsonschema_error()` + `_error()`：校验→调用（同步/async 兼容）→异常分类转换

数据流：`@tool` 装饰器执行 → 写 `_REGISTRY[name]=ToolSpec` → list_tools 读 → dispatch 读+校验+调 handler。

状态机：`_REGISTRY` 是进程级单例状态，import 期填充，运行期只读。

## 上下游关系
> extracted=静态可信；inferred=推断待复核

**上游（谁触发本模块）：**
| 上游模块 | 触发场景 | confidence |
|---------|---------|-----------|
| `server` | `_list_tools`/`_call_tool` 回调调 list_tools/dispatch | extracted |
| `tools` | import 时执行 `@tool` 装饰器填充 `_REGISTRY` | extracted |

**下游（本模块依赖）：**
| 下游模块 | 依赖原因 | confidence |
|---------|---------|-----------|
| `errors` | `from codesense_v1.errors import ToolError`，dispatch 捕获 ToolError 转 isError | extracted |
| `tools` | dispatch 通过 `_REGISTRY` 间接调 tools handler（非直接 import，运行期反射调用） | inferred |
