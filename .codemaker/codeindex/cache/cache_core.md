---
module_id: cache
architectural_role: 缓存读写层
entity_names:
  constants:
    - name: _SEGMENT_IDS
      source: src/codesense_v1/cache/cache.py:270
      value: '("01_identity", "02_structure", "03_modules", "04_dependencies")'
    - name: _META_FILE
      source: src/codesense_v1/cache/cache.py:18
      value: '"project_map.json"'
    - name: _PROJECT_MAP_FILE
      source: src/codesense_v1/cache/cache.py:19
      value: '"project_map.md"'
    - name: _MODULES_INDEX_FILE
      source: src/codesense_v1/cache/cache.py:20
      value: '"modules_index.json"'
    - name: _MODULES_DIR
      source: src/codesense_v1/cache/cache.py:21
      value: '"modules"'
    - name: _MODULE_HASHES_FILE
      source: src/codesense_v1/cache/cache.py:22
      value: '".hashes.json"'
    - name: _SEGMENTS_DIR
      source: src/codesense_v1/cache/cache.py:23
      value: '"project_map_segments"'
    - name: _CHUNK
      source: src/codesense_v1/cache/cache.py:17
      value: '65536'
    - name: _ILLEGAL_CHARS
      source: src/codesense_v1/cache/cache.py:219
      value: 're.compile(r''[\\/:*?"<>|\x00-\x1f]'') — safe_key 用的非法字符正则'
    - name: safe_key
      source: src/codesense_v1/cache/cache.py:222
      value: '行为规则：strip 输入 → 用 _ILLEGAL_CHARS 把 / \ : * ? " < > | 及 ASCII 控制字符替换为 _ → strip("_") → 截断 100 字符；空结果返回 "_"。可读 sanitize，非 sha1 hash'
    - name: module_key
      source: src/codesense_v1/cache/cache.py:206
      value: '行为规则：strip 输入 → 仅把 / 和 \ 替换为 _。旧版 key 生成，保留兼容'
retrieval_hints:
  - 新增缓存键/文件必须放 cache.py，不可在 tools 层直写 .codesense/（架构归属：cache 是唯一 .codesense/ 读写层）
  - project_map 四段拼接顺序固定为 _SEGMENT_IDS，render_project_map 任一段缺失返回 None（架构归属：段缓存层）
  - 模块文件名 key 用 safe_key(name) 不是 module_key(path)，safe_key 是可读 sanitize 非 hash（架构归属：模块缓存层）
  - write_modules_index 写入前会 _prune_stale_modules 清理孤儿模块缓存（架构归属：索引写入层）
  - auto-expire 由 summarizer 读 CODESENSE_CACHE_AUTO_EXPIRE 决定，cache 的 is_segment_valid 只做 hash 机械比对（架构归属：失效判断分层）
  - read_* 全返回 None 视为 miss，write_* 传播 OSError，invalidate 静默忽略缺失（架构归属：错误约定）
---

## 对外接口

cache 通过 `__init__.py` re-export 20 个公开符号。按职责分组：

**DB hash 与整库失效**
- `db_hash(db_path: Path) -> str` — SHA-256 of codegraph.db，分块读（`_CHUNK=65536`）；`FileNotFoundError` 传播
- `is_cache_valid(codesense_dir: Path, current_hash: str) -> bool` — 比对 `project_map.json` 的 `db_hash`；任何异常返回 False

**project_map 整文件（非段模式，旧路径）**
- `read_project_map(codesense_dir) -> str | None`
- `write_project_map(codesense_dir, content, current_hash) -> None` — 写 `project_map.md` + 更新 meta

**modules_index**
- `read_modules_index(codesense_dir) -> dict | None`
- `write_modules_index(codesense_dir, modules, current_hash, aux_dirs=None) -> None` — 写前 `_prune_stale_modules`，可选存 `auxiliary_dirs`

**模块摘要 + per-module hash**
- `read_module_hashes(codesense_dir) -> dict[str, str]` — 兼容 legacy flat 格式与新 `{hash, generated_at}` 格式
- `write_module_hash(codesense_dir, module_key_str, module_hash) -> None`
- `read_module(codesense_dir, module_key_str) -> str | None`
- `write_module(codesense_dir, module_key_str, name, summary, current_hash, module_content_hash="") -> None` — `name` 参数当前 `# noqa: ARG001` 仅保 API 兼容

**全量失效**
- `invalidate(codesense_dir) -> None` — 删 `project_map.md` / `modules_index.json` / `project_map.json` + 清空 `modules/`
- `invalidate_segments(codesense_dir) -> None` — 删 `project_map_segments/` 整目录

**key 生成**
- `module_key(module_path: str) -> str` — 旧版
- `safe_key(module_name: str) -> str` — 新版

**段缓存**
- `read_segment(codesense_dir, segment_id) -> str | None`
- `read_segment_hash(codesense_dir, segment_id) -> str | None`
- `is_segment_valid(codesense_dir, segment_id, current_hash) -> bool` — hash 匹配且段文件存在
- `write_segment(codesense_dir, segment_id, content, source_hash) -> None`
- `render_project_map(codesense_dir) -> str | None` — 按 `_SEGMENT_IDS` 顺序拼接，`\n\n---\n\n` 分隔，写回 `project_map.md`；任一段缺失返回 None

## 跨模块依赖

### 外部依赖（cache → 外部）

| 依赖 | 用途 |
|------|------|
| `hashlib` | `db_hash` SHA-256 |
| `json` | meta / index / hashes 序列化 |
| `re` | `_ILLEGAL_CHARS` 正则（safe_key） |
| `datetime` | `_now_iso` 时间戳 |
| `pathlib.Path` | 全部路径操作 |

无内部依赖（leaf）。

### 反向调用方（谁调 cache，extracted 自源码 import）

| 调用方 | import | 主要用到的 cache 函数 |
|--------|--------|---------------------|
| `tools/project_map.py` | `from codesense_v1 import cache` | read_segment / is_segment_valid / render_project_map |
| `tools/explore_module.py` | `from codesense_v1 import cache` | read_modules_index / read_module / read_module_hashes |
| `tools/save_project_map_segment.py` | `from codesense_v1 import cache` | write_segment |
| `summarizer/summarizer.py` | `from codesense_v1 import cache` | write_modules_index / write_module / render_project_map / invalidate 等 |

`write_modules_index` 的上游调用链（callers, depth=2）：`submit_project_map_tool` → `submit_project_map`（summarizer）→ `write_modules_index`（cache）。

## 典型调用链

1. **段缓存读取路径**：`tools/project_map._seg_valid` → `cache.is_segment_valid` → `cache.read_segment_hash` + `cache.read_segment`；命中则 `cache.render_project_map` 拼接四段。
2. **段缓存写入路径**：`summarizer.save_project_map_segment` → `cache.write_segment`（写 `.md` + `.hash`）。
3. **模块摘要读取路径**：`tools/explore_module` → `cache.read_modules_index`（查模块名→key）→ `cache.read_module`（读 `.md`）。
4. **模块摘要写入路径**：`summarizer.save_module_summary` → `cache.write_module`（写 `.md` + `write_module_hash`）。
5. **索引重建路径**：`summarizer.submit_project_map` → `cache.write_modules_index`（先 `_prune_stale_modules` 再写 index + meta）。

## 实现约束清单

1. **缓存文件路径规约**：meta 文件名是 `project_map.json`（常量 `_META_FILE`），不是 `meta.json`（Week3 文档写的 `meta.json` 已过时，以源码为准）。`project_map.json` 存 `{"db_hash", "generated_at"}`，是整库级失效基准。`project_map.md` 是最终拼接产物。二者关系：write_project_map / write_modules_index / write_module / write_segment(render) 都会调 `_write_meta` 更新 `project_map.json` 的 `db_hash`。

2. **safe_key vs module_key 新旧区别**：
   - `module_key(path)`：旧版，输入目录路径，仅替换 `/` `\` 为 `_`。保留兼容，新代码不用。
   - `safe_key(name)`：新版，输入模块名（LLM 给的中文/任意文本），用 `_ILLEGAL_CHARS` 替换 `/ \ : * ? " < > |` + ASCII 控制字符为 `_`，strip `_`，截断 100 字符，空串返回 `_`。
   - **注意**：当前 `safe_key` 是可读 sanitize，**不是** Week5 handoff 文档说的 `sha1[:12]`——以源码为准。原始模块名存在 `modules_index.json` 的 `module_name` 字段反查。

3. **write_modules_index 的 prune 行为**：写入前调 `_prune_stale_modules(codesense_dir, new_keys)`，其中 `new_keys = {safe_key(m["name"]) for m in modules}`。prune 删除 `modules/` 下 stem 不在 `new_keys` 的 `.md` 文件（跳过 `.hashes.json`），并从 `.hashes.json` 删除 stale key 条目。存活模块的 `.md` 保留，交由 per-module 失效判断是否重生。

4. **auto-expire 语义**：环境变量 `CODESENSE_CACHE_AUTO_EXPIRE`（默认 true）在 **summarizer** 的 `_is_auto_expire_enabled` 读取，不在 cache 自身。cache 的 `is_segment_valid` 只做机械 hash 比对（stored hash == current_hash 且段文件存在），不关心 auto-expire 开关。auto-expire 关闭时，summarizer 即使 hash 不匹配也可能复用旧缓存（具体策略在 summarizer 层）。

5. **错误约定**：所有 `read_*` 捕获全部异常返回 None（视为 miss）；`write_*` 传播 `OSError`（磁盘满等真实错误），但 `codesense_dir` 不存在时自动 `mkdir(parents=True, exist_ok=True)`；`invalidate` / `invalidate_segments` / `_clear_modules_dir` 静默忽略 `OSError`（缺失 = 已失效）；`db_hash` 传播 `FileNotFoundError`；`is_cache_valid` 任何异常返回 False。

6. **段拼接分隔符**：`render_project_map` 用 `"\n\n---\n\n"` 连接四段，每段先 `.strip()`。任一段 `read_segment` 返回 None 则整体返回 None（不写部分文件）。

7. **read_module_hashes 兼容性**：同时支持 legacy flat 格式（`{key: "hash_str"}`）与新格式（`{key: {"hash": "...", "generated_at": "..."}}`），统一返回 `{key: hash_str}`。

## 附：内置文档摘要

**缓存结构（Week5 handoff §2 + Week3 design/cache.md）**

`.codesense/` 目录布局（以源码常量为准）：
```
.codesense/
├── project_map.md              # _PROJECT_MAP_FILE，四段拼接产物
├── project_map.json            # _META_FILE，{"db_hash", "generated_at"}
├── modules_index.json          # _MODULES_INDEX_FILE，{"generated_at", "modules":[...], "auxiliary_dirs"?}
├── modules/                    # _MODULES_DIR
│   ├── <safe_key>.md           # 模块摘要
│   └── .hashes.json            # _MODULE_HASHES_FILE，{key: {"hash","generated_at"}}
└── project_map_segments/       # _SEGMENTS_DIR
    ├── 01_identity.md / 01_identity.hash
    ├── 02_structure.md / 02_structure.hash
    ├── 03_modules.md / 03_modules.hash
    └── 04_dependencies.md / 04_dependencies.hash
```

**Lazy 失效策略（Week5 handoff §2）**：hash 一致 → 命中缓存；hash 不一致 → `invalidate()` 全清后重生。`write_modules_index` 写入时额外清空 `modules/` 子缓存中不再存在的模块（防模块名变动导致孤儿缓存）。

**safe_key 变更（Week5 handoff §2.4）**：Week5 前置改动把模块 key 从 `module_key(path)`（路径→下划线）改为 `safe_key(name)`。handoff 文档记载目标为 `sha1[:12]`，但**实际源码实现为可读 sanitize**（替换非法字符 + 截断 100），以源码为准。`module_key` 保留不删（旧代码仍引用）。

**invalidate 修复（Week5 handoff §2.3）**：`invalidate()` 同时删除 `modules_index.json`（Week3 旧版只删 project_map.md + modules/ + meta，漏删 index）。

**错误处理规范（Week5 handoff §5.4）**：缓存错误约定——`read_*` 返回 None（视为 miss）；`write_*` 传播 OSError；`invalidate` 静默忽略。

> 📄 本节内容来源于仓库内置文档：`doc/Week3/design/cache.md`、`doc/Week3/tasks/cache.md`、`doc/Week5/week5_handoff.md`（原文已提炼，非完整转录）
