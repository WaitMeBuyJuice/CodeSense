# Prompts 索引

> 每个 prompt 自包含，子 Agent 无需读取其他文档。
> 主 Agent 按下方顺序分配；遇阻塞停止上报。

---

## 执行顺序（拓扑序）

| # | Task ID | Prompt 文件 | 产出文件 | 依赖 |
|---|---------|-------------|----------|------|
| 1 | B-1 | `doc/prompts/B-1.md` | `pyproject.toml` | 无 |
| 2 | B-2 | `doc/prompts/B-2.md` | `src/codesense_v1/__init__.py` | B-1 |
| 3 | B-3 | `doc/prompts/B-3.md` | `tests/__init__.py` | B-1 |
| 4 | E-1 | `doc/prompts/E-1.md` | `src/codesense_v1/errors.py` | B-2 |
| 5 | S-1 | `doc/prompts/S-1.md` | `src/codesense_v1/schemas.py` | B-2 |
| 6 | R-1 | `doc/prompts/R-1.md` | `src/codesense_v1/registry.py` | E-1, B-1 |
| 7 | T-1 | `doc/prompts/T-1.md` | `src/codesense_v1/tools/add.py` | E-1, S-1, R-1 |
| 8 | T-2 | `doc/prompts/T-2.md` | `src/codesense_v1/tools/__init__.py` | T-1 |
| 9 | SV-1 | `doc/prompts/SV-1.md` | `src/codesense_v1/server.py` | R-1, T-2, B-1 |
| 10 | TS-1 | `doc/prompts/TS-1.md` | `tests/test_registry.py` | R-1, B-3 |
| 11 | TS-2 | `doc/prompts/TS-2.md` | `tests/test_add.py` | T-2, B-3 |
| 12 | TS-3 | `doc/prompts/TS-3.md` | `tests/test_mcp_integration.py` | SV-1, B-3 |

合计 12 个 prompt。

---

## Agent 执行模式

**主 Agent**：
- 持有并维护 `doc/tasks/progress.md`
- 按上表顺序与 `依赖` 字段调度子 Agent
- 子 Agent 完成后验证 pytest / mypy / ruff 三项结果
- 通过则勾选 `doc/tasks/<module>.md` 与 `progress.md`
- 失败将信息写入 `doc/tasks/<module>.md`「缺陷记录」区
- 阻塞中止上报

**子 Agent**：
- 仅读取分配的 `doc/prompts/<task-id>.md`
- 实现代码（或测试），不得改任务范围外的文件
- 自行运行 pytest / mypy --strict / ruff check，全部通过后返回
