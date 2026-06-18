# 任务列表 — schemas（Week 3 扩展）

## 模块说明
扩展 `src/codesense_v1/schemas.py`，新增 `EXPLORE_MODULE_INPUT_SCHEMA`。

---

- [x] 任务ID: SCH-W3-1 — 新增 `EXPLORE_MODULE_INPUT_SCHEMA`
  - 输入: `doc/Week3/design/tools_explore_module.md`（schema 定义）、现有 `src/codesense_v1/schemas.py`
  - 输出: `src/codesense_v1/schemas.py`（新增常量）
  - 验收标准:
    - `EXPLORE_MODULE_INPUT_SCHEMA` 为 `Final[dict[str, object]]`，含 `module_path` 必填字段
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过
  - 依赖: 无

---

## 缺陷记录
