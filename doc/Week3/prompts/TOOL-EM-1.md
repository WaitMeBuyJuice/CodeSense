# Prompt — TOOL-EM-1：实现 `tools/explore_module.py`

## 任务背景

`explore_module` 是 Week 3 的核心 MCP Tool，AI 主动调用以获取某模块的架构理解。
遵循现有工具注册模式（`@tool` 装饰器 + `schemas.py` 常量 + `tools/__init__.py` 导入）。

**前置条件**：
- `EXPLORE_MODULE_INPUT_SCHEMA` 已在 `schemas.py` 定义（SCH-W3-1）
- `summarizer.module_summary` 已实现（SUM-1）

## 实现目标

新建 `src/codesense_v1/tools/explore_module.py`，修改 `src/codesense_v1/tools/__init__.py` 添加导入。
新建 `tests/test_explore_module.py` 覆盖参数校验、错误路径、正常路径。

## 接口契约

```python
from codesense_v1.registry import tool
from codesense_v1.schemas import EXPLORE_MODULE_INPUT_SCHEMA

@tool(
    name="explore_module",
    description=(
        "返回指定模块目录的架构理解：一句话描述、对外接口、内部子模块、依赖模块。"
        " module_path 为相对于 CODESENSE_PROJECT_ROOT 环境变量所指项目根目录的目录路径，"
        " 如 'src/auth'。要求目录中存在 __init__.py（Python 包）。"
    ),
    input_schema=EXPLORE_MODULE_INPUT_SCHEMA,
)
async def explore_module(module_path: str) -> str:
    """Raises: InvalidArgumentError, LLMError (→ ToolError chain, handled by registry)."""
```

### 执行流程

```python
async def explore_module(module_path: str) -> str:
    # 1. 参数基础校验
    module_path = module_path.strip()
    if not module_path:
        raise InvalidArgumentError("参数错误：module_path 不能为空")

    # 2. 读取 project_root
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        raise InvalidArgumentError("参数错误：环境变量 CODESENSE_PROJECT_ROOT 未设置")
    project_root = Path(project_root_str)

    # 3. 校验目录存在
    module_dir = project_root / module_path
    if not module_dir.is_dir():
        raise InvalidArgumentError(f"参数错误：模块路径不存在: {module_path}")

    # 4. 校验 __init__.py（包边界）
    if not (module_dir / "__init__.py").exists():
        raise InvalidArgumentError(
            f"参数错误：路径 {module_path} 不是 Python 包（缺少 __init__.py）"
        )

    # 5. 调用 summarizer
    try:
        return await summarizer.module_summary(project_root, module_path)
    except FileNotFoundError as e:
        raise InvalidArgumentError(
            f"内部错误：CodeGraph 数据库不存在，请先运行 codegraph init -i。({e})"
        ) from e
    # LLMError 是 ToolError 子类，直接向上传播（registry 会捕获）
```

### `tools/__init__.py` 修改

在现有 `from . import add  # noqa: F401` 之后新增：
```python
from . import explore_module  # noqa: F401
```

## 需要实现/修改的文件

- `src/codesense_v1/tools/explore_module.py`（新建）
- `src/codesense_v1/tools/__init__.py`（新增一行 import）
- `tests/test_explore_module.py`（新建）

## 测试用例要求

使用 `monkeypatch` 设置环境变量，`tmp_path` 创建临时目录结构，`unittest.mock.patch` mock `summarizer.module_summary`。
测试通过 `registry.dispatch("explore_module", args)` 调用，验证 `isError` 字段和内容。

| 测试用例 | 场景 |
|---------|------|
| `test_explore_module_empty_path` | `module_path=""` → `isError=True`，内容含"不能为空" |
| `test_explore_module_no_env` | `CODESENSE_PROJECT_ROOT` 未设置 → `isError=True`，含"CODESENSE_PROJECT_ROOT" |
| `test_explore_module_dir_not_exist` | 路径不存在 → `isError=True`，含"模块路径不存在" |
| `test_explore_module_no_init_py` | 目录存在但无 `__init__.py` → `isError=True`，含"不是 Python 包" |
| `test_explore_module_db_not_found` | summarizer 抛 `FileNotFoundError` → `isError=True`，含"数据库不存在" |
| `test_explore_module_llm_error` | summarizer 抛 `LLMError("fail")` → `isError=True`，内容含错误信息 |
| `test_explore_module_success` | 正常路径：mock summarizer 返回 Markdown → `isError=False`，内容为该 Markdown |
| `test_explore_module_registered` | `registry.list_tools()` 中存在 name 为 "explore_module" 的工具 |

> 提示：创建 `__init__.py` 示例：`(tmp_path / module_path / "__init__.py").touch()`（需先 `mkdir(parents=True)`）。

## 验收标准

1. 所有上述测试用例通过
2. `uv run ruff check src/codesense_v1/tools/explore_module.py src/codesense_v1/tools/__init__.py tests/test_explore_module.py` 零警告
3. `uv run mypy --strict src/codesense_v1/tools/explore_module.py src/codesense_v1/tools/__init__.py tests/test_explore_module.py` 零错误
4. `uv run pytest -q` 全部通过（包含现有测试，无回归）

## 约束

- 只能创建/修改上述三个文件
- 不得修改其他任何文件
- 测试中不发真实 API 请求，不依赖真实 CodeGraph DB
