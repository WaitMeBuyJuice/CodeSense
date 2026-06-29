---
module_id: errors
architectural_role: 错误类型体系
world_model_hints:
  - CodeSense 用异常类 + registry 统一捕获的模式处理工具错误（D4 决策），工具代码直接 raise，registry 兜底转 MCP isError 响应
  - 错误分两类：schema 校验失败（ValidationError，registry 抛）与业务语义非法（InvalidArgumentError，工具内部抛）；LLM 调用失败单独一类（LLMError）
  - errors 是 leaf 模块，零内部依赖，是依赖图叶子节点
upstream_modules:
  - registry
  - tools/explore_module
  - tools/get_module_prompt
  - tools/save_module_summary
  - tools/save_project_map_segment
  - tools/submit_project_map
  - summarizer
downstream_modules: []
---

## Files

- `src/codesense_v1/errors.py` — 单文件，4 个异常类

## 子文档速览

- `errors_core.md` — 对外接口、跨模块依赖、典型调用链、实现约束清单、内置文档摘要

## 模块概述

errors 模块集中定义 CodeSense 工具调用过程中的领域异常类。所有异常最终由 `registry.dispatch` 统一捕获并转换为 MCP `CallToolResult(isError=true)` 响应。本模块不负责异常→MCP 响应的格式化（由 registry 完成）、不负责日志、不含任何业务逻辑。

继承体系：
```
Exception
  └── ToolError              # 基类，__init__(message)，message property
        ├── ValidationError  # JSON Schema 校验失败（registry 抛）
        ├── InvalidArgumentError  # 业务语义非法（工具内部抛）
        └── LLMError         # LLM API 调用失败（llm 调用层抛）
```

## 架构简析

errors 体现 D4 决策（错误用异常类 + registry 统一捕获）：工具代码可读性最高（直接 raise），错误响应格式集中维护在 registry。三个子类按"谁抛"划分职责边界：

- `ValidationError`：专属 registry 校验阶段，工具内部**严禁** raise。
- `InvalidArgumentError`：工具实现内部抛（schema 通过但语义非法，如 NaN/Infinity/溢出）。
- `LLMError`：llm 调用层抛，registry 转 isError=true。

未列入 ToolError 体系的异常（TypeError/ZeroDivisionError 等）由 registry 兜底为通用错误响应（`内部错误：<ExcType>: <e>`）。

## 上下游关系

**上游（谁 import errors，extracted）**：

| 调用方 | import 的符号 |
|--------|--------------|
| `registry/registry.py` | `ToolError` |
| `tools/explore_module.py` | `InvalidArgumentError` |
| `tools/get_module_prompt.py` | `InvalidArgumentError` |
| `tools/save_module_summary.py` | `InvalidArgumentError` |
| `tools/save_project_map_segment.py` | `InvalidArgumentError` |
| `tools/submit_project_map.py` | `LLMError` |
| `summarizer/summarizer.py` | `InvalidArgumentError` |

**下游（errors 依赖）**：无（leaf，零内部依赖，仅继承 Python 内置 `Exception`）。
