# Prompt — RES-1：实现 `resources/project_map.py`

## 任务背景

`project_map` 是一个 MCP Resource，AI 连接 Server 时被动注入，无需主动调用。
`resources/project_map.py` 负责读取环境变量 `CODESENSE_PROJECT_ROOT`，调用 `summarizer.project_map_summary`，将所有错误转为 Markdown 格式返回（不使用 MCP 错误机制）。

**前置条件**：`summarizer.project_map_summary` 已实现（SUM-1）。

## 实现目标

新建 `src/codesense_v1/resources/__init__.py`（空文件）和 `src/codesense_v1/resources/project_map.py`。
新建 `tests/test_resources_project_map.py` 覆盖正常路径和各错误路径。

## 接口契约

```python
RESOURCE_URI: str = "codesense://project_map"
RESOURCE_NAME: str = "Project Architecture Map"
RESOURCE_DESCRIPTION: str = "项目整体架构概览（模块列表、依赖关系）"
RESOURCE_MIME_TYPE: str = "text/markdown"

async def read_project_map() -> str:
    """Return project map content as Markdown.

    Reads CODESENSE_PROJECT_ROOT from environment.
    On any error, returns a Markdown string describing the error (does NOT raise).
    """
```

### 错误 Markdown 格式

| 场景 | 返回的 Markdown |
|------|----------------|
| `CODESENSE_PROJECT_ROOT` 未设置 | 以 `# 错误` 开头，含"CODESENSE_PROJECT_ROOT 未设置"说明 |
| `FileNotFoundError` | 以 `# 错误` 开头，含"CodeGraph 数据库不存在"和运行 `codegraph init -i` 提示 |
| `LLMError` | 以 `# 错误` 开头，含"LLM 调用失败"和检查环境变量提示 |
| 其他 `Exception` | 以 `# 错误` 开头，含异常类型名和消息 |

## 需要实现的文件

- `src/codesense_v1/resources/__init__.py`（空文件，使其成为 Python 包）
- `src/codesense_v1/resources/project_map.py`
- `tests/test_resources_project_map.py`

## 测试用例要求

使用 `monkeypatch` 设置/删除环境变量，`unittest.mock.patch` mock `summarizer.project_map_summary`。

| 测试用例 | 场景 |
|---------|------|
| `test_read_project_map_success` | mock summarizer 返回 Markdown → 函数返回该 Markdown |
| `test_read_project_map_no_env` | `CODESENSE_PROJECT_ROOT` 未设置 → 返回含"未设置"的 Markdown |
| `test_read_project_map_file_not_found` | summarizer 抛 `FileNotFoundError` → 返回含"不存在"的 Markdown |
| `test_read_project_map_llm_error` | summarizer 抛 `LLMError` → 返回含"LLM 调用失败"的 Markdown |
| `test_read_project_map_unexpected_error` | summarizer 抛 `RuntimeError` → 返回含异常类型名的 Markdown |
| `test_constants_values` | `RESOURCE_URI == "codesense://project_map"`，`RESOURCE_MIME_TYPE == "text/markdown"` |

## 验收标准

1. 所有上述测试用例通过
2. `uv run ruff check src/codesense_v1/resources/ tests/test_resources_project_map.py` 零警告
3. `uv run mypy --strict src/codesense_v1/resources/ tests/test_resources_project_map.py` 零错误
4. `uv run pytest -q` 全部通过

## 约束

- 只能创建 `src/codesense_v1/resources/__init__.py`、`src/codesense_v1/resources/project_map.py`、`tests/test_resources_project_map.py`
- 不得修改其他任何文件
