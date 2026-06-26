---
entity_names:
  constants:
    - name: "EXTERNAL_PREFIX"
      value: "\"external::\""
      source: "src/codesense_v1/data/modules.py"
    - name: "_CALLABLE_KINDS"
      value: "frozenset({\"function\", \"method\", \"class\"})"
      source: "src/codesense_v1/data/modules.py"
    - name: "_STRIP_EXT_LANGS"
      value: '{"typescript": (".d.ts", ".ts", ".tsx"), "javascript": (".js", ".jsx", ".mjs", ".cjs")}'
      source: "src/codesense_v1/data/modules.py"
  classes:
    - name: "Module"
      source: "src/codesense_v1/data/modules.py"
    - name: "ModuleEdge"
      source: "src/codesense_v1/data/modules.py"
retrieval_hints:
  - "如何从 CodeGraphDB 构建文件级别的依赖图？"
  - "Module.id 和 file_path 是什么格式？"
  - "module_dependencies 的 include_external/include_calls/include_imports 参数怎么用？"
  - "to_file_dependency_dict 和 to_package_dependency_dict 的区别是什么？"
  - "外部依赖如何标记？external:: 前缀的含义是什么？"
  - "calls 边的过滤规则是什么？为什么有 cross-file guard？"
architectural_role: "文件级依赖模型，将 CodeGraph 节点/边映射为 Module/ModuleEdge"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部函数调用。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：

| 模块 | 用途 | 关键符号 |
|------|------|---------|
| `data/db` | 从 CodeGraphDB 读取文件、节点、边 | `CodeGraphDB`, `NodeRow` |

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `data/architecture` | 图算法分析的输入数据源 | `Module`, `ModuleEdge`, `list_modules`, `module_dependencies` |
| `data/aggregate` | 目录级聚合的输入 | `Module`, `ModuleEdge`, `EXTERNAL_PREFIX` |
| `summarizer` | 项目架构概览生成 | `list_modules`, `module_dependencies` |

## 典型调用链

### 构建文件级依赖图
```
summarizer
  → list_modules(db)                           ← 遍历 db.iter_files() 构建 Module 列表
  → module_dependencies(db, include_external=True, include_calls=True, include_imports=True)
    │
    ├─ 1. 构建解析映射:
    │     file_id_by_path, resolve_id_by_path, file_id_by_resolve_id
    │     → Python: "a/b/c.py" → resolve_id "a.b.c"
    │     → TS/JS:  "a/b/c.ts" → resolve_id "a/b"  (strip extension)
    │
    ├─ 2. imports 边处理:
    │     for e in db.iter_edges(kinds=("imports",)):
    │       → 新版 CodeGraph: tgt_node.file_path 指向真实文件 → 直接映射
    │       → 旧版/占位符: tgt_node.kind=="import" → 按 import_name 解析
    │       → 内部解析成功 → emit(src_fid, tgt_fid, "imports", external=False)
    │       → 内部解析失败 + include_external → emit(src_fid, raw_name, "imports", external=True)
    │
    └─ 3. calls 边处理:
          for e in db.iter_edges(kinds=("calls",)):
            → 过滤: tgt_node.kind ∈ _CALLABLE_KINDS (function/method/class)
            → 过滤: src_node.kind ∈ _CALLABLE_KINDS OR same-file
            → cross-file guard: 跨文件 calls 必须有同名 imports 边才信任
            → emit(src_fid, tgt_fid, "calls", external=False)
```

### 导出为字典格式
```
summarizer
  → edges = module_dependencies(db)
  → to_file_dependency_dict(edges)       ← {file: {imports:[...], calls:[...]}}
  → to_package_dependency_dict(edges, modules)  ← {package: {imports:[...], calls:[...]}}
```

## 数据结构

### Module
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 文件级 ID = POSIX 文件路径（如 `codesense/data/db.py`） |
| `file_path` | `str` | 同 `id`，语义保留 |
| `language` | `str` | 编程语言 |
| `package_id` | `str` | 所属 package/目录（Python: `codesense.data`，其他: `src/bin`） |

### ModuleEdge
| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `str` | 源文件 ID（POSIX 路径） |
| `target` | `str` | 目标文件 ID 或原始 import 名称 |
| `kind` | `str` | `"imports"` 或 `"calls"` |
| `is_external` | `bool` | 是否外部依赖 |

## 实现约束清单

### 必须定义的常量/枚举

| 标识符 | 值 | 所在文件 | 说明 |
|-------|----|---------|------|
| `EXTERNAL_PREFIX` | `"external::"` | `modules.py` | 外部依赖前缀，用于 `to_file_dependency_dict` / `to_package_dependency_dict` |
| `_CALLABLE_KINDS` | `frozenset({"function", "method", "class"})` | `modules.py`（局部变量） | calls 边目标必须是这些 kind 才可信 |
| `_STRIP_EXT_LANGS` | TS/JS 扩展名映射 | `modules.py` | 用于 `_resolve_id` 计算 TS/JS 的扩展名剥离 |

### 文件 ID 解析规则

| 语言 | `_file_id`（公开 ID） | `_resolve_id`（内部匹配用） | 示例 |
|------|----------------------|---------------------------|------|
| Python | POSIX 路径 | 点分模块名，去 `.py` | `a/b/c.py` → `a.b.c`；`a/__init__.py` → `a` |
| TypeScript | POSIX 路径 | 路径去扩展名 | `src/foo.ts` → `src/foo` |
| JavaScript | POSIX 路径 | 路径去扩展名 | `lib/bar.js` → `lib/bar` |
| 其他 | POSIX 路径 | 路径原样 | `main.go` → `main.go` |

### calls 边信任规则

| 条件 | 结果 |
|------|------|
| 目标 kind 不在 `_CALLABLE_KINDS` | 丢弃 |
| 源 kind 非 callable 且跨文件 | 丢弃（CodeGraph 误判，如字符串字面量触发） |
| 跨文件 calls 但无同名 imports 边 | 丢弃（防止同名函数误关联） |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| 文件 ID 格式 | POSIX 路径（`/`） | 原生 OS 路径 | 跨平台一致，便于比较 |
| 外部依赖标记 | `"external::"` 前缀 | 单独标志位 | 字典视图一眼可区分内外 |
| 新旧 CodeGraph 兼容 | 双通道（直接映射 + import_name 解析） | 仅新版 | 向后兼容旧索引 |
| cross-file calls guard | 必须有 imports 边 | 无条件信任 | 消除 CodeGraph 同名函数误关联 |
