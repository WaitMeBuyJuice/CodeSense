---
entity_names:
  classes:
    - name: "DirectoryNode"
      source: "src/codesense_v1/data/files.py"
retrieval_hints:
  - "如何获取所有被索引的文件列表？"
  - "如何构建项目的目录树？"
  - "如何按目录聚合依赖关系？"
  - "如何获取每个目录定义了哪些符号？"
  - "directory_dependencies 和 to_package_dependency_dict 有什么区别？"
architectural_role: "目录级聚合与文件树视图，将文件级 ModuleEdge 聚合成目录级依赖，并提供文件列表和目录树"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部函数调用。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：

| 模块 | 用途 | 关键符号 |
|------|------|---------|
| `data/db` | 读取文件和节点数据 | `CodeGraphDB`, `FileRow` |
| `data/modules` | 输入类型和外部前缀常量 | `Module`, `ModuleEdge`, `EXTERNAL_PREFIX` |

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `summarizer` | 目录级聚合供 LLM 理解目录角色 | `directory_dependencies`, `directory_symbols` |

## 典型调用链

### 目录级依赖聚合
```
summarizer
  → modules = list_modules(db)
  → edges = module_dependencies(db)
  → directory_dependencies(edges, modules, max_depth=None)
    → 每个 Module 映射到其文件所在目录: _module_to_dir(file_path, max_depth)
    → 遍历 ModuleEdge 列表，按 (source_dir, target_dir) 去重聚合
    → 外部依赖保留 external:: 前缀
    → 返回 {dir: {"imports": [...], "calls": [...]}}
```

### 目录符号概览
```
summarizer
  → directory_symbols(db, max_depth=None, kinds=("function","class","method"))
    → 遍历 db.iter_nodes(kinds=kinds)
    → 每个节点映射到目录: _module_to_dir(file_path, max_depth)
    → 返回 {dir: [{"name":..., "kind":..., "file":...}, ...]}
    → max_per_dir 控制每目录最大符号数
```

### 文件列表与目录树
```
tools / summarizer
  → list_files(db)              ← 返回 list[FileRow]，扁平列表
  → directory_tree(db)          ← 返回 DirectoryNode 树根
    → 遍历 db.iter_files()
    → 按 PurePosixPath.parts 拆分为层级
    → 构建嵌套 DirectoryNode（含 files 和 subdirs）
```

## 数据结构

### DirectoryNode（files.py）
| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 目录名（仅最后一段） |
| `path` | `str` | 完整路径（POSIX 格式，根为空字符串） |
| `files` | `list[FileRow]` | 该目录下的文件列表 |
| `subdirs` | `dict[str, DirectoryNode]` | 子目录字典 |

## 实现约束清单

### 函数一览

| 文件 | 函数 | 说明 |
|------|------|------|
| `aggregate.py` | `directory_dependencies(edges, modules, *, max_depth, include_external, include_self_loops)` | 将 ModuleEdge 聚合为目录级依赖字典 |
| `aggregate.py` | `directory_edges(edges, modules, *, max_depth, include_external, include_self_loops)` | `directory_dependencies` 的扁平列表变体 |
| `aggregate.py` | `directory_symbols(db, *, max_depth, kinds, max_per_dir)` | 按目录聚合节点符号 |
| `files.py` | `list_files(db)` | 返回所有被索引文件的扁平列表 |
| `files.py` | `directory_tree(db)` | 构建嵌套目录树 |

### 聚合规则

| 规则 | 说明 |
|------|------|
| 目录提取 | `PurePosixPath(file_path).parts[:-1]` — 文件的父目录路径 |
| max_depth | 截断目录深度，`None`=不截断，`1`=仅一级 |
| include_self_loops | 默认 `False`，过滤源目录=目标目录的聚合边 |
| include_external | 默认 `True`，外部依赖以 `external::` 前缀保留 |

### 与 modules.py 的差异

| 维度 | `directory_dependencies` (aggregate) | `to_package_dependency_dict` (modules) |
|------|--------------------------------------|----------------------------------------|
| 聚合单位 | 文件系统目录 | Package ID（Python 点分名 / 其他目录） |
| Python 差异 | `src/codesense/data` | `codesense.data` |
| 顶层目录 | 保留完整路径 | 点分名 vs `.` |
