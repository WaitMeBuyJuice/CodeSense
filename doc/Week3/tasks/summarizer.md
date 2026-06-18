# 任务列表 — summarizer

## 模块说明
新建 `src/codesense_v1/summarizer.py`，协调 Data Layer + LLM + Cache 生成摘要。

---

- [x] 任务ID: SUM-1 — 实现 `summarizer.py` 及其单元测试
  - 输入: `doc/Week3/design/summarizer.md`
  - 输出:
    - `src/codesense_v1/summarizer.py`
    - `tests/test_summarizer.py`
  - 验收标准:
    - `project_map_summary`：缓存命中时不调用 LLM（mock llm.call_llm 未被 call）
    - `project_map_summary`：缓存失效时调用 LLM，写入缓存，返回 LLM 结果
    - `module_summary`：传入不存在目录 → 抛 `InvalidArgumentError`
    - `module_summary`：传入无 `__init__.py` 的目录 → 抛 `InvalidArgumentError`
    - `module_summary`：缓存命中时不调用 LLM
    - `module_summary`：缓存失效时调用 LLM，写入缓存，更新 meta.json
    - DB 不存在时 → 抛 `FileNotFoundError`（由 CodeGraphDB 触发）
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过（使用 mock DB，不依赖真实 CodeGraph DB）
  - 依赖: LLM-1、CACHE-1

---

## 缺陷记录
