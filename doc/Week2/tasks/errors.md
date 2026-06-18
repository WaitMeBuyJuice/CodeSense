# 任务列表 - errors 模块

> 详细设计：`doc/design/errors.md`
> 目标文件：`src/codesense_v1/errors.py`

---

- [x] E-1: 实现 `src/codesense_v1/errors.py`
  - 输入: `doc/design/errors.md` §2、§3、§4
  - 输出: `src/codesense_v1/errors.py`
  - 验收标准:
    - 定义 `ToolError(Exception)`，`__init__(self, message: str) -> None`，`message` 属性返回字符串
    - 定义 `ValidationError(ToolError)`
    - 定义 `InvalidArgumentError(ToolError)`
    - 全部公开符号带完整类型注解
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - 零内部依赖（不 import 本项目其他模块）
  - 依赖: B-2
