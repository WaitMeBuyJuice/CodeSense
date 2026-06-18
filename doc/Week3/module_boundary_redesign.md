# 模块边界重定义：单文件模块支持

> 本文件记录「多粒度 explore」Stretch Goal 的前期讨论和设计决策。
> 新对话先读 `doc/Week3/project_overview_for_qa.md` 建立项目背景，再读本文件。

---

## 1. 问题背景

当前 `explore_module` 模块边界 = 含 `__init__.py` 的目录（Python 包）。这导致 `src/codesense_v1/` 下的单文件（`llm.py`、`summarizer.py`、`cache.py`、`server.py`、`registry.py`、`schemas.py`、`errors.py`）无法被单独探索——它们的信息被聚合到父包 `src/codesense_v1` 的摘要中，AI 无法按需深入了解单个文件模块。

## 2. 现有模块定义的两层

| 层 | 位置 | 定义方式 |
|---|---|---|
| Data 层 | `data/modules.py:94-113` `_package_id()` | Python 文件 → dotted package ID（如 `codesense_v1`） |
| Tool 层 | `summarizer.py:60-66` + `explore_module.py:36-42` | 模块 = 含 `__init__.py` 的目录 |

两层粒度已不一致：Data 层把 `llm.py` 归属到 `codesense_v1`，Tool 层不认单文件。

## 3. 子模块判断标准

> **如果文件 A 没了、文件 BCD 的职责描述都要改，它们就不该拆成独立子模块。**

满足此标准的反例——`data/` 包下 4 个文件：

| 文件 | 职责 | 关系 |
|------|------|------|
| `db.py` | SQLite 只读封装 | 上游数据源 |
| `files.py` | 文件列表 + 目录树 | 依赖 db.py |
| `modules.py` | 模块定义 + 依赖边提取 | 依赖 db.py |
| `aggregate.py` | 目录级聚合 | 依赖 modules.py |

它们是一条数据处理流水线的步骤，**不应拆成子模块**。

满足此标准的正例——`src/codesense_v1/` 下单文件：

| 文件 | 核心职责 | 独立性验证 |
|------|----------|-----------|
| `llm.py` | OpenAI API 调用封装 | 换 provider 不影响其他模块职责描述 |
| `cache.py` | `.codesense/` 读写 + DB hash | 换存储方式不影响其他模块职责描述 |
| `summarizer.py` | 协调 Data + Cache + LLM | 调用的三个模块各自独立 |
| `server.py` | MCP Server 启动 + 回调绑定 | 换框架入口不影响其他模块 |
| `registry.py` | Tool 注册/分发 + jsonschema 校验 | 换注册机制不影响 Tool 实现 |
| `schemas.py` | JSON Schema 常量 | 常量换位置定义即可 |
| `errors.py` | 错误类型体系 | 换错误基类即可 |

**结论：这 7 个单文件功能独立，应各自成为可探索的子模块。**

## 4. 选定方案：重构为子目录

将单文件模块各自挪入子目录，使每个模块有独立的 `__init__.py`：

```
src/codesense_v1/
├── __init__.py
├── llm/
│   └── __init__.py          ← 原 llm.py 内容
├── cache/
│   └── __init__.py          ← 原 cache.py 内容
├── summarizer/
│   └── __init__.py          ← 原 summarizer.py 内容
├── server/
│   └── __init__.py          ← 原 server.py 内容
├── registry/
│   └── __init__.py          ← 原 registry.py 内容
├── schemas/
│   └── __init__.py          ← 原 schemas.py 内容
├── errors/
│   └── __init__.py          ← 原 errors.py 内容
├── data/                    ← 保持不变（叶子模块）
│   ├── __init__.py
│   ├── db.py
│   ├── files.py
│   ├── modules.py
│   └── aggregate.py
├── tools/                   ← 保持不变
│   ├── __init__.py
│   ├── add.py
│   └── explore_module.py
└── resources/               ← 保持不变
    ├── __init__.py
    └── project_map.py
```

### 优势

1. **explore_module 无需改边界判断逻辑**：仍然用 `__init__.py` 检测，7 个新子目录自然被识别为模块
2. **project_map 模块列表自动变细**：Data 层 `_package_id()` 会为每个子目录生成独立 `package_id`
3. **符合 Python 社区惯例**：子包是标准做法
4. **import 路径向后兼容**：`from codesense_v1.llm import call_llm` 仍然有效（`llm/__init__.py` 导出）

### 影响

1. 所有 import 语句需要更新（如 `from codesense_v1 import llm` → `from codesense_v1.llm import call_llm`，实际取决于 `__init__.py` 如何重新导出）
2. 测试文件的 import 路径需同步更新
3. `pyproject.toml` 的包发现可能需要调整

## 5. 待讨论的开放问题

### 5.1 子模块粒度标准

> 目录含 `__init__.py` 且包含 >=2 个子目录（各有 `__init__.py`）→ 有子模块；否则为叶子模块。

`src/codesense_v1/` → 有 `data/`、`tools/`、`resources/` + 7 个新子模块 → 有子模块。
`src/codesense_v1/data/` → 无子目录包 → 叶子。

### 5.2 project_map 粒度控制

project_map 是否展示所有层级？建议仍只展示顶层，子模块信息通过 `explore_module` 按需获取，保持「全局鸟瞰 → 按需深入」分工。

### 5.3 递归深度控制

`explore_module` 是否加 `max_depth` 参数？默认 `max_depth=1`（只展开一级子模块），避免深嵌套项目 token 爆炸。

### 5.4 子模块间依赖呈现

如 `summarizer.py` 依赖 `llm.py` + `cache.py` + Data 层，子模块化后这些成为跨子模块依赖。摘要中「依赖的模块」应列出这些新增的模块间依赖。

## 6. 实施步骤（建议）

1. 创建新分支
2. 逐个文件迁移：`llm.py` → `llm/__init__.py`，同步更新所有 import 引用
3. 更新测试文件 import
4. 运行 `mypy --strict` + `ruff check` + `pytest` 确保零错误
5. 重新生成 `.codegraph/codegraph.db`（`codegraph init -i`）
6. 验证 `project_map` 和 `explore_module` 对新子模块的输出质量
