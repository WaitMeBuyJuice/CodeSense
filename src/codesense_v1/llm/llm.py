"""OpenAI-compatible LLM client wrapper.

Configuration is read from environment variables at call time:

* ``CODESENSE_LLM_BASE_URL``          — default ``https://api.gemai.cc/v1``
* ``CODESENSE_LLM_API_KEY``           — required; empty string → ``LLMError``
* ``CODESENSE_LLM_MODEL``             — default ``deepseek-v4-flash``
* ``CODESENSE_LLM_BUDGET_TOKENS``     — thinking budget (int); for Kimi/Claude thinking models
* ``CODESENSE_LLM_REASONING_EFFORT``  — ``low``/``medium``/``high``; for OpenAI o-series
"""

from __future__ import annotations

import os

import openai

from codesense_v1.errors import LLMError

_DEFAULT_BASE_URL = "https://api.gemai.cc/v1"
_DEFAULT_MODEL = "deepseek-v4-flash"


async def call_llm(prompt: str) -> str:
    """Send *prompt* as a user message and return the response text.

    Raises:
        LLMError: on empty API key, API failure, or empty/null response.
    """
    base_url = os.environ.get("CODESENSE_LLM_BASE_URL", _DEFAULT_BASE_URL)
    api_key = os.environ.get("CODESENSE_LLM_API_KEY", "")
    model = os.environ.get("CODESENSE_LLM_MODEL", _DEFAULT_MODEL)
    budget_tokens = os.environ.get("CODESENSE_LLM_BUDGET_TOKENS")
    reasoning_effort = os.environ.get("CODESENSE_LLM_REASONING_EFFORT")

    if not api_key:
        raise LLMError("CODESENSE_LLM_API_KEY 未设置")

    client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    if budget_tokens:
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled", "budget_tokens": int(budget_tokens)}
        }

    try:
        response = await client.chat.completions.create(**kwargs)
    except openai.OpenAIError as exc:
        raise LLMError(f"API 调用失败：{exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise LLMError("LLM 返回空内容")
    return content.strip()
