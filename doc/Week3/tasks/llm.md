# 任务列表 — llm

## 模块说明
新建 `src/codesense_v1/llm.py`，封装 OpenAI 兼容 API 调用。

---

- [x] 任务ID: LLM-1 — 实现 `llm.py` 及其单元测试
  - 输入: `doc/Week3/design/llm.md`
  - 输出:
    - `src/codesense_v1/llm.py`
    - `tests/test_llm.py`
  - 验收标准:
    - `call_llm(prompt)` 正常路径：mock `AsyncOpenAI`，返回期望字符串
    - `call_llm(prompt)` 异常路径：API 返回错误 → 抛 `LLMError`；空内容 → 抛 `LLMError`；API Key 未设置 → 抛 `LLMError`
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过
  - 依赖: ERR-W3-1（需要 `LLMError` 定义）

---

## 缺陷记录
