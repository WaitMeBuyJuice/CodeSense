# 任务列表 - registry 模块

> 详细设计：`doc/design/registry.md`
> 目标文件：`src/codesense_v1/registry.py`、`tests/test_registry.py`

---

- [x] R-1: 实现 `src/codesense_v1/registry.py`
  - 输入: `doc/design/registry.md` §2~§5
  - 输出: `src/codesense_v1/registry.py`
  - 验收标准:
    - 定义 `ToolHandler = Callable[..., Union[str, Awaitable[str]]]`
    - 定义 `@dataclass(frozen=True) class ToolSpec`，字段 `name/description/input_schema/handler`
    - 定义模块级 `_REGISTRY: Final[dict[str, ToolSpec]] = {}`
    - 实现 `tool(name, description, input_schema)` 装饰器：
      - 重复名抛 `RuntimeError(f"tool '{name}' already registered")`
      - 返回原函数（不包装）
    - 实现 `list_tools() -> list[Tool]`：返回 `mcp.types.Tool` 列表
    - 实现 `async def dispatch(name, arguments) -> CallToolResult`：
      - 未知工具 → `isError=True`，文案 `"未知工具：'<name>'"`
      - 用 `jsonschema.Draft202012Validator` 校验，按 §4.3 表格翻译错误文案
      - handler 同步/异步均支持（用 `inspect.isawaitable`）
      - `ToolError` → 文案 = `e.message`
      - 其他异常 → 文案 = `"内部错误：<exc_type 名字>"`，不泄漏堆栈
      - 永不抛异常；任何路径 `len(result.content) >= 1`
    - 严禁 import `codesense_v1.tools` 或 `codesense_v1.schemas`
    - 全部公开符号带完整类型注解
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: E-1, B-1（依赖 mcp、jsonschema）
