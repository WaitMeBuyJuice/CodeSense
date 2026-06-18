# 任务列表 - tools 模块（含 add 工具）

> 详细设计：`doc/design/tools.md`
> 目标文件：`src/codesense_v1/tools/add.py`、`src/codesense_v1/tools/__init__.py`、`tests/test_add.py`

---

- [x] T-1: 实现 `src/codesense_v1/tools/add.py`
  - 输入: `doc/design/tools.md` §2.2、§4、§5
  - 输出: `src/codesense_v1/tools/add.py`
  - 验收标准:
    - 从 `codesense_v1.errors` 导入 `InvalidArgumentError`
    - 从 `codesense_v1.registry` 导入 `tool`
    - 从 `codesense_v1.schemas` 导入 `ADD_INPUT_SCHEMA`
    - `@tool(name="add", description="计算两个数的和并返回字符串结果。", input_schema=ADD_INPUT_SCHEMA)`
    - 函数签名 `def add(a: float, b: float) -> str`
    - NaN/Infinity 自检按 §4 文案抛 `InvalidArgumentError`
    - 结果非有限抛 `InvalidArgumentError("参数错误：结果溢出或非有限数")`
    - 正常路径返回 `str(a + b)`
    - 不 raise `ValidationError`，不 import `server`
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: E-1, S-1, R-1

- [x] T-2: 实现 `src/codesense_v1/tools/__init__.py`
  - 输入: `doc/design/tools.md` §2.1
  - 输出: `src/codesense_v1/tools/__init__.py`
  - 验收标准:
    - 文件包含 `from . import add  # noqa: F401`
    - 声明 `__all__: list[str] = []`
    - `python -c "import codesense_v1.tools; from codesense_v1.registry import _REGISTRY; assert 'add' in _REGISTRY"` 成功
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: T-1
