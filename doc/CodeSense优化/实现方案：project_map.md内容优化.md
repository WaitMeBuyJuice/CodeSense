# project_map.md 内容优化实现文档

> 项目路径：`E:\Python_Project\CodeSense_V1`
> 本文档供另一对话实现并测试。完成后将结果反馈给原对话。

---

## 一、变更全览

### 1.1 Segment 重新命名与顺序

| 旧 segment_id      | 新 segment_id      | 变更                  |
| ----------------- | ----------------- | ------------------- |
| `01_identity`     | `01_identity`     | 不变                  |
| `02_structure`    | `02_structure`    | 简化：删除"辅助目录"摘要区      |
| `03_modules`      | `03_modules`      | 不变                  |
| （新增）              | `04_constraints`  | 模块边界规则              |
| （新增）              | `05_flows`        | 关键流程描述              |
| （新增）              | `06_concepts`     | 概念索引                |
| `04_dependencies` | `07_dependencies` | 简化：删除 ASCII 箭头图，重命名 |

### 1.2 新增 MCP 工具

| 工具名                              | 用途                          |
| -------------------------------- | --------------------------- |
| `get_constraints_segment_prompt` | 返回 04_constraints 的 LLM 提示词 |
| `get_flows_segment_prompt`       | 返回 05_flows 的 LLM 提示词       |
| `get_concepts_segment_prompt`    | 返回 06_concepts 的半程序+LLM 提示词 |

`save_project_map_segment` 工具扩展 `_VALID_SEGMENT_IDS`，加入三个新 segment_id。

---

## 二、简化改动（02 和 07）

### 2.1 简化 02_structure

**文件**：`src/codesense_v1/summarizer/summarizer.py`
**函数**：`render_structure_segment`

**改动**：删除末尾的辅助目录摘要区（约最后 6 行）：

```python
# 删除以下代码块：
# Add auxiliary dirs summary
aux = [d for d in top_dirs if d.is_auxiliary]
if aux:
    lines.append("\n**辅助目录**\n")
    for d in sorted(aux, key=lambda x: x.name):
        lines.append(f"- `{d.name}/` — {d.category}（{d.file_count} 个文件）")
```

辅助目录已在树状图中以 `[辅助脚本]` `[测试代码]` 标注，无需重复。

### 2.2 重命名 04_dependencies → 07_dependencies + 删除箭头图

**文件 1**：`src/codesense_v1/cache/cache.py`
**改动**：更新 `_SEGMENT_IDS` 元组：

```python
_SEGMENT_IDS: tuple[str, ...] = (
    "01_identity",
    "02_structure",
    "03_modules",
    "04_constraints",  # 新增
    "05_flows",         # 新增
    "06_concepts",      # 新增
    "07_dependencies",  # 原 04_dependencies
)
```

**文件 2**：`src/codesense_v1/summarizer/summarizer.py`
**函数**：`render_dependencies_segment`
**改动**：删除 `## 依赖关系图` 代码块，只保留上下游表和循环依赖警告：

```python
# 删除以下代码块：
lines: list[str] = ["## 依赖关系图\n", "```"]
for src, tgt in sorted(edge_set):
    lines.append(f"{src} ──→ {tgt}")
if not edge_set:
    lines.append("（无依赖关系数据）")
lines.append("```")

# 改为直接从 ## 上下游详表 开始
lines: list[str] = []
```

**文件 3**：`src/codesense_v1/tools/project_map.py`
所有 `"04_dependencies"` → `"07_dependencies"`

**文件 4**：`src/codesense_v1/summarizer/summarizer.py`
`submit_project_map` 中 `"04_dependencies"` → `"07_dependencies"`

**文件 5**：`src/codesense_v1/tools/save_project_map_segment.py`
`_VALID_SEGMENT_IDS` 里更新 segment_id（同时加入新增三个，见下文）

---

## 三、新增 Segment 实现

### 3.1 `04_constraints` — 模块边界规则

#### 数据收集（在 summarizer 新函数中）

```python
async def get_constraints_segment_prompt(project_root: Path) -> str:
    """Return LLM prompt for generating 04_constraints."""
    codesense_dir = project_root / ".codesense"
    db_path = project_root / ".codegraph" / "codegraph.db"

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=False)
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]

    # 模块列表
    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    # 模块间 imports 关系
    dir_deps = directory_dependencies(edges_all, modules_data,
                                       include_external=False, include_self_loops=False)

    # 拓扑层次（基础层→入口层）
    layers = topological_layers(edges_all, modules_data)
    cycles = find_cycles(edges_all, modules_data)

    # 参考文档
    ref_section = ref_docs_prompt_section(project_root)

    # 构建 prompt
    modules_text = "\n".join(
        f"- `{m.get('name')}` ({', '.join(m.get('directories', []) or m.get('files', []))}): {m.get('description', '')}"
        for m in saved_modules if isinstance(m, dict)
    )
    deps_text = "\n".join(
        f"- {src} → {', '.join(tgts.get('imports', []))}"
        for src, tgts in dir_deps.items() if tgts.get('imports')
    )
    layers_text = "\n".join(
        f"- 第{i}层: {', '.join(sorted(layer))}"
        for i, layer in enumerate(layers)
    )
    cycle_text = "无循环依赖" if not cycles else "\n".join(
        f"- 循环: {' → '.join(c)}" for c in cycles
    )

    return (
        "# 模块边界规则生成\n\n"
        "你是一位软件架构师。请根据以下模块结构数据，推断并总结项目的**架构规则与边界约束**。\n\n"
        "## 输出格式（Markdown）\n\n"
        "```markdown\n"
        "## 模块边界规则\n\n"
        "### 层次约束\n"
        "- <层次结构规则，如「server → registry → tools → summarizer」单向依赖>\n\n"
        "### 访问禁忌\n"
        "- <哪些模块不能直接调用哪些，如「tools 层禁止直接操作 .codesense/ 目录」>\n\n"
        "### 职责边界\n"
        "- <每层的唯一职责，如「data 层只读，不写任何文件」>\n\n"
        "### 新增代码约束\n"
        "- <新增功能时必须遵守的规则>\n"
        "```\n\n"
        "## 模块数据\n\n"
        f"### 模块列表\n{modules_text}\n\n"
        f"### 模块间依赖（imports）\n{deps_text or '（无数据）'}\n\n"
        f"### 拓扑层次\n{layers_text or '（无数据）'}\n\n"
        f"### 循环依赖\n{cycle_text}\n\n"
        + (f"## 参考文档\n\n{ref_section}\n" if ref_section else "")
        + "**注意**：规则要基于数据推断，不要凭空捏造；如推断依据不足，请注明「待人工补充」。"
    )
```

#### Cache Hash 计算

```python
# 04_constraints hash = hash(模块目录集 + 模块间 imports 边集)
# 在 project_map.py 中：
from codesense_v1.data import compute_architecture_hash, compute_dependencies_hash

# 模块目录集（同 hash_03 的叶目录方案）
hash_04 = compute_dependencies_hash([e for e in edges_all if not e.is_external])
# 注意：这里用 imports 边集，而不是所有边。已有的 compute_dependencies_hash 基于 edges，直接复用
# 实际上 hash_04 和 hash_07 共用同一个 imports 边集 hash，两者一起失效
```

**简化处理**：04_constraints 和 07_dependencies 用同一个 hash 值（都基于模块间 imports 边集），当 imports 关系变化时，两者一起失效重生成。

---

### 3.2 `05_flows` — 关键流程描述

#### 入口点识别（启发式 A + LLM C）

```python
_ENTRY_LAYER_KEYWORDS = frozenset({
    "tool", "tools", "handler", "handlers",
    "controller", "controllers", "server",
    "main", "api", "cli", "cmd", "endpoint", "endpoints",
    "route", "routes", "app",
})

def _identify_entry_modules(saved_modules: list[dict]) -> list[dict]:
    """Identify candidate entry modules by name heuristics."""
    candidates = []
    for m in saved_modules:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", "")).lower()
        dirs = [str(d).lower() for d in (m.get("directories") or m.get("files") or [])]
        is_candidate = any(kw in name for kw in _ENTRY_LAYER_KEYWORDS) or \
                       any(any(kw in d for kw in _ENTRY_LAYER_KEYWORDS) for d in dirs)
        if is_candidate:
            candidates.append(m)
    return candidates
```

#### 数据收集

```python
async def get_flows_segment_prompt(project_root: Path) -> str:
    """Return LLM prompt for generating 05_flows."""
    codesense_dir = project_root / ".codesense"

    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_calls = [e for e in module_dependencies(db, include_external=False)
                       if e.kind == "calls"]
        edges_imports = [e for e in module_dependencies(db, include_external=False)
                         if e.kind == "imports"]
        dir_syms = directory_symbols(db, max_per_dir=20)

    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    # 识别候选入口模块
    candidates = _identify_entry_modules(saved_modules)
    candidate_names = [m.get("name", "") for m in candidates]

    # 各入口模块的公开符号（作为流程起点参考）
    entry_syms_text = ""
    for m in candidates:
        dirs = m.get("directories") or [str(f).rsplit("/", 1)[0] for f in (m.get("files") or [])]
        syms = []
        for d in dirs:
            syms.extend(dir_syms.get(d, []))
        if syms:
            sym_str = ", ".join(s["name"] for s in syms[:10])
            entry_syms_text += f"\n- `{m.get('name')}` 符号: [{sym_str}]"

    # 模块依赖摘要
    dir_deps = directory_dependencies(edges_imports, modules_data,
                                       include_external=False, include_self_loops=False)
    ref_section = ref_docs_prompt_section(project_root)

    return (
        "# 关键流程描述生成\n\n"
        "你是一位软件架构师。请根据以下数据，识别并描述项目中**最重要的跨模块端到端流程**（3-5 个）。\n\n"
        "## 输出格式（Markdown）\n\n"
        "```markdown\n"
        "## 关键流程描述\n\n"
        "### 流程名称\n"
        "**场景**：<什么时候触发>\n"
        "**调用链**：模块A → 模块B → 模块C\n"
        "**关键步骤**：\n"
        "1. <步骤1>\n"
        "2. <步骤2>\n"
        "3. <步骤3>\n"
        "```\n\n"
        "## 候选入口模块（程序启发式识别，请根据实际情况确认/修改）\n\n"
        f"以下模块可能是流程入口：**{', '.join(candidate_names) or '（未识别到，请自行判断）'}**\n"
        f"{entry_syms_text}\n\n"
        "如有遗漏或误判（如项目用不同命名规范），请在流程描述中自行补充正确入口。\n\n"
        "## 模块列表（用于理解跨模块协作）\n\n"
        + "\n".join(
            f"- `{m.get('name')}`: {m.get('description', '')}"
            for m in saved_modules if isinstance(m, dict)
        )
        + "\n\n"
        + (f"## 参考文档\n\n{ref_section}\n" if ref_section else "")
        + "**要求**：每个流程必须跨越至少 2 个模块；描述要具体到函数名或数据流向，不要泛泛而谈。"
    )
```

#### Cache Hash 计算

```python
# 05_flows hash = hash(全部 calls 边集合)
# 在 project_map.py 的 hash 计算区：
from codesense_v1.data.hashes import _sha256
import json

with CodeGraphDB(project_root) as db:
    all_edges = list(db.iter_edges())  # 需要在 CodeGraphDB 中暴露 iter_edges

calls_edges = sorted(
    (e.source, e.target)
    for e in all_edges
    if e.kind == "calls"
)
hash_05 = _sha256(json.dumps(calls_edges))
```

> **注意**：`CodeGraphDB.iter_edges()` 当前可能没有暴露 kind 过滤，需要确认 `data/db.py` 里 `iter_edges` 的实现，看是否支持 `kinds=("calls",)` 过滤。

---

### 3.3 `06_concepts` — 概念索引（半程序 + LLM）

#### 程序部分：构建符号→模块映射表

```python
def _build_symbol_module_map(
    saved_modules: list[dict],
    db: CodeGraphDB,
    public_kinds: tuple[str, ...] = ("function", "class", "method"),
) -> dict[str, str]:
    """Build {symbol_name: module_name} for all public symbols."""
    # 构建目录→模块名映射
    dir_to_module: dict[str, str] = {}
    for m in saved_modules:
        if not isinstance(m, dict):
            continue
        mname = str(m.get("name", ""))
        for d in (m.get("directories") or []):
            dir_to_module[str(d)] = mname
        for f in (m.get("files") or []):
            fp = str(f).replace("\\", "/")
            dir_to_module[fp] = mname
            parent = fp.rsplit("/", 1)[0] if "/" in fp else ""
            if parent:
                dir_to_module.setdefault(parent, mname)

    # 遍历 nodes，提取公开符号
    symbol_map: dict[str, str] = {}
    for node in db.iter_nodes(kinds=public_kinds):
        fp = node.file_path.replace("\\", "/")
        parent = fp.rsplit("/", 1)[0] if "/" in fp else fp
        module = dir_to_module.get(fp) or dir_to_module.get(parent)
        if module and not node.name.startswith("_"):  # 跳过私有符号
            symbol_map[node.name] = module
    return symbol_map
```

#### LLM Prompt

```python
async def get_concepts_segment_prompt(project_root: Path) -> str:
    """Return LLM prompt for generating 06_concepts."""
    codesense_dir = project_root / ".codesense"

    with CodeGraphDB(project_root) as db:
        pass  # symbol_map 在下面

    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    with CodeGraphDB(project_root) as db:
        symbol_map = _build_symbol_module_map(saved_modules, db)

    # 按模块分组
    module_symbols: dict[str, list[str]] = {}
    for sym, mod in symbol_map.items():
        module_symbols.setdefault(mod, []).append(sym)

    symbol_table_text = "\n".join(
        f"- 模块 `{mod}` 公开符号: {', '.join(sorted(syms)[:15])}"
        for mod, syms in sorted(module_symbols.items())
    )

    modules_text = "\n".join(
        f"- `{m.get('name')}`: {m.get('description', '')}"
        for m in saved_modules if isinstance(m, dict)
    )

    return (
        "# 概念索引生成\n\n"
        "你是一位软件架构师。请根据以下数据，生成项目的**概念索引**——即"用户可能会用哪些词语搜索，对应的是哪个模块/符号"。\n\n"
        "## 输出格式（Markdown，表格形式）\n\n"
        "```markdown\n"
        "## 概念索引\n\n"
        "| 关键词 / 业务概念 | 对应模块 | 核心符号 | 备注 |\n"
        "|-----------------|---------|---------|------|\n"
        "| 关键词（中文或英文）| 模块名 | 函数/类名 | 易混淆提示或说明 |\n"
        "```\n\n"
        "## 要求\n"
        "1. 关键词要覆盖：业务操作词（如「缓存失效」「模块划分」）+ 技术词（如「segment」「prompt」）\n"
        "2. 对同名/近义系统，必须加「备注」区分（如「submit_project_map vs save_project_map_segment 的区别」）\n"
        "3. 至少 15 条，覆盖所有模块\n\n"
        "## 程序提取的符号-模块映射（已完成，你只需添加关键词和备注）\n\n"
        f"{symbol_table_text}\n\n"
        "## 模块描述\n\n"
        f"{modules_text}\n\n"
        "**注意**：关键词要是用户实际可能搜索的词，不要是技术实现细节词；备注栏专门写易混淆说明。"
    )
```

#### Cache Hash 计算

```python
# 06_concepts hash = hash(modules_index 内容 + 各模块公开符号名集合)
# 在 project_map.py 中：
with CodeGraphDB(project_root) as db:
    symbol_map = _build_symbol_module_map(saved_modules, db)

# 把 symbol_map 中的 (symbol, module) 排序后 hash
concepts_data = sorted(symbol_map.items())
hash_06 = _sha256(json.dumps(concepts_data))
```

---

## 四、project_map.py 主流程改造

### 4.1 Segment 顺序和 Hash 计算更新

```python
# tools/project_map.py 核心逻辑重写

async def project_map() -> str:
    ...
    # ---- Gather data --------------------------------------------------------
    with CodeGraphDB(project_root) as db:
        modules_data = list_modules(db)
        edges_all = module_dependencies(db, include_external=True)
        edges_internal = [e for e in edges_all if not e.is_external]
        all_file_paths = [f.path.replace("\\", "/") for f in db.iter_files()]
        tree_root = directory_tree(db)
        identity_sources = collect_identity_sources(project_root, db)
        # calls 边用于 05_flows hash
        all_db_edges = list(db.iter_edges())  # 需要 CodeGraphDB.iter_edges()

    top_dirs = classify_top_dirs(all_file_paths)
    cycles = find_cycles(edges_internal, modules_data)
    modules_index = cache.read_modules_index(codesense_dir)
    saved_modules = (modules_index or {}).get("modules", [])

    # ---- Compute hashes -----------------------------------------------------
    hash_01 = compute_identity_hash(identity_sources)
    hash_02 = compute_structure_hash(top_dirs)

    # 03: 叶目录集
    all_parent_dirs = {fp.rsplit("/", 1)[0] for fp in all_file_paths if "/" in fp}
    current_leaf_dirs = sorted({
        d for d in all_parent_dirs
        if not any(other != d and other.startswith(d + "/") for other in all_parent_dirs)
    })
    hash_03 = compute_architecture_hash([current_leaf_dirs])

    # 04 & 07: imports 边集（共用）
    imports_hash = compute_dependencies_hash(edges_internal)
    hash_04 = imports_hash  # constraints
    hash_07 = imports_hash  # dependencies

    # 05: calls 边集
    calls_edges = sorted(
        (e.source, e.target)
        for e in all_db_edges
        if getattr(e, 'kind', '') == "calls"
    )
    hash_05 = _sha256(json.dumps(calls_edges))

    # 06: symbol-module map
    with CodeGraphDB(project_root) as db2:
        symbol_map = _build_symbol_module_map(saved_modules, db2)
    concepts_data = sorted(symbol_map.items())
    hash_06 = _sha256(json.dumps(concepts_data))

    # ---- Generate pure-program segments immediately -------------------------
    if not _seg_valid(codesense_dir, "02_structure", hash_02, auto_expire):
        adaptive_depth = compute_tree_max_depth(all_file_paths)
        content_02 = render_structure_segment(project_root, top_dirs, tree_root, max_depth=adaptive_depth)
        cache.write_segment(codesense_dir, "02_structure", content_02, hash_02)

    if not _seg_valid(codesense_dir, "07_dependencies", hash_07, auto_expire):
        content_07 = render_dependencies_segment(saved_modules, edges_internal, cycles)
        cache.write_segment(codesense_dir, "07_dependencies", content_07, hash_07)

    # ---- Check what needs Agent ---------------------------------------------
    missing = []
    # 先检查不依赖 03 的段
    if not _seg_valid(codesense_dir, "01_identity", hash_01, auto_expire):
        missing.append(("01_identity", "仓库定位 + 技术栈", "get_identity_segment_prompt", None))
    if not _seg_valid(codesense_dir, "03_modules", hash_03, auto_expire):
        missing.append(("03_modules", "模块列表（其他段依赖此段，请优先完成）", "get_modules_segment_prompt → submit_project_map", None))
    # 依赖 03 的段（03 missing 时也列出，带"需 03 先完成"提示）
    need_03 = not _seg_valid(codesense_dir, "03_modules", hash_03, auto_expire)
    dep_note = "（需 03_modules 先完成）" if need_03 else ""
    if not _seg_valid(codesense_dir, "04_constraints", hash_04, auto_expire):
        missing.append(("04_constraints", "模块边界规则" + dep_note, "get_constraints_segment_prompt", "03_modules"))
    if not _seg_valid(codesense_dir, "05_flows", hash_05, auto_expire):
        missing.append(("05_flows", "关键流程描述" + dep_note, "get_flows_segment_prompt", "03_modules"))
    if not _seg_valid(codesense_dir, "06_concepts", hash_06, auto_expire):
        missing.append(("06_concepts", "概念索引" + dep_note, "get_concepts_segment_prompt", "03_modules"))

    if not missing:
        result = cache.render_project_map(codesense_dir)
        if result:
            return result

    # ---- One-shot missing list ----------------------------------------------
    steps = []
    for i, (seg_id, desc, tool_name, dep) in enumerate(missing):
        dep_str = f"（依赖 {dep}，请等 {dep} 完成后再做）" if dep and need_03 else ""
        steps.append(f"{i+1}. **{seg_id}**（{desc}）\n   → 调用 `{tool_name}` 获取提示词，生成后调用 `save_project_map_segment(segment_id=\"{seg_id}\", ...)` 保存{dep_str}")

    steps_str = "\n".join(steps)
    return (
        "# 项目概览尚未完整，需生成以下段落\n\n"
        f"{steps_str}\n\n"
        "## 生成顺序说明\n\n"
        "- **必须先完成 `03_modules`**（其他段依赖模块划分结果）\n"
        "- `01_identity` 与 `03_modules` 可并行生成\n"
        "- `04_constraints`、`05_flows`、`06_concepts` 需在 `03_modules` 完成后执行\n\n"
        "**全部完成后，重新调用 `project_map` 获取完整概览（共 2 次调用即可完成初始化）。**"
    )
```

---

## 五、工具注册

### 5.1 新增三个 prompt 工具文件

每个文件结构与 `get_identity_segment_prompt.py` 相同：

**`tools/get_constraints_segment_prompt.py`**

```python
"""MCP Tool: get_constraints_segment_prompt — returns LLM prompt for module boundary rules."""
from codesense_v1.summarizer import get_constraints_segment_prompt

@tool(name="get_constraints_segment_prompt", description=(...), input_schema=_SCHEMA)
async def get_constraints_segment_prompt_tool() -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()
    try:
        return await get_constraints_segment_prompt(project_root)
    except FileNotFoundError:
        return "# 错误\n\nCodeGraph 数据库不存在。请先运行 `codegraph init -i`。"
```

**`tools/get_flows_segment_prompt.py`** 和 **`tools/get_concepts_segment_prompt.py`** 同上，替换函数名即可。

### 5.2 更新 `tools/__init__.py`

```python
from . import (
    ...
    get_constraints_segment_prompt,  # noqa: F401
    get_flows_segment_prompt,        # noqa: F401
    get_concepts_segment_prompt,     # noqa: F401
    ...
)
```

### 5.3 更新 `save_project_map_segment.py`

```python
_VALID_SEGMENT_IDS = (
    "01_identity",
    "03_modules",
    "04_constraints",
    "05_flows",
    "06_concepts",
)
```

对应的 hash 计算 `else` 分支要扩展，针对每个 segment_id 用正确的 hash 方法。

### 5.4 更新 `summarizer/__init__.py`

导出三个新函数：`get_constraints_segment_prompt`、`get_flows_segment_prompt`、`get_concepts_segment_prompt`。

---

## 六、测试方法

### 6.1 整体集成测试（最重要）

```
1. 删除 .codesense/ 目录
2. 重启 MCP 服务（重载代码）
3. 调用 project_map（首次）
   → 预期返回：列出 01/03/04/05/06 缺失，明确 03 优先顺序
4. 按照引导，依次完成所有 5 个段
5. 调用 project_map（二次）
   → 预期返回：完整 project_map.md（7 段合并，无缺失）
6. 检查 .codesense/project_map_segments/ 下有 7 个文件
7. 检查 .codesense/project_map.md 内容包含 7 个标题
```

### 6.2 简化测试（02 和 07）

```
# 测试 02 辅助目录摘要已删除
1. 查看 .codesense/project_map_segments/02_structure.md
   → 确认末尾没有 "**辅助目录**" 小结表
   → 确认目录树中有 [辅助脚本] [测试代码] 标注

# 测试 07 箭头图已删除
2. 查看 .codesense/project_map_segments/07_dependencies.md
   → 确认没有 "## 依赖关系图" + 箭头列表
   → 确认有 "## 上下游详表" + 表格
```

### 6.3 缓存失效测试（06不行

```
# 04_constraints / 07_dependencies 共同失效
1. 在某文件加一行 import → codegraph sync
2. 调用 project_map
   → 预期：04_constraints 和 07_dependencies 缓存失效
   → 07 自动重生成（程序段）
   → 04 提示重新生成（LLM 段）

# 05_flows 失效
3. 在某文件增删一个函数调用 → codegraph sync
4. 调用 project_map
   → 预期：05_flows 缓存失效，提示重新生成

# 06_concepts 失效
5. 在 submit_project_map 修改模块描述（改变 modules_index）→ 调用 project_map
   → 预期：06_concepts 缓存失效，提示重新生成
```

### 6.4 单段内容质量测试

```
# 04_constraints 质量
- 检查是否有具体禁忌（"XX 层不能做 YY"），而非模糊描述
- 检查是否提到循环依赖规则（如果有）

# 05_flows 质量
- 检查是否识别到正确的入口模块（tools 层）
- 检查每个流程是否跨越 2+ 模块
- 检查调用链方向是否准确

# 06_concepts 质量
- 检查是否有中文业务关键词
- 检查是否有 submit vs save 等混淆提示
- 检查是否覆盖了所有模块
```

---

## 七、注意事项

1. `CodeGraphDB.iter_edges()` 是否已暴露并支持查询 kind？查看 `data/db.py`，可能需要确认。
2. `_build_symbol_module_map` 和 `_identify_entry_modules` 作为私有函数放在 `summarizer/summarizer.py` 里。
3. `_sha256` 辅助函数已在 `data/hashes.py` 中定义，`project_map.py` 需要导入。
4. `render_dependencies_segment` 改动后，原有测试 (`tests/test_summarizer.py`) 可能需要更新。
5. 所有 segment_id 修改（04_dependencies → 07_dependencies）涉及文件：`cache/cache.py`、`tools/project_map.py`、`summarizer/summarizer.py`、`tools/save_project_map_segment.py`。
