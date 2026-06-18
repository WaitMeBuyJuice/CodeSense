# Prompt — ERR-W3-1：新增 `LLMError` 异常类

## 任务背景

Week 3 新增 LLM 调用层，需要一个专属异常类 `LLMError` 表示 LLM API 调用失败。
现有 `errors.py` 中已有 `ToolError`（基类）、`ValidationError`、`InvalidArgumentError`。
`LLMError` 应继承 `ToolError`，使其能被 `registry.dispatch` 统一捕获并转为 `isError=true` 响应。

## 实现目标

在 `src/codesense_v1/errors.py` 末尾新增 `LLMError(ToolError)` 类，docstring 说明其用途。

## 接口契约

```python
class LLMError(ToolError):
    """LLM API 调用失败（网络错误、超时、非 200 响应、返回空内容等）。
    由 llm.py 抛出，经 registry 转为 isError=true 响应。"""
```

## 需要修改的文件

- `src/codesense_v1/errors.py`（仅追加，不修改现有代码）

## 测试文件

无需新增独立测试文件。验证方式：
- 运行 `uv run pytest -q` 确认全量测试通过（现有 57 个测试不受影响）

## 验收标准

1. `LLMError` 是 `ToolError` 的子类（`issubclass(LLMError, ToolError)` 为 `True`）
2. `LLMError` 的构造函数接受 `message: str`（继承自 `ToolError`，无需重写）
3. `uv run ruff check src/codesense_v1/errors.py` 零警告
4. `uv run mypy --strict src/codesense_v1/errors.py` 零错误
5. `uv run pytest -q` 全部通过

## 约束

- 严禁修改 `errors.py` 中现有的任何代码
- 不得修改其他任何文件
