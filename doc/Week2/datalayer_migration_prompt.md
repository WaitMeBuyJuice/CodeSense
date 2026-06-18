# DataLayer 迁移提示词（给执行 Agent 使用）

> **任务**：把 `CodeSense_MCP_Server` 项目的 DataLayer 实现迁移到 `CodeSense_V1` 项目，
> 严格贴合 V1 工程规范。
>
> **执行者**：另一个 Coding Agent。
> **审阅者**：用户本人。
> **迁移完成的判定**：在 V1 项目中能产出与原项目一模一样的 4 个产物文件（`files_deps.json` / `module_deps.json` / `summary.txt` / `dep_facts.json`），且 `mypy strict` 与 `ruff` 零警告、单测全绿。

---

## 0. 路径速查

| 角色 | 路径 |
|------|------|
| 源项目（DataLayer 当前所在） | `E:\Python_Project\CodeSense\CodeSense_MCP_Server` |
| 目标项目（V1） | `E:\Python_Project\CodeSense_V1` |
| 源 DataLayer 包 | `CodeSense_MCP_Server\codesense\data\` |
| 源验证脚本 | `CodeSense_MCP_Server\scripts\validate_dir_deps.py` |
| 目标 DataLayer 包 | `CodeSense_V1\src\codesense_v1\data\` |
| 目标验证脚本 | `CodeSense_V1\scripts\validate_dir_deps.py` |
| 目标测试目录 | `CodeSense_V1\tests\` |
| 目标设计文档 | `CodeSense_V1\doc\design\data.md` + `CodeSense_V1\doc\tasks\data.md` |

---

## 1. 背景与上下文（你必须先读这些再动手）

### 1.1 V1 项目工程规范（必须遵守）

1. **`src/` layout**：所有源码在 `src/codesense_v1/` 下，`pyproject.toml` 已用 hatchling 配置。
2. **Python 3.14**：`requires-python = ">=3.14"`。**不要写 `from __future__ import annotations`**；类型注解直接用 `X | None`、`list[T]`、`dict[K, V]`，不用 `Optional`、`List`、`Dict`。
3. **mypy strict**：`pyproject.toml` 已开启 `[tool.mypy] strict = true`，所有函数必须有完整类型注解（含返回值），不能有 `Any` 漏网。
4. **ruff lint**：`[tool.ruff.lint] select = ["E", "F", "I", "B", "UP"]`，`line-length = 100`。
5. **分层依赖单向无环**：`data` 模块**严禁** import `registry` / `server` / `tools`，反向也不允许（除非未来某个 tool 主动 import data）。
6. **测试用 pytest + pytest-asyncio**：`tests/` 下，`conftest` 不需要自己加，`pythonpath = ["src"]` 已配。

### 1.2 V1 现有分层（已落地）

```
L1 入口    server.py     (mcp Server + stdio)
L2 注册    registry.py   (@tool 装饰器 + dispatch)
L3 工具    tools/        (每个 .py 一个工具)
L4 基础设施 schemas.py, errors.py
```

**本次迁移**：在 L4 同层新增 `data/` 子包。`data` 是纯数据加工层，不暴露 MCP 工具，不被 `tools/`、`registry/`、`server/` 引用。

### 1.3 源 DataLayer 结构（要原样迁移过去的东西）

```
codesense/data/
├── __init__.py     # 公开 API 统一导出
├── db.py           # CodeGraphDB + FileRow/NodeRow/EdgeRow（SQLite 只读边界）
├── files.py        # list_files / directory_tree / DirectoryNode
├── modules.py      # Module / ModuleEdge / list_modules / module_dependencies
│                   # to_file_dependency_dict / to_package_dependency_dict
│                   # EXTERNAL_PREFIX = "external::"
└── aggregate.py    # directory_dependencies / directory_edges
```

源 `scripts/validate_dir_deps.py` 包含：
- CLI 主流程（读 DB → 产出 `files_deps.json` / `module_deps.json` / `summary.txt`）
- `_compute_dep_facts()` 函数（图论预计算 → `dep_facts.json`）

---

## 2. 迁移目标产物（最终 V1 项目应出现的文件）

```
CodeSense_V1/
├── pyproject.toml                                ← 不动（除非需要加依赖；data 层只用标准库 sqlite3，无需加）
├── src/codesense_v1/
│   ├── data/                                     ← 新增
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── files.py
│   │   ├── modules.py
│   │   └── aggregate.py
│   └── (server.py / registry.py / ... 不动)
├── scripts/                                      ← 新增目录
│   └── validate_dir_deps.py
├── tests/
│   ├── test_data_db.py                           ← 新增
│   ├── test_data_modules.py                      ← 新增
│   └── test_data_aggregate.py                    ← 新增
└── doc/
    ├── design/
    │   └── data.md                               ← 新增
    └── tasks/
        └── data.md                               ← 新增
```

---

## 3. 迁移规则（逐项执行，不得遗漏）

### 3.1 包路径与 import 重写

| 源 import | 目标 import |
|-----------|------------|
| `from codesense.data.db import ...` | `from codesense_v1.data.db import ...` |
| `from codesense.data.modules import ...` | `from codesense_v1.data.modules import ...` |
| `from codesense.data import ...` | `from codesense_v1.data import ...` |

**全文搜索替换**：把所有 `codesense.data` 改成 `codesense_v1.data`，把所有 `codesense/data` （文档/注释中的路径引用）改成 `codesense_v1/data`。

### 3.2 Python 3.14 现代化重写（每个文件都要）

逐文件按以下规则改写：

1. **删除** `from __future__ import annotations`（V1 是 3.14，不需要）。
2. **类型别名替换**：
   - `from typing import Optional` → 删；用 `X | None`
   - `from typing import List, Dict, Tuple, Set` → 删；用 `list`、`dict`、`tuple`、`set` 小写
   - `from typing import Iterable, Iterator` → 改为 `from collections.abc import Iterable, Iterator`
3. **函数/方法注解必须完整**（含返回值），mypy strict 不放过缺失注解。
4. **`Optional[X]`** 全部改 `X | None`。
5. **`Union[A, B]`** 全部改 `A | B`。
6. **dataclass** 用法不变，`@dataclass(frozen=True)` 保持。
7. **保留所有 docstring**（原项目的中英文 docstring 都保留，质量很高，不要重写）。

### 3.3 ruff 风格

- `line-length = 100`：超过的换行。
- import 排序遵循 isort（ruff 的 `I` rule），分三组：stdlib / third-party / first-party。
- 不要保留无用 import；不要触发 `B` 系列警告（如 `B008` 函数默认参数为可变对象）。

### 3.4 mypy strict 要点

- `_REGISTRY` 这种全局可变字典在 V1 用 `Final[dict[...]]`，data 层若有类似全局字典也照办。
- 所有函数参数和返回值必须有注解。
- 不允许 `# type: ignore`，除非确实是上游库未标注（如 `mcp` 本身的某些类型），即便如此也要带具体原因注释。
- `_compute_dep_facts` 函数内的 `defaultdict` 在 mypy 下需要明确 value 类型，确保所有 type narrowing 通过。

### 3.5 验证脚本迁移

`scripts/validate_dir_deps.py` 复制到 `CodeSense_V1\scripts\validate_dir_deps.py`，规则：

1. **顶部 import** 改为 `from codesense_v1.data import ...`。
2. **`DEFAULT_PROJECT`** 路径计算：原来是 `Path(__file__).resolve().parent.parent.parent / "codegraph"`。在 V1 中保持同样语义（V1 项目根 → 上一级 → `codegraph`）。如果实际目录布局不一致，仍指向 `E:\Python_Project\CodeSense\codegraph`（用户的 codegraph 实仓库位置）。
3. **`--out` 默认值** 调整为 `Path(__file__).resolve().parent.parent / "out"`（V1 项目根的 `out/`）。
4. 其他逻辑完全保留，特别是 `_compute_dep_facts()` 函数（不准简化，不准合并、不准删字段）。
5. 类型注解补全：原脚本里 `_compute_dep_facts` 的 `edges` / `modules` 参数没标类型，迁移时补成 `list[ModuleEdge]` / `list[Module]`；返回 `dict[str, object]` 或更精确类型，保证 mypy strict 通过。

### 3.6 `__init__.py` 公开 API

`src/codesense_v1/data/__init__.py` 保持与源项目完全一致的导出符号（用户已有调用习惯）：

```python
"""CodeSense Data Layer — query CodeGraph's SQLite knowledge graph."""

from codesense_v1.data.aggregate import directory_dependencies
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.files import directory_tree, list_files
from codesense_v1.data.modules import (
    Module,
    ModuleEdge,
    list_modules,
    module_dependencies,
    to_file_dependency_dict,
    to_package_dependency_dict,
)

__all__ = [
    "CodeGraphDB",
    "Module",
    "ModuleEdge",
    "directory_dependencies",
    "directory_tree",
    "list_files",
    "list_modules",
    "module_dependencies",
    "to_file_dependency_dict",
    "to_package_dependency_dict",
]
```

（import 顺序按 isort 字母序排好，避免 ruff 报警）

---

## 4. 单测要求（必须新增）

V1 工程有完整测试传统，data 模块要补单测，覆盖**接口主路径 + 关键边界**。**不要追求 100% 覆盖率**，只覆盖以下关键点。

### 4.1 `tests/test_data_db.py`

- 用 `tempfile` + `sqlite3` 在 setup 阶段构造一个最小化的 `codegraph.db`，包含：
  - 2 个 file 行（`a.py`、`b.py`，都是 python）
  - 4 个 node（每文件 1 个 file 节点 + 1 个 import 节点）
  - 1 条 imports 边（a.py 的 import 节点 → b.py 的 file 节点）
- 测试用例：
  - `test_db_open_ok`：能成功打开，`stats()` 返回正确计数
  - `test_db_missing_raises`：传不存在的 project_root，`FileNotFoundError`
  - `test_iter_files`：迭代结果为 2 条 FileRow
  - `test_iter_nodes_with_kind_filter`：按 kind 过滤生效
  - `test_iter_edges`：迭代结果为 1 条 EdgeRow
  - `test_get_node`：能按 id 取到，不存在返回 None
  - `test_context_manager`：`with` 退出后再查询应抛错（连接已关闭）

### 4.2 `tests/test_data_modules.py`

- 复用 `test_data_db.py` 的最小 DB fixture（建议提到 `conftest.py` 里）。
- 测试用例：
  - `test_list_modules_python`：Python 项目，`package_id` 是 dotted name
  - `test_module_dependencies_internal`：构造一条内部 imports 边，能识别为 internal
  - `test_module_dependencies_external`：构造一条外部 imports（target 节点 kind=import），能识别为 external 且带原始名
  - `test_to_file_dependency_dict_sorted`：输出按 key 排序、value 内 imports/calls 排序
  - `test_to_package_dependency_dict_aggregates`：同包多文件聚合后不重复，且默认不含 self-loop
  - `test_resolve_id_python_init`：`a/b/__init__.py` → resolve_id = `a.b`
  - `test_resolve_id_ts`：`src/foo.ts` → resolve_id = `src/foo`
  - `test_external_prefix`：外部依赖在 dict 输出里带 `external::` 前缀

### 4.3 `tests/test_data_aggregate.py`

- 用手工构造的 `Module` 列表 + `ModuleEdge` 列表（不需要真 DB）。
- 测试用例：
  - `test_directory_dependencies_basic`：基本聚合
  - `test_directory_dependencies_max_depth`：`max_depth=1` 时聚合到顶层
  - `test_directory_dependencies_external_passthrough`：外部依赖带 `external::` 前缀通过
  - `test_directory_edges_flat_list`：返回 `[(src, tgt, kind), ...]` 形态

### 4.4 测试约束

- **不写集成测试**（验证脚本本身不在 pytest 范围）。
- 所有测试函数必须有 `-> None` 返回类型注解（mypy strict）。
- 使用 `pytest` 原生断言，不用 `unittest.TestCase`。

---

## 5. 文档要求

### 5.1 `doc/design/data.md`（详细设计，对齐 `doc/design/registry.md` 的结构）

模板：

```markdown
# 详细设计 - data 模块

> 路径：`src/codesense_v1/data/`
> 层级：L4 基础设施（与 schemas/errors 平级，纯数据加工层，不暴露 MCP 工具）
> 上游数据源：CodeGraph 索引数据库 `<project>/.codegraph/codegraph.db`（SQLite）

## 1. 模块功能说明
（参考源项目 codesense_项目解析.md 第二章，重写贴合 V1 语境）

## 2. 子模块职责
| 子模块 | 文件 | 职责 |
|---|---|---|
| db | data/db.py | SQLite 唯一边界，提供 CodeGraphDB + FileRow/NodeRow/EdgeRow |
| files | data/files.py | 文件平铺列表与层级目录树 |
| modules | data/modules.py | 文件级依赖边提取 + 文件/包级两种视图 |
| aggregate | data/aggregate.py | 按目录路径聚合（备用视图） |

## 3. 对外暴露接口
（列 __init__.py 中导出的全部符号，每个函数的签名和一句话说明）

## 4. 核心数据结构
- FileRow / NodeRow / EdgeRow（frozen dataclass）
- Module / ModuleEdge
- DirectoryNode

## 5. 与其他模块的交互契约
- 严禁被 registry / tools / server 引用（当前阶段是纯数据层）
- 仅依赖标准库 sqlite3 + dataclasses + pathlib + collections.abc.typing

## 6. 错误处理
- 文件不存在 → FileNotFoundError（来自 db.py 构造）
- 其他错误均向上抛，不做兜底（由调用方决定）

## 7. 关键设计决策
（搬运源项目 codesense_项目解析.md 第三章"关键设计与决策"表格）
```

### 5.2 `doc/tasks/data.md`（任务拆解，对齐 `doc/tasks/registry.md` 的结构）

模板：

```markdown
# 任务拆解 - data 模块

## T-D-1：迁移 db.py（SQLite 边界）
- 验收：CodeGraphDB 能 open 真实 codegraph.db；stats() 返回正确数；mypy strict 通过
- 测试：tests/test_data_db.py 全绿

## T-D-2：迁移 files.py
- 验收：list_files / directory_tree 输出与源项目一致

## T-D-3：迁移 modules.py（核心）
- 验收：list_modules / module_dependencies / 两种 view 函数全部输出与源项目一致
- 测试：tests/test_data_modules.py 全绿

## T-D-4：迁移 aggregate.py
- 验收：directory_dependencies / directory_edges 输出与源项目一致
- 测试：tests/test_data_aggregate.py 全绿

## T-D-5：迁移 scripts/validate_dir_deps.py
- 验收：跑 `python scripts\validate_dir_deps.py <real-project>` 能产出 4 个文件，
  内容与源项目 100% 字节级一致（顺序、JSON 缩进、键序均同）

## T-D-6：补单测 + 文档
- 单测：4.1~4.3 三个文件
- 文档：本任务文档 + design 文档

## T-D-7：质量门禁
- `uv run mypy src tests` 零错误
- `uv run ruff check src tests scripts` 零警告
- `uv run pytest` 全绿
```

---

## 6. 验收清单（迁移完成后逐项打勾）

执行 Agent 在迁移结束后必须自检以下项，每项都给出**实际命令输出**或**实际文件路径**作为证据：

- [ ] 1. `src/codesense_v1/data/` 下有 5 个文件，文件名与源项目一致。
- [ ] 2. `scripts/validate_dir_deps.py` 存在，能 import `codesense_v1.data` 而非 `codesense.data`。
- [ ] 3. 所有迁移后的 .py 文件均无 `from __future__ import annotations`。
- [ ] 4. 所有迁移后的 .py 文件均无 `typing.Optional` / `typing.List` / `typing.Dict` / `typing.Tuple` / `typing.Set` 残留。
- [ ] 5. `cd CodeSense_V1 && uv run mypy src tests scripts` 输出 0 errors。
- [ ] 6. `cd CodeSense_V1 && uv run ruff check src tests scripts` 输出 All checks passed。
- [ ] 7. `cd CodeSense_V1 && uv run pytest` 全部用例通过（含新增 3 个测试文件）。
- [ ] 8. 在 V1 上运行 `uv run python scripts/validate_dir_deps.py E:\Python_Project\CodeSense\CodeSense_MCP_Server`，产出文件与源项目 `out/CodeSense_MCP_Server/` 下 4 个文件**字节级一致**（用 `fc` 或 `Compare-Object` 或 sha256 校验）。
- [ ] 9. `doc/design/data.md` 与 `doc/tasks/data.md` 均存在且内容完整（不是占位符）。
- [ ] 10. 源项目 `CodeSense_MCP_Server` 完全不动（不删除、不修改任何文件）。

---

## 7. 严格禁令

执行迁移过程中，**严禁**做以下事情：

1. ❌ **不要修改源项目** `CodeSense_MCP_Server` 的任何文件（迁移是单向复制 + 重写，不是移动）。
2. ❌ **不要把 data 注册为 MCP 工具**（本次迁移不新增工具；Week 3 任务再做）。
3. ❌ **不要修改 V1 已有的** `server.py` / `registry.py` / `tools/` / `errors.py` / `schemas.py`（与 data 模块无关，本次不动）。
4. ❌ **不要修改 V1 的** `pyproject.toml`（data 层只用标准库，无新增依赖；如果你认为必须加，先停下来问用户）。
5. ❌ **不要"顺便重构"** data 模块的算法逻辑（如 `_resolve_internal_import` / `_compute_dep_facts`）。算法 1:1 复刻，只改 import 路径和类型注解风格。
6. ❌ **不要简化或合并产物**（4 个产物文件结构必须与源项目完全一致）。
7. ❌ **不要省略文档**（design 与 tasks 两份文档都要写完整）。
8. ❌ **不要跳过单测**（3 个测试文件必须落地且通过）。

---

## 8. 推荐执行顺序

1. **读上下文**：先读 `CodeSense_V1\doc\design\overview.md` / `registry.md` / `tools.md`、`pyproject.toml`、`src/codesense_v1/server.py` / `registry.py` 熟悉 V1 风格。
2. **读源码**：通读源项目 `codesense\data\*.py` 与 `scripts\validate_dir_deps.py`。
3. **创建包骨架**：先建 `src/codesense_v1/data/__init__.py`（占位）。
4. **逐文件迁移**：按 `db → files → modules → aggregate` 顺序复制重写，每写完一个跑一次 `mypy` 和 `ruff` 通过再继续。
5. **迁移脚本**：`scripts/validate_dir_deps.py` 复制重写。
6. **写单测**：3 个测试文件，跑 `pytest` 通过。
7. **写文档**：`doc/design/data.md` + `doc/tasks/data.md`。
8. **端到端验证**：跑验证脚本，对比 4 个产物字节一致。
9. **自检清单**：第 6 节 10 项全部打勾。
10. **汇报**：把第 6 节清单的逐项结果（含命令输出）作为最终交付，提交给用户审阅。

---

## 9. 沟通规则

- 迁移过程中**任何**与本提示词冲突的情况、任何拿不准的决策点，**立刻停下来问用户**，不要自行假设。
- 例如：发现源代码某段逻辑似乎有 bug、发现 V1 现有代码与 overview 文档冲突、发现产物字节对比有微小差异（如换行符）。
- 报告中文为主，命令/路径/代码片段保持原样。

---

## 10. 一句话目标

**把 DataLayer 干净地搬进 V1，让 V1 拥有从 CodeGraph SQLite 输出 4 份依赖产物的能力，且达到 V1 工程的全部质量标准，不破坏 V1 现有任何东西。**
