---
module_id: errors
architectural_role: 错误类型体系
entity_names:
  constants:
    - name: ToolError
      source: src/codesense_v1/errors.py:1
      value: '异常类（基类）— Exception 子类，__init__(message: str)，message property 返回 str'
    - name: ValidationError
      source: src/codesense_v1/errors.py:13
      value: '异常类 — ToolError 子类，JSON Schema 校验失败时由 registry 抛'
    - name: InvalidArgumentError
      source: src/codesense_v1/errors.py:17
      value: '异常类 — ToolError 子类，业务级非法参数（schema 通过但语义非法，如 NaN/Infinity/溢出），工具内部抛'
    - name: LLMError
      source: src/codesense_v1/errors.py:22
      value: '异常类 — ToolError 子类，LLM API 调用失败（网络错误/超时/非 200/空内容），llm 调用层抛'
retrieval_hints:
  - 新增工具错误类型必须继承 ToolError 并放 errors.py，不可在 tools 层自定义异常（架构归属：错误类型体系集中维护）
  - ValidationError 专属 registry 校验阶段，工具内部严禁 raise ValidationError（架构归属：错误职责边界）
  - registry.dispatch 捕获 ToolError 转 isError=true，未知异常兜底转"内部错误：<ExcType>: <e>"（架构归属：错误兜底约定）
  - Resource 类工具（project_map）错误返回 Markdown 字符串不抛异常，与 Tool 类工具约定不同（架构归属：错误返回约定）
  - errors 是 leaf 模块零内部依赖，是依赖图叶子节点（架构归属：依赖方向）
  - message 文案须含字段名与原因，不得携带敏感信息（路径/堆栈/内部对象 repr）（架构归属：错误文案规范）
---

## 对外接口

```python
class ToolError(Exception):
    """工具领域异常基类。所有可预期的业务/校验错误都应继承自此类。"""
    def __init__(self, message: str) -> None: ...
    @property
    def message(self) -> str: ...

class ValidationError(ToolError):
    """JSON Schema 校验失败时抛出。由 registry 在调用 handler 前抛出。"""

class InvalidArgumentError(ToolError):
    """业务级非法参数（schema 校验通过但语义非法），如 NaN / Infinity / 溢出。由工具实现内部抛出。"""

class LLMError(ToolError):
    """LLM API 调用失败（网络错误、超时、非 200 响应、返回空内容等）。由 llm.py 抛出，经 registry 转为 isError=true 响应。"""
```

类型注解要点：构造参数 `message: str` 必填；`message` property 返回字符串，等价于 `str(exc)`；不引入额外字段（无错误码、无详情 dict，保持 MVP 最小）。

## 跨模块依赖

### 外部依赖（errors → 外部）

| 依赖 | 用途 |
|------|------|
| Python 内置 `Exception` | 基类继承 |

无内部依赖（leaf）。

### 反向调用方（谁 import errors，extracted 自源码 import）

| 调用方 | import 的符号 | 用途 |
|--------|--------------|------|
| `registry/registry.py` | `ToolError` | `except ToolError as e` 统一捕获，读 `e.message` 写入 `TextContent.text` |
| `tools/explore_module.py` | `InvalidArgumentError` | 模块名不存在/索引缺失时 raise |
| `tools/get_module_prompt.py` | `InvalidArgumentError` | 模块名不存在时 raise |
| `tools/save_module_summary.py` | `InvalidArgumentError` | 非法参数时 raise |
| `tools/save_project_map_segment.py` | `InvalidArgumentError` | 非法 segment_id/参数时 raise |
| `tools/submit_project_map.py` | `LLMError` | LLM 调用失败时 raise |
| `summarizer/summarizer.py` | `InvalidArgumentError` | 业务语义非法时 raise |

Codemap `get_dependencies({symbol_name:"ToolError"})` 确认继承关系：`LLMError` / `InvalidArgumentError` / `ValidationError` 均继承 `ToolError`。

## 典型调用链

1. **schema 校验失败路径**：Agent → `tools/call` → `registry.dispatch` → `jsonschema.validate` 失败 → `raise ValidationError("参数错误：缺失必填参数 'b'")` → registry `except ToolError` → `CallToolResult(isError=true, text=e.message)`。
2. **业务语义非法路径**：Agent → `tools/call` → `registry.dispatch`（schema 通过）→ tool handler 内部 `raise InvalidArgumentError("参数错误：'a' 不能为 NaN")` → registry `except ToolError` → `CallToolResult(isError=true)`。
3. **LLM 调用失败路径**：tool handler → `summarizer` → `llm.call_llm` 失败 → `raise LLMError("LLM 调用超时")` → 冒泡到 registry → `except ToolError` → `CallToolResult(isError=true)`。
4. **未知异常兜底路径**：tool handler 抛 `TypeError`（非 ToolError）→ registry 兜底捕获 → `CallToolResult(isError=true, text="内部错误：TypeError: ...")`。

## 实现约束清单

1. **ToolError 子类划分约定**：
   - `ValidationError`：JSON Schema 校验失败，**专属 registry 校验阶段**，工具内部严禁 raise。
   - `InvalidArgumentError`：schema 通过但语义非法（NaN/Infinity/溢出/模块不存在等），**工具实现内部抛**。
   - `LLMError`：LLM API 调用失败（网络/超时/非 200/空内容），**llm 调用层抛**（llm.py / summarizer / submit_project_map）。
   - 新增错误类型必须继承 `ToolError`，放 `errors.py`。

2. **registry 兜底捕获约定**：`registry.dispatch` 用 `except ToolError as e` 捕获所有 ToolError 子类，转 `CallToolResult(isError=true)`，text 取 `e.message`。未知异常（非 ToolError，如 TypeError/ZeroDivisionError）兜底转 `isError=true` 并附通用文案 `内部错误：<ExcType>: <e>`。进程不崩溃。

3. **Resource 类工具错误返回约定**：Resource 类工具（如 `resources/project_map.py`）错误时**返回包含错误描述的 Markdown 字符串，不抛异常**。这与 Tool 类工具（抛 ToolError 子类）约定不同。Resource 读失败不影响 MCP 协议层。

4. **message 文案规范**：
   - `ValidationError`：须含字段名与原因，如 `"参数错误：缺失必填参数 'b'"` / `"参数错误：'a' 期望 number，收到 str"`。
   - `InvalidArgumentError`：须含字段名与非法值原因，如 `"参数错误：'a' 不能为 NaN"` / `"参数错误：结果溢出"`。
   - 不得携带敏感信息（路径、堆栈、内部对象 repr）。

5. **不使用数字错误码**：MVP 仅用异常类型区分，无错误码字段。

6. **零内部依赖**：errors 不 import 任何其他内部模块（不 import tools/schemas/registry），是依赖图叶子节点。严禁反向依赖。

## 附：内置文档摘要

**D4 决策（Week2 design/overview.md §5）**：错误用异常类 + registry 统一捕获。理由：工具代码可读性最高（直接 raise），错误响应格式集中维护。否决备选：Result 元组冗长；工具自构响应分散。

**errors 接口与继承体系（Week2 design/errors.md §2-3）**：`ToolError`（基类，`__init__(message)`，`message` property）→ `ValidationError` / `InvalidArgumentError`。类型注解：`message: str` 必填，`message` property 等价 `str(exc)`，不引入额外字段。继承关系：`Exception → ToolError → {ValidationError, InvalidArgumentError}`（Week2 文档未含 LLMError，Week5 handoff 补充）。

**错误处理规范（Week5 handoff §5.4）**：
- 业务错误：抛 `ToolError` 子类（`ValidationError` / `InvalidArgumentError` / `LLMError`）→ registry 转 `isError=true` 的 `CallToolResult`。
- Resource 错误：返回包含错误描述的 Markdown 字符串，不抛异常（`resources/project_map.py` 模式）。
- 缓存错误：`read_*` 返回 None（视为 miss）；`write_*` 传播 OSError；`invalidate` 静默忽略。

**交互契约（Week2 design/errors.md §6）**：registry `except ToolError as e` 读 `e.message` 写入 `TextContent.text`；tools `raise InvalidArgumentError("...")`，严禁工具内部 raise `ValidationError`；errors 零内部依赖，是依赖图叶子节点。

> 📄 本节内容来源于仓库内置文档：`doc/Week2/design/errors.md`、`doc/Week2/design/overview.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）
