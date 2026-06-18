# 任务列表 — errors（Week 3 扩展）

## 模块说明
扩展 `src/codesense_v1/errors.py`，新增 `LLMError` 异常类。

---

- [x] 任务ID: ERR-W3-1 — 新增 `LLMError` 异常类
  - 输入: `doc/Week3/design/llm.md`（错误规范）、现有 `src/codesense_v1/errors.py`
  - 输出: `src/codesense_v1/errors.py`（新增 `LLMError(ToolError)` 类）
  - 验收标准:
    - `LLMError` 是 `ToolError` 的子类
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - 现有 `tests/test_registry.py` 全部通过
  - 依赖: 无

---

## 缺陷记录
