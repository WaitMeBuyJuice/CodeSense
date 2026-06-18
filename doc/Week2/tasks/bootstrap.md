# 任务列表 - bootstrap 模块

> 工程骨架：依赖声明、包初始化文件。
> 参考：`doc/stack.md`、`doc/design/overview.md` §6

---

- [x] B-1: 编写 `pyproject.toml`
  - 输入: `doc/stack.md`、`doc/design/overview.md` §6、`doc/design/server.md` §6（`[project.scripts]` 要求）
  - 输出: `pyproject.toml`
  - 验收标准:
    - 声明 `requires-python = ">=3.14"`
    - 声明依赖：`mcp`、`jsonschema`
    - 声明 dev 依赖：`pytest`、`pytest-asyncio`、`mypy`、`ruff`
    - 声明 `[project.scripts] codesense = "codesense_v1.server:main"`
    - 配置 `[tool.mypy]` strict 模式
    - 配置 `[tool.ruff]` 基础规则
    - 配置 `[tool.pytest.ini_options]` 包含 `asyncio_mode = "auto"` 与 `testpaths = ["tests"]`
    - 声明 `[tool.hatch.build.targets.wheel] packages = ["src/codesense_v1"]`（或等效 setuptools 配置）
    - `uv sync` 成功，无解析冲突
  - 依赖: 无

- [x] B-2: 创建包根 `src/codesense_v1/__init__.py`
  - 输入: `doc/design/overview.md` §6
  - 输出: `src/codesense_v1/__init__.py`
  - 验收标准:
    - 文件存在且为空（或仅含 `__version__ = "0.1.0"`，与 `pyproject.toml` 一致）
    - `python -c "import codesense_v1"` 成功
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: B-1

- [x] B-3: 创建测试包占位 `tests/__init__.py`
  - 输入: 无
  - 输出: `tests/__init__.py`
  - 验收标准:
    - 文件存在（空文件即可）
    - `uv run pytest tests --collect-only` 不报导入错误
  - 依赖: B-1
