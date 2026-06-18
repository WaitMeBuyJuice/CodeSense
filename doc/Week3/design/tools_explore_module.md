# 详细设计 — `tools/explore_module` 模块

> 对应文件：`src/codesense_v1/tools/explore_module.py`
> 层级：L3 工具层
> 依赖：`codesense_v1.registry`、`codesense_v1.schemas`、`codesense_v1.summarizer`、`codesense_v1.errors`、标准库

---

## 1. 模块功能说明

实现 MCP Tool `explore_module`。接收 `module_path` 参数（相对于 `CODESENSE_PROJECT_ROOT` 的目录路径），校验模块边界（`__init__.py` 存在），调用 `summarizer.module_summary` 获取 Markdown 摘要，遵循现有工具注册模式（`@tool` 装饰器）。

---

## 2. 对外暴露的接口签名

工具函数本身（通过 `@tool` 装饰器注册，不直接对外暴露 Python 接口）：

```python
@tool(
    name="explore_module",
    description="返回指定模块目录的架构理解：一句话描述、对外接口、内部子模块、依赖模块。"
                " module_path 为相对于项目根目录（CODESENSE_PROJECT_ROOT）的目录路径，"
                " 如 'src/auth'。",
    input_schema=EXPLORE_MODULE_INPUT_SCHEMA,
)
async def explore_module(module_path: str) -> str:
    """Raises: InvalidArgumentError, LLMError, FileNotFoundError (→ ToolError chain)."""
```

---

## 3. 核心数据结构定义

无自定义数据结构。

**`EXPLORE_MODULE_INPUT_SCHEMA`**（定义在 `schemas.py`）：

```python
EXPLORE_MODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_path": {
            "type": "string",
            "description": "相对于项目根目录的模块目录路径，如 'src/auth'",
        }
    },
    "required": ["module_path"],
    "additionalProperties": False,
}
```

---

## 4. 错误码与异常处理规范

遵循现有工具错误处理规范（`errors.py`），由 `registry.dispatch` 统一捕获并转为 `isError=true`：

| 场景 | 异常 | 文案 |
|------|------|------|
| `CODESENSE_PROJECT_ROOT` 未设置 | `InvalidArgumentError` | `"参数错误：环境变量 CODESENSE_PROJECT_ROOT 未设置"` |
| `module_path` 为空字符串 | `InvalidArgumentError` | `"参数错误：module_path 不能为空"` |
| 对应目录不存在 | `InvalidArgumentError` | `"参数错误：模块路径不存在: {module_path}"` |
| 目录存在但无 `__init__.py` | `InvalidArgumentError` | `"参数错误：路径 {module_path} 不是 Python 包（缺少 __init__.py）"` |
| LLM 调用失败 | `LLMError`（自动转 `ToolError`） | `"内部错误：LLMError — ..."` |
| DB 不存在 | `FileNotFoundError`（继承链不是 ToolError，需包装） | `"内部错误：FileNotFoundError — ..."` |

> `FileNotFoundError` 不是 `ToolError` 子类，需在工具内捕获并重新抛 `InvalidArgumentError` 或包装为通用错误。文案：`"内部错误：CodeGraph 数据库不存在，请先运行 codegraph init -i"`。

---

## 5. 关键算法或业务逻辑说明

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
    # LLMError 是 ToolError 子类，直接向上传播，registry 会处理
```

---

## 6. 与其他模块的交互契约

| 依赖 | 使用方式 |
|------|---------|
| `registry` | `@tool` 装饰器注册 |
| `schemas` | `EXPLORE_MODULE_INPUT_SCHEMA` 常量 |
| `summarizer` | `await summarizer.module_summary(project_root, module_path)` |
| `errors` | `InvalidArgumentError`、`LLMError` |

注册触发：`tools/__init__.py` 新增：
```python
from . import explore_module  # noqa: F401
```
