"""Tests for codesense_v1.resources.project_map."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from codesense_v1.errors import LLMError
from codesense_v1.resources import project_map as pm


async def test_read_project_map_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", "/some/project")
    with patch(
        "codesense_v1.resources.project_map.summarizer.project_map_summary",
        new_callable=AsyncMock,
    ) as mock_sum:
        mock_sum.return_value = "# Architecture"
        result = await pm.read_project_map()
    assert result == "# Architecture"


async def test_read_project_map_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODESENSE_PROJECT_ROOT", raising=False)
    result = await pm.read_project_map()
    assert "CODESENSE_PROJECT_ROOT" in result
    assert "未设置" in result


async def test_read_project_map_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", "/some/project")
    with patch(
        "codesense_v1.resources.project_map.summarizer.project_map_summary",
        new_callable=AsyncMock,
    ) as mock_sum:
        mock_sum.side_effect = FileNotFoundError("db missing")
        result = await pm.read_project_map()
    assert "不存在" in result
    assert "codegraph init" in result


async def test_read_project_map_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", "/some/project")
    with patch(
        "codesense_v1.resources.project_map.summarizer.project_map_summary",
        new_callable=AsyncMock,
    ) as mock_sum:
        mock_sum.side_effect = LLMError("timeout")
        result = await pm.read_project_map()
    assert "LLM 调用失败" in result
    assert "CODESENSE_LLM_API_KEY" in result


async def test_read_project_map_unexpected_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODESENSE_PROJECT_ROOT", "/some/project")
    with patch(
        "codesense_v1.resources.project_map.summarizer.project_map_summary",
        new_callable=AsyncMock,
    ) as mock_sum:
        mock_sum.side_effect = RuntimeError("boom")
        result = await pm.read_project_map()
    assert "RuntimeError" in result


def test_constants_values() -> None:
    assert pm.RESOURCE_URI == "codesense://project_map"
    assert pm.RESOURCE_MIME_TYPE == "text/markdown"
    assert pm.RESOURCE_NAME
    assert pm.RESOURCE_DESCRIPTION
