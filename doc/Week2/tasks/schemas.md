# 任务列表 - schemas 模块

> 详细设计：`doc/design/schemas.md`
> 目标文件：`src/codesense_v1/schemas.py`

---

- [x] S-1: 实现 `src/codesense_v1/schemas.py`
  - 输入: `doc/design/schemas.md` §2、§3
  - 输出: `src/codesense_v1/schemas.py`
  - 验收标准:
    - 定义 `ADD_INPUT_SCHEMA: Final[dict]`，结构与 `doc/design/schemas.md` §2 完全一致
    - 包含字段 `type`、`properties`(a/b)、`required`(["a","b"])、`additionalProperties: False`
    - 使用 `from typing import Final` 标注
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - 零内部依赖
  - 依赖: B-2
