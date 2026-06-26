---
module_id: errors
architectural_role: "横切错误域"
world_model_hints:
  - "被所有模块依赖的叶子层，定义统一异常层次"
upstream_modules:
  - module: summarizer
    confidence: extracted
  - module: tools
    confidence: extracted
  - module: registry
    confidence: extracted
downstream_modules: []
---

## Files

### 源代码路径
- `src/codesense_v1/errors.py`

### 知识库文档
- `.codemaker/codeindex/src/codesense_v1/errors/_overview.md`（本文件）
- `.codemaker/codeindex/src/codesense_v1/errors/errors_core.md`

### 符号索引
- 由 **Codemap MCP** 实时提供（`find_symbol` / `search_code` / `get_symbol_detail`）

## 子文档速览

| 子文档 | 覆盖内容 | 关键实体 |
|--------|---------|---------|
| `errors_core.md` | 异常类层次、错误分类体系 | ToolError, ValidationError, InvalidArgumentError, LLMError |

## 模块概述

本模块定义 CodeSense 的统一异常层次，使上层调用方能区分"可预期业务错误"与"不可预期内部错误"，前者转为用户友好消息，后者转为内部错误报告。

上游：所有业务模块（summarizer、tools）在参数校验失败或业务逻辑异常时抛出对应子类异常；registry 在 dispatch 时统一捕获 ToolError。

下游：无下游依赖，这是一个叶子模块。

## 架构简析

单文件模块，定义四层异常分类体系：ToolError（基类）→ ValidationError（Schema 层）/ InvalidArgumentError（语义层）/ LLMError（外部服务层）。通过 `message` property 定义隐式契约——所有子类必须传 `message: str` 给 `super().__init__`。

## 上下游关系
> `extracted` = 静态分析可信；`inferred` = Agent 推断待复核

- **上游**：summarizer（submit_project_map/get_module_prompt/save_module_summary 抛出 InvalidArgumentError）、tools（参数校验失败抛出异常）、registry（dispatch 捕获 ToolError 转为 MCP 错误响应）
- **下游**：无
