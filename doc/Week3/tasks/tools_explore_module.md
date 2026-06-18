# 任务列表 — tools/explore_module

## 模块说明
新建 `src/codesense_v1/tools/explore_module.py`，实现 `explore_module` MCP Tool。

---

- [x] 任务ID: TOOL-EM-1 — 实现 `tools/explore_module.py` 及单元测试
  - 输入: `doc/Week3/design/tools_explore_module.md`、`doc/Week3/tasks/schemas.md`（SCH-W3-1 需先完成）
  - 输出:
    - `src/codesense_v1/tools/explore_module.py`
    - `src/codesense_v1/tools/__init__.py`（新增 import）
    - `tests/test_explore_module.py`
  - 验收标准:
    - `module_path` 为空 → `isError=true`，文案含"module_path 不能为空"
    - `CODESENSE_PROJECT_ROOT` 未设置 → `isError=true`，文案含"CODESENSE_PROJECT_ROOT"
    - `module_path` 对应目录不存在 → `isError=true`，文案含"模块路径不存在"
    - 目录存在但无 `__init__.py` → `isError=true`，文案含"不是 Python 包"
    - DB 不存在 → `isError=true`，文案含"CodeGraph 数据库不存在"
    - LLM 失败 → `isError=true`，文案含"LLMError"
    - 正常路径：mock summarizer，返回 Markdown 字符串，`isError=false`
    - 工具在 `registry.list_tools()` 中可见
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过
  - 依赖: SCH-W3-1、SUM-1

---

## 缺陷记录
