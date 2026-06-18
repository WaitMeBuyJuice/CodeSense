# 详细设计 - errors 模块

> 路径：`src/codesense_v1/errors.py`  
> 层级：L4 基础设施  
> 概要设计参考：`doc/design/overview.md` §2、§3.2、§4.3

---

## 1. 模块功能说明

集中定义本服务工具调用过程中可能抛出的领域异常类。所有异常最终由 `registry.dispatch` 统一捕获并转换为 MCP `CallToolResult(isError=true)` 响应。本模块不负责：
- 异常→MCP 响应的格式化（由 `registry` 完成）
- 日志输出
- 任何业务逻辑

---

## 2. 对外暴露的接口签名

```python
class ToolError(Exception):
    """工具领域异常基类。所有可预期的业务/校验错误都应继承自此类。"""

    def __init__(self, message: str) -> None: ...

    @property
    def message(self) -> str: ...


class ValidationError(ToolError):
    """JSON Schema 校验失败时抛出。由 registry 在调用 handler 前抛出。"""


class InvalidArgumentError(ToolError):
    """业务级非法参数（schema 校验通过但语义非法），如 NaN / Infinity / 溢出。
    由工具实现内部抛出。"""
```

类型注解要点：
- 构造参数 `message: str` 必填。
- `message` 属性返回字符串，等价于 `str(exc)`。
- 不引入额外字段（错误码、详情 dict 等暂不需要，保持 MVP 最小）。

---

## 3. 核心数据结构定义

无独立数据结构。仅利用 Python 内置 `Exception` 继承体系。

继承关系：
```
Exception
  └── ToolError
        ├── ValidationError
        └── InvalidArgumentError
```

---

## 4. 错误码与异常处理规范

- **不使用数字错误码**。MVP 仅用异常类型区分。
- `message` 文案规范（用于直接返回给 Agent）：
  - `ValidationError`：必须包含字段名与原因，例如 `"参数错误：缺失必填参数 'b'"` / `"参数错误：'a' 期望 number，收到 str"` / `"参数错误：不允许的多余参数 'c'"`。
  - `InvalidArgumentError`：必须包含字段名与非法值原因，例如 `"参数错误：'a' 不能为 NaN"` / `"参数错误：结果溢出"`。
- 异常**不得**携带敏感信息（路径、堆栈、内部对象 repr）。
- 未列入 `ToolError` 体系的异常（如 `TypeError`、`ZeroDivisionError`）由 `registry` 统一兜底为通用错误响应，不在本模块定义范畴。

---

## 5. 关键算法或业务逻辑说明

无算法。仅声明类与初始化。

---

## 6. 与其他模块的交互契约

| 调用方 | 用法 | 约束 |
|--------|------|------|
| `registry` | `except ToolError as e: ...`；读取 `e.message` 写入 `TextContent.text` | 不得 import `tools/*` 或 `schemas` |
| `tools/*` | `raise InvalidArgumentError("...")` | 严禁工具内部 raise `ValidationError`（专属 registry 校验阶段） |
| `schemas` | 不交互 | —— |
| `server` | 不直接交互 | —— |

依赖方向：本模块**零内部依赖**，是依赖图叶子节点。
