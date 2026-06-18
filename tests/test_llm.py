"""Tests for codesense_v1.llm."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from codesense_v1.errors import LLMError
from codesense_v1.llm import call_llm


def _make_response(content: str | None) -> MagicMock:
    """Build a fake chat completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture()
def mock_openai() -> Any:
    """Patch AsyncOpenAI so no real HTTP calls are made."""
    with patch("codesense_v1.llm.llm.openai.AsyncOpenAI") as cls_mock:
        yield cls_mock


# ---- success paths ----------------------------------------------------------


async def test_call_llm_success(mock_openai: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    instance = mock_openai.return_value
    instance.chat.completions.create = AsyncMock(return_value=_make_response("hello"))
    result = await call_llm("prompt")
    assert result == "hello"


async def test_call_llm_strips_whitespace(
    mock_openai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    instance = mock_openai.return_value
    instance.chat.completions.create = AsyncMock(return_value=_make_response("  hi  \n"))
    result = await call_llm("prompt")
    assert result == "hi"


async def test_call_llm_uses_env_model(
    mock_openai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    monkeypatch.setenv("CODESENSE_LLM_MODEL", "my-model")
    instance = mock_openai.return_value
    instance.chat.completions.create = AsyncMock(return_value=_make_response("ok"))
    await call_llm("p")
    _, kwargs = instance.chat.completions.create.call_args
    assert kwargs.get("model") == "my-model" or instance.chat.completions.create.call_args[0][0] == "my-model"  # noqa: E501
    # More robust: check via call_args
    call_kwargs = instance.chat.completions.create.call_args
    assert call_kwargs.kwargs.get("model") == "my-model" or call_kwargs.args[0] == "my-model"


async def test_call_llm_uses_env_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    monkeypatch.setenv("CODESENSE_LLM_BASE_URL", "https://custom.url/v1")
    with patch("codesense_v1.llm.llm.openai.AsyncOpenAI") as cls_mock:
        instance = cls_mock.return_value
        instance.chat.completions.create = AsyncMock(return_value=_make_response("ok"))
        await call_llm("p")
        _, kwargs = cls_mock.call_args
        assert kwargs.get("base_url") == "https://custom.url/v1"


# ---- error paths ------------------------------------------------------------


async def test_call_llm_empty_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "")
    with pytest.raises(LLMError, match="未设置"):
        await call_llm("p")


async def test_call_llm_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODESENSE_LLM_API_KEY", raising=False)
    with pytest.raises(LLMError, match="未设置"):
        await call_llm("p")


async def test_call_llm_none_content(
    mock_openai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    instance = mock_openai.return_value
    instance.chat.completions.create = AsyncMock(return_value=_make_response(None))
    with pytest.raises(LLMError, match="空内容"):
        await call_llm("p")


async def test_call_llm_empty_content(
    mock_openai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    instance = mock_openai.return_value
    instance.chat.completions.create = AsyncMock(return_value=_make_response(""))
    with pytest.raises(LLMError, match="空内容"):
        await call_llm("p")


async def test_call_llm_api_error(
    mock_openai: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODESENSE_LLM_API_KEY", "test-key")
    instance = mock_openai.return_value
    instance.chat.completions.create = AsyncMock(
        side_effect=openai.APIConnectionError(request=MagicMock())
    )
    with pytest.raises(LLMError, match="API 调用失败"):
        await call_llm("p")
