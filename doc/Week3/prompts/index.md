# Week 3 Prompt 索引

## 执行顺序

### 第一批（可并行，无依赖）

| 任务 | Prompt 文件 | 修改文件 |
|------|------------|---------|
| ERR-W3-1 | `ERR-W3-1.md` | `src/codesense_v1/errors.py` |
| SCH-W3-1 | `SCH-W3-1.md` | `src/codesense_v1/schemas.py` |
| CACHE-1  | `CACHE-1.md`  | `src/codesense_v1/cache.py`、`tests/test_cache.py` |
| LLM-1    | `LLM-1.md`    | `src/codesense_v1/llm.py`、`tests/test_llm.py` |

> 注意：执行 LLM-1 前需先 `uv add openai` 添加依赖（仅需一次）。

### 第二批（依赖第一批）

| 任务 | Prompt 文件 | 依赖 | 修改文件 |
|------|------------|------|---------|
| SUM-1 | `SUM-1.md` | LLM-1、CACHE-1 | `src/codesense_v1/summarizer.py`、`tests/test_summarizer.py` |

### 第三批（依赖 SUM-1，RES-1 和 TOOL-EM-1 可并行）

| 任务 | Prompt 文件 | 依赖 | 修改文件 |
|------|------------|------|---------|
| RES-1     | `RES-1.md`     | SUM-1 | `src/codesense_v1/resources/__init__.py`、`resources/project_map.py`、`tests/test_resources_project_map.py` |
| TOOL-EM-1 | `TOOL-EM-1.md` | SUM-1、SCH-W3-1 | `src/codesense_v1/tools/explore_module.py`、`tools/__init__.py`、`tests/test_explore_module.py` |

### 第四批（依赖 RES-1）

| 任务 | Prompt 文件 | 依赖 | 修改文件 |
|------|------------|------|---------|
| RES-2 | `RES-2.md` | RES-1 | `src/codesense_v1/server.py` |

## 任务总数

8 个任务，预计新增 ~7 个源文件、~5 个测试文件。
