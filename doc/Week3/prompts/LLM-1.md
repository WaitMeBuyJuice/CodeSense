# Prompt — LLM-1：实现 `llm.py`

## 任务背景

Week 3 通过 OpenAI 兼容 API（中转网关）调用 LLM 生成架构摘要。
`llm.py` 是叶子模块，封装 API 调用细节，屏蔽 `openai` SDK，向上暴露单一 `call_llm(prompt)` 接口。

**前置条件**：`LLMError` 已在 `src/codesense_v1/errors.py` 中定义（ERR-W3-1 完成后）。

## 实现目标

新建 `src/codesense_v1/llm.py`，从环境变量读取配置，封装 `AsyncOpenAI` 客户端调用。
新建 `tests/test_llm.py` 用 mock 覆盖正常路径和异常路径（不发真实 API 请求）。

## 接口契约

```python
async def call_llm(prompt: str) -> str:
    """Send prompt as a user message and return the LLM response text.

    Configuration (read from environment at call time):
        CODESENSE_LLM_BASE_URL  (default: "https://api.gemai.cc/v1")
        CODESENSE_LLM_API_KEY   (required; empty string → LLMError)
        CODESENSE_LLM_MODEL     (default: "deepseek-v4-flash")

    Raises:
        LLMError: on empty API key, API failure, empty response, or any openai exception.
    """
```

### 内部实现要点

1. 在函数内部（而非模块顶层）读取环境变量，避免测试时环境变量设置困难。
2. API Key 为空字符串时，抛 `LLMError("CODESENSE_LLM_API_KEY 未设置")`。
3. 构造 `AsyncOpenAI(base_url=base_url, api_key=api_key)` 客户端（每次调用新建）。
4. 调用 `await client.chat.completions.create(model=model, messages=[{"role":"user","content":prompt}])`。
5. 取 `response.choices[0].message.content`；若为 `None` 或空字符串，抛 `LLMError("LLM 返回空内容")`。
6. 返回 `.strip()` 后的字符串。
7. 捕获所有 `openai.OpenAIError` 及其子类，包装为 `LLMError(f"API 调用失败：{e}")`。

## 需要实现的文件

- `src/codesense_v1/llm.py`
- `tests/test_llm.py`

## 测试用例要求

使用 `pytest-asyncio`（`asyncio_mode=auto`）和 `unittest.mock.AsyncMock` / `patch`，**不发真实 API 请求**。

| 测试用例 | 场景 |
|---------|------|
| `test_call_llm_success` | mock `AsyncOpenAI`，返回预期字符串 |
| `test_call_llm_strips_whitespace` | LLM 返回带前后空白的字符串 → 返回 stripped 结果 |
| `test_call_llm_empty_api_key` | 设置 `CODESENSE_LLM_API_KEY=""` → 抛 `LLMError` |
| `test_call_llm_missing_api_key` | 未设置 `CODESENSE_LLM_API_KEY` → 抛 `LLMError` |
| `test_call_llm_none_content` | mock 返回 `content=None` → 抛 `LLMError` |
| `test_call_llm_empty_content` | mock 返回 `content=""` → 抛 `LLMError` |
| `test_call_llm_api_error` | mock 抛 `openai.APIError` → 抛 `LLMError` |
| `test_call_llm_uses_env_model` | 设置 `CODESENSE_LLM_MODEL=test-model` → 调用时传该 model |
| `test_call_llm_uses_env_base_url` | 设置 `CODESENSE_LLM_BASE_URL` → client 使用该 URL |

> 提示：用 `monkeypatch.setenv` / `monkeypatch.delenv` 设置环境变量；用 `unittest.mock.patch` 或 `pytest-mock` 的 `mocker.patch` mock `AsyncOpenAI`。

## 验收标准

1. 所有上述测试用例通过
2. `uv run ruff check src/codesense_v1/llm.py tests/test_llm.py` 零警告
3. `uv run mypy --strict src/codesense_v1/llm.py tests/test_llm.py` 零错误
4. `uv run pytest -q` 全部通过

## 约束

- 只能创建/修改 `src/codesense_v1/llm.py` 和 `tests/test_llm.py`
- 不得修改其他任何文件
- 测试中禁止发真实 API 请求
- `openai` 包已在 `pyproject.toml` 中（若未添加，本 prompt 不覆盖，需先 `uv add openai`）
