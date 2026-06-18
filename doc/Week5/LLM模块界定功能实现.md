# LLM 模块界定实现文档

> 任务：将 `explore_module` / `project_map` 从"基于 `__init__.py` 的 Python 包检测"改造为"基于 LLM 推断的语言无关模块界定"，使 CodeSense 能在任意语言项目（Python / TypeScript / Go / …）上工作。
> 
> 接手实现的对话请按本文档逐节执行，不确定的地方**必须问用户**，禁止自行猜测。

---

## 0. 关键决策汇总（2026-06-17 二次评审已定）

下列决策由用户在二次评审中确认，**实现时必须遵守**。原文档 §8.2 的开放问题已在此关闭，§4.1 / §3.2.1 / §3.2.2 / §5.2 等小节的方案以本节为准（如有冲突以本节为准）。

| #   | 决策点                         | 最终选择                                                                                                         |
| --- | --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| D1  | LLM 调用策略                    | **拆两次**：只让 LLM 输出 JSON 模块划分；Markdown 概览由代码模板渲染（不再调 LLM）                                                      |
| D2  | `modules_index.json` schema | LLM **只输出 `directories`**，`files` 由数据层从 `directories` 展开                                                     |
| D3  | `explore_module` 索引缺失       | **抛 `InvalidArgumentError`**，提示先调用 `project_map`；不再隐式触发 `project_map_summary`                                |
| D4  | `safe_key` 生成               | `hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]`；可读名存 JSON 内字段 `module_name`，由 `list_cached_modules` 反查 |
| D5  | `max_per_dir` 默认值           | **50**（覆盖原文档 §4.1 的建议 20）                                                                                    |
| D6  | 模块名查找归一化                    | trim + **大小写不敏感**（防 "缓存层 " / "Cache" / "cache" 输入失配）                                                         |
| D7  | 缓存一致性                       | `write_modules_index` 必须**同步清空 `modules/` 子缓存**（即使 db_hash 未变；LLM 输出非确定性，模块名漂移会让旧 module summary 成孤儿）        |
| D8  | `package_id` 字段             | **保留不删**，避免破坏 `tests/test_data_modules.py` 大面积；新代码不再读它                                                       |
| D9  | LLM JSON 解析二次失败             | **抛 `LLMError`**（实验阶段需要清晰反馈）                                                                                 |
| D10 | LLM 输出后处理校验                 | 解析 JSON 后必须跑：①`name` 唯一 ②`directories` 不重叠（A 含 `src/x`，B 不能含 `src/x/sub`）③ 至少一个模块。违反则 retry，二次失败抛 `LLMError` |

### 0.1 实现前置验证（开工前必须完成）

| #   | 任务                                                                                                                                          | 输出                                                                 |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| V1  | 在 codegraph-main 的 `.codegraph/codegraph.db` 上跑一次 `iter_nodes` / `iter_files`，确认 TS 项目的 `file_path` 是相对路径还是绝对、分隔符是否统一为 `/`，是否有 namespace 前缀 | 一段验证脚本输出 + 结论；如果格式不一致，`directory_symbols` / `_module_to_dir` 需相应处理 |
| V2  | grep 一遍 `.codemaker/skills/codesense-workflow/SKILL.md` 和 `src/codesense_v1/server/server.py` 的 Instructions 字符串里是否出现 `module_path` 字样      | 列出所有命中点，实现时同步改为 `module_name`                                      |

### 0.2 Markdown 模板规格（替代 §4.1 的"LLM 同时输出 Markdown"方案）

`project_map.md` 由代码渲染，模板字段全部来自 `modules_index.json` + `directory_dependencies`，不再调 LLM：

```
# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| <name> | <description> | <directories> |
...

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| <src_module> | <tgt_module> | imports / calls |
...
```

模块间依赖的推导：把每条 `directory_dependencies` 边的两端目录映射回所属模块（用 `directories` 前缀匹配），跨模块的边才入表，模块内自环忽略。

### 0.3 LLM Prompt（仅 JSON 输出版）

替代 §4.1 的 prompt：

```
# 项目模块划分请求

你是一位软件架构师。根据以下项目结构数据，请你：
1. 推断项目的逻辑模块划分（一个模块可对应一个目录、跨多目录、或一个目录的子集）
2. 为每个模块取一个有意义的名字（中文或英文均可）
3. 一句话描述该模块的核心职责

## 输入数据

### 目录结构（含每目录代表性符号，最多 50 个/目录）
<directory + symbols>

### 目录间依赖
<src_dir -> tgt_dir [imports/calls]>

## 输出格式（必须为 JSON，不要任何额外文字）

{
  "modules": [
    {
      "name": "...",
      "description": "...",
      "directories": ["<相对项目根的目录路径>", ...]
    }
  ]
}

约束：
- name 在 modules 列表中唯一
- directories 路径不能互相覆盖（A 含 src/x，B 不能含 src/x/sub）
- 所有非平凡目录必须被某个模块覆盖
- 不输出 Markdown、不输出代码块包裹、直接输出 JSON 对象
```

---

## 1. 背景与目标

### 1.1 当前问题

| 文件                                                | 问题代码                                           | 影响                             |
| ------------------------------------------------- | ---------------------------------------------- | ------------------------------ |
| `src/codesense_v1/tools/explore_module.py:43`     | `if not (module_dir / "__init__.py").exists()` | 非 Python 项目直接报错                |
| `src/codesense_v1/summarizer/summarizer.py:62-65` | 同样的 `__init__.py` 检查                           | 非 Python 项目无法生成 module summary |
| `src/codesense_v1/data/modules.py` 整体             | 用 `package_id` 做模块聚合（Python 包语义）               | TypeScript 项目的 package_id 不准   |
| `_build_module_prompt` 中"名称不以 `_` 开头"             | Python 私有约定                                    | TypeScript 用 `export`，此规则失效    |

### 1.2 目标

- `explore_module` 接受**模块名**（不再接受路径），由 LLM 在 `project_map` 阶段先界定模块
- 模块边界完全由 LLM 推断，不依赖任何语言级约定文件（`__init__.py` / `package.json` / `go.mod` 等）
- 数据层只做语言无关的目录级聚合（已有的 `aggregate.directory_dependencies` 是基础）
- 现有 111 个测试经过调整后**全部通过**，`mypy --strict` 零错误，`ruff check` 零警告

### 1.3 不在本任务范围内

- 不动 `cache.py` 的 lazy 失效机制（hash 不变命中、变了重生）
- 不动 `llm.py` 调用方式（仅改 prompt 内容）
- 不动 MCP Server / Resource 注册逻辑
- 不新增 MCP Tool / Resource

---

## 2. 总体设计

### 2.1 新数据流

```
[CodeGraph DB]
      │
      ▼
[Data 层：语言无关的目录级聚合]
      │  (directory_dependencies + 新增 directory_symbols)
      ▼
[Summarizer：构建 prompt → 调 LLM]
      │
      ├─→ project_map  → LLM 输出：Markdown 概览 + JSON 模块映射
      │                   缓存：project_map.md + modules_index.json
      │
      └─→ explore_module(module_name)
                │
                ├─ 读 modules_index.json
                ├─ 找到该模块对应的 files
                ├─ 构建 prompt → 调 LLM → 详细 Markdown
                └─ 缓存：modules/<safe_key>.json
```

### 2.2 关键决策

| 决策点               | 选择                         | 理由                                 |
| ----------------- | -------------------------- | ---------------------------------- |
| 模块边界判断            | LLM 推断                     | 用户与导师确认（详见 `doc/Week4/待确认.md` 议题3） |
| explore_module 入参 | 模块名（不是路径）                  | 用户决策                               |
| 模块名→文件映射          | project_map 一次性输出并缓存（方案 A） | 模块定义统一、token 节省、缓存复用               |
| 数据层粒度             | 目录级聚合，不喂原始 CodeGraph 数据    | 控制 token、降低噪声                      |

---

## 3. 具体修改

### 3.1 数据层：`src/codesense_v1/data/`

#### 3.1.1 新增函数 `directory_symbols`

**位置**：建议放在 `data/aggregate.py`，与 `directory_dependencies` 并列。

**签名**：

```python
def directory_symbols(
    db: CodeGraphDB,
    *,
    max_depth: int | None = None,
    kinds: tuple[str, ...] = ("function", "class", "method"),
    max_per_dir: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Return mapping of directory → list of symbols defined in that directory.

    Each symbol entry: {"name": str, "kind": str, "file": str}.
    Used by summarizer to give LLM enough info to describe each directory's role.
    """
```

**实现要点**：

- 遍历 `db.iter_nodes(kinds=kinds)`，按 `node.file_path` 取 dirname 聚合
- `max_depth` 与 `directory_dependencies` 语义一致
- `max_per_dir` 用于截断超大目录（避免 token 爆炸），默认 `None` 不截断
- **不做** `_` 前缀过滤（语言无关）

#### 3.1.2 `data/modules.py`

- **保持不变**。`Module` / `ModuleEdge` / `list_modules` / `module_dependencies` 仍然是文件级聚合，是上层目录聚合的输入
- `package_id` 字段保留，但 summarizer 不再使用它

> ⚠️ **不确定点**：是否要彻底删除 `package_id` 字段？  
> **建议**：保留不删，避免破坏 `tests/test_data_modules.py` 大面积。新代码不再读它即可。  
> **必须问用户**：如果你倾向彻底清理，告诉我。

---

### 3.2 Summarizer：`src/codesense_v1/summarizer/summarizer.py`

#### 3.2.1 `project_map_summary` 改造（按 D1 / D2 / D9 / D10 拆两次）

**新行为**：

1. 数据层准备：`directory_symbols`（max_per_dir=50）+ `directory_dependencies`
2. 构建 **JSON-only** prompt（见 §0.3），调 LLM
3. 解析 LLM 输出为 JSON：
   - 直接 `json.loads`；失败则尝试剥离可能的 ```json fence 后重试一次
   - 解析后跑后处理校验（D10）：`name` 唯一、`directories` 不重叠、至少一个模块
   - 校验失败 → 加入错误说明的 retry prompt 重试**一次**；二次失败抛 `LLMError`
4. 数据层把 `directories` 展开为 `files`（D2）：遍历 `db.iter_files()`，按 `directories` 前缀匹配
5. 写 `.codesense/modules_index.json`（含 `name` / `description` / `directories` / `files` / `generated_at`）
6. 同步清空 `modules/` 子缓存（D7）
7. 用 §0.2 模板把 modules_index + 跨模块依赖渲染为 Markdown，写 `project_map.md`
8. 更新 `meta.json`（db_hash）

#### 3.2.2 `module_summary` 改造（按 D3 / D4 / D6）

**新签名**：

```python
async def module_summary(project_root: Path, module_name: str) -> str:
```

**新行为**：

1. 读取 `.codesense/modules_index.json`
   - **不存在 → 抛 `InvalidArgumentError`**（D3），消息："请先调用 project_map 资源生成模块划分"
2. 在 `modules` 列表中查找名字匹配的条目（D6：trim + lower 后比对）
   - 找不到 → 抛 `InvalidArgumentError`，错误消息列出可用模块名
3. 取该条目的 `files`（数据层在 §3.2.1 步骤 4 已展开），构建 prompt（见 §4.2）
4. 调 LLM 生成详细 Markdown
5. 缓存到 `.codesense/modules/<safe_key>.json`，文件内含 `module_name` 字段（D4）

**`safe_key` 生成规则（D4 已定）**：

```python
def safe_key(module_name: str) -> str:
    norm = module_name.strip().lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]
```

注意：归一化（trim+lower）后再 hash，保证 D6 的查找一致性——"Cache" 与 " cache " 命中同一缓存。

#### 3.2.3 删除 `_file_in_module`

不再按 `module_path` 前缀匹配文件，改为直接用 `modules_index.json` 中预存的 `files` 列表。

---

### 3.3 Tool：`src/codesense_v1/tools/explore_module.py`

#### 3.3.1 入参语义变更

| 旧                                         | 新                                             |
| ----------------------------------------- | --------------------------------------------- |
| `module_path: str`（目录路径，需含 `__init__.py`） | `module_name: str`（LLM 在 project_map 中给出的模块名） |

**校验逻辑改造**：

- 删除 `module_dir.is_dir()` 检查
- 删除 `(module_dir / "__init__.py").exists()` 检查
- 改为：传给 `summarizer.module_summary`，由 summarizer 内部判断模块名是否存在
- 模块名不存在时，错误消息要列出可用模块名（从 `modules_index.json` 读）

#### 3.3.2 `description` 改写

需要更新工具描述，强调"模块名"而非"路径"，删除 Python 包相关措辞。建议草稿：

```
返回指定模块的架构理解：一句话描述、对外接口、内部文件、依赖模块。
适用场景：询问某模块的作用或策略、改动某模块前需先了解其结构和接口契约、理解模块间依赖关系。
不适用场景：仅需定位模块位置（用 project_map 即可）、已知确切文件路径或符号名（直接 grep/read_file）。
参数：module_name 是 project_map 中列出的模块名。如果不知道有哪些模块，请先读取 codesense://project_map 资源。
```

> ⚠️ **不确定点**：description 措辞是否符合你的偏好？  
> **必须问用户**：写好后给你过目，再定稿。

---

### 3.4 Schema：`src/codesense_v1/schemas/schemas.py`

将 `EXPLORE_MODULE_INPUT_SCHEMA` 的 `module_path` 改为 `module_name`：

```python
EXPLORE_MODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_name": {
            "type": "string",
            "description": "project_map 中列出的模块名（如 '缓存层'）",
        }
    },
    "required": ["module_name"],
    "additionalProperties": False,
}
```

---

### 3.5 缓存层：`src/codesense_v1/cache/cache.py`

#### 3.5.1 新增读写函数

```python
def read_modules_index(codesense_dir: Path) -> dict[str, object] | None: ...
def write_modules_index(codesense_dir: Path, index: dict[str, object], current_hash: str) -> None: ...
```

行为约定与 `read_project_map` / `write_project_map` 一致。

#### 3.5.2 `invalidate` 扩展

`invalidate()` 同时删除 `modules_index.json`。

#### 3.5.2b `write_modules_index` 同步清子缓存（D7）

`write_modules_index` 在写入新索引之前，必须先清空 `modules/` 子目录下所有 `*.json`（不删 `modules_index.json` 自身、不删 `meta.json`）。理由：LLM 输出非确定性，模块名漂移会让旧 `modules/<safe_key>.json` 成孤儿；DB hash 未变也可能发生（用户手动删 index 触发重生）。

实现可直接复用 `invalidate` 中清 modules/ 的那段循环，提取为内部 helper `_clear_modules_dir`。

#### 3.5.3 `module_key` 函数改造

按 3.2.2 决策（slugify 或 hash），实现 `safe_key(module_name: str) -> str`。原有 `module_key(module_path)` 可保留或重命名，由实现者决定，但要保证 `cache.read_module` / `cache.write_module` 调用方一致。

---

## 4. LLM Prompt 设计

### 4.1 `_build_project_map_prompt`

> ⚠️ 本节原"同时输出 Markdown + JSON"方案已废弃，统一采用 §0.3 的 **JSON-only prompt**。Markdown 由代码模板渲染（§0.2），不再调 LLM。

**输入数据**（来自 Data 层）：

- 目录树（含每个目录的文件数）
- 目录间依赖（`directory_dependencies`，过滤 external）
- 每个目录的代表性符号（`directory_symbols`，每目录最多 50 个 — D5）

具体 prompt 文本见 §0.3。

> ✅ **已定（D5）**：`max_per_dir = 50`。codegraph-main 符号量大时若 token 超限，再降。

### 4.2 `_build_module_prompt`

**输入数据**：

- 模块名 + LLM 在 project_map 阶段给出的描述
- 该模块包含的所有文件
- 每个文件的符号（函数/类，含签名）
- 该模块依赖的其他模块（基于 `directory_dependencies` 反查）
- 该模块被哪些模块依赖（入向）

**Prompt 模板**：

```
# 模块详细分析请求

你是一位软件架构师。请根据以下数据，生成对模块「<module_name>」的详细理解文档。

## 输入数据

### 模块信息
- 名称：<module_name>
- project_map 中的初步描述：<description>
- 包含文件：<files>

### 模块内符号（函数/类）
<file_path → [symbols with signatures]>

### 依赖关系
- 该模块依赖：<outbound modules>
- 被以下模块依赖：<inbound modules>

## 输出格式（Markdown）

1. **一句话描述**：核心职责（不超过 30 字）
2. **对外接口**：列出该模块对外暴露的函数/类（参考语言惯例：Python 看名称是否以 _ 开头；TypeScript/JS 看是否 export；其他语言依据签名特征推断）
3. **内部文件**：列出文件并给每个文件一句话作用说明
4. **依赖关系**：上游 / 下游模块列表
```

---

## 5. 缓存结构变更

### 5.1 新结构

```
<project_root>/.codesense/
├── project_map.md                  ← Markdown 概览（保持不变）
├── modules_index.json              ← 【新增】LLM 输出的结构化模块映射
├── modules/<safe_key>.json         ← module_summary 缓存（key 规则变更）
└── meta.json                       ← {"db_hash", "generated_at"}
```

### 5.2 `modules_index.json` Schema

```json
{
  "generated_at": "2026-06-17T10:00:00+00:00",
  "modules": [
    {
      "name": "缓存层",
      "description": "...",
      "directories": ["src/codesense_v1/cache"],
      "files": ["src/codesense_v1/cache/__init__.py", "src/codesense_v1/cache/cache.py"]
    }
  ]
}
```

---

## 6. 测试改造

### 6.1 必须修改的测试文件

| 文件                                    | 改造方向                                                                               |
| ------------------------------------- | ---------------------------------------------------------------------------------- |
| `tests/test_explore_module.py`        | 入参从 `module_path` 改为 `module_name`；删除 `__init__.py` 检查相关用例；新增"模块名不存在时报错并列出可用名字"的用例 |
| `tests/test_summarizer.py`            | mock LLM 返回带 JSON 代码块的响应；新增 `modules_index.json` 写入校验；测试 `module_summary` 走索引查找路径  |
| `tests/test_cache.py`                 | 新增 `read_modules_index` / `write_modules_index` / `invalidate` 含 modules_index 的用例 |
| `tests/test_data_modules.py`          | 保持不变（如果 `package_id` 字段保留）。如删除则同步删除断言                                              |
| `tests/test_resources_project_map.py` | 检查响应中包含模块列表（视输出格式而定，可能不需改）                                                         |

### 6.2 新增测试

| 测试用例                   | 位置                                |
| ---------------------- | --------------------------------- |
| `directory_symbols` 函数 | `tests/test_data_aggregate.py` 新增 |
| LLM 响应 JSON 解析失败的处理    | `tests/test_summarizer.py`        |
| 模块名→files 映射查找         | `tests/test_summarizer.py`        |
| `safe_key` 函数（中文/特殊字符） | `tests/test_cache.py`             |

### 6.3 测试约束

- 总测试数从 111 起，**调整后必须仍 ≥111 全部通过**
- LLM 调用一律 mock，不发真实请求
- `mypy --strict` 零错误
- `ruff check` 零警告

---

## 7. 验收标准

### 7.1 自动化检查

```bat
cd /d e:\Python_Project\CodeSense_V1
uv run mypy --strict
uv run ruff check
uv run pytest -q
```

全部零错误 / 零警告 / 全部 passed。

### 7.2 端到端冒烟测试（手动）

1. 重装：`uv tool install --editable . --reinstall`
2. 重启 VSCode
3. 在 CodeMaker 中读 `codesense://project_map`，确认 Markdown 包含模块列表
4. 检查 `.codesense/modules_index.json` 文件存在且格式合法
5. 在 CodeMaker 中调 `explore_module(module_name="<index 中的某个名字>")`，确认返回详细描述
6. 调用一个不存在的模块名，确认错误消息列出可用模块名

### 7.3 实验对比（Week 5 实验产物）

- 在 CodeSense_V1 上跑一次，对比 LLM 输出的模块划分与你的人工判断
- 在 codegraph-main 上跑一次，结合其 README 描述粗校验
- 输出实验记录（建议路径：`doc/Week5/LLM模块界定实验.md`）

---

## 8. 风险与开放问题

### 8.1 已知风险

| 风险                                   | 应对                          |
| ------------------------------------ | --------------------------- |
| LLM 输出的 JSON 格式不稳定                   | 重试一次 + 严格 schema 描述；二次失败抛错  |
| 大型项目（codegraph-main ~15k 符号）token 超限 | 用 `max_per_dir` 截断；必要时分批喂数据 |
| 模块名含特殊字符导致文件名非法                      | `safe_key` 函数兜底处理           |
| 用户输入模块名大小写/空格不一致                     | 查找时做归一化匹配（trim + 大小写不敏感）    |

### 8.2 实现者必须问用户的开放问题

**全部已在 §0 关键决策汇总中关闭**。下表保留作历史记录：

| #   | 原问题                                   | 关闭于 | 决策                                               |
| --- | ------------------------------------- | --- | ------------------------------------------------ |
| 1   | `package_id` 字段是否彻底删除？                | D8  | 保留不删                                             |
| 2   | LLM JSON 解析二次失败时，抛错还是退化？              | D9  | 抛 `LLMError`                                     |
| 3   | `safe_key` 用 slugify 还是 hash？         | D4  | hash[:12]，可读名存 JSON 内                            |
| 4   | `explore_module` description 草稿是否需调整？ | —   | 草稿可用，加一句"返回结果由 LLM 生成，准确性依赖 project_map 阶段的模块划分" |
| 5   | `max_per_dir` 默认值（建议 20）是否合理？         | D5  | 改为 50                                            |
| 6   | 模块名查找的归一化策略粒度？                        | D6  | trim + 大小写不敏感                                    |

---

## 9. 实现顺序建议

按以下顺序提交 commit，每步通过测试再进入下一步：

0. **前置验证**（§0.1 V1 + V2）：跑 codegraph-main DB 探查 file_path 格式；扫 Skill / server.py Instructions 中的 `module_path` 字样
1. 数据层：实现 `directory_symbols`，加测试 → `test_data_aggregate.py` 通过
2. 缓存层：扩展 `read/write_modules_index` + `_clear_modules_dir` + `invalidate`，加测试 → `test_cache.py` 通过
3. Summarizer：实现 LLM JSON 调用 + 后处理校验（D10），加测试 → `test_summarizer.py` 通过
4. Summarizer：实现 Markdown 模板渲染（§0.2），加测试 → 模板输出快照断言
5. Summarizer：改造 `module_summary`（按 D3 抛错、D4 safe_key、D6 归一化），加测试
6. Schema + Tool：改 `EXPLORE_MODULE_INPUT_SCHEMA` 和 `explore_module.py`，同步改 Skill / Instructions（V2 命中点），加测试
7. 全量回归：`pytest -q` 整体通过
8. 重装 MCP，CodeMaker 端冒烟（§7.2）
9. 实验：CodeSense_V1 + codegraph-main 各跑一次，记录结果（§7.3）

---

## 10. 参考文件

- 当前实现：
  - `src/codesense_v1/summarizer/summarizer.py`
  - `src/codesense_v1/tools/explore_module.py`
  - `src/codesense_v1/data/aggregate.py`（`directory_dependencies` 是改造基础）
  - `src/codesense_v1/cache/cache.py`
- 设计背景：`doc/Week4/待确认.md`（议题 3 的最终决策）
- 项目规约：`doc/vibecoding_rules/vibecoding_rules.md`
- Week 4 交付物（不要破坏）：`.codemaker/skills/codesense-workflow/SKILL.md`、MCP Instructions（`server.py`）
