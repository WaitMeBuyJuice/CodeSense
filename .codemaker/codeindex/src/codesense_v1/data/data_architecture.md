---
entity_names:
  classes:
    - name: "DirCentrality"
      source: "src/codesense_v1/data/architecture.py"
    - name: "ArchitectureFeatures"
      source: "src/codesense_v1/data/architecture.py"
retrieval_hints:
  - "如何计算每个目录的 fan-in / fan-out？"
  - "如何检测依赖图中的循环依赖？"
  - "拓扑分层算法怎么处理循环？"
  - "跨目录公开 API 是如何提取的？与语言无关吗？"
  - "architecture_features 一站式调用返回哪些信号？"
  - "max_depth 参数控制什么？"
architectural_role: "语言无关的架构分析算法层，基于依赖图计算中心性、循环、分层和公开 API"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部函数调用。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：

| 模块 | 用途 | 关键符号 |
|------|------|---------|
| `data/db` | cross_dir_public_api 需要查询节点信息 | `CodeGraphDB` |
| `data/modules` | 输入数据类型 | `Module`, `ModuleEdge` |

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `summarizer` | 全量架构分析 | `architecture_features`, `compute_centrality`, `find_cycles`, `topological_layers`, `cross_dir_public_api`, `external_dependencies_by_dir` |

## 典型调用链

### 全量架构分析（一站式入口）
```
summarizer
  → modules = list_modules(db)
  → edges = module_dependencies(db)
  → architecture_features(db, edges, modules, max_depth=None)
    │
    ├─ compute_centrality(edges, modules, max_depth)
    │     → 按目录聚合 fan_in / fan_out / fan_out_external
    │     → 返回 dict[str, DirCentrality]
    │
    ├─ topological_layers(edges, modules, max_depth)
    │     → 构建目录级邻接表 (_build_dir_adj)
    │     → Tarjan SCC (_tarjan_sccs) 将循环收缩为超节点
    │     → 在压缩 DAG 上迭代式 DFS 计算层号
    │     → layer 0 = 基础层（无出边的叶子目录）
    │
    ├─ find_cycles(edges, modules, max_depth)
    │     → 构建目录级邻接表
    │     → Tarjan SCC → 过滤 size > 1 的 SCC
    │
    ├─ cross_dir_public_api(db, max_depth=max_depth)
    │     → 遍历 imports 边
    │     → 源目录 ≠ 目标目录 且 tgt.kind ∈ {function,class,method,variable}
    │     → 聚合为 {dir: [qualified_names...]}
    │
    └─ external_dependencies_by_dir(edges, modules, max_depth)
          → 过滤 is_external=True 的 ModuleEdge
          → 聚合为 {dir: [external_target_names...]}
```

### 单独计算中心性
```
summarizer
  → compute_centrality(edges, modules, max_depth=None)
    → 每个 Module 映射到目录: _dir_of(file_path, max_depth)
    → 遍历 edges: 按 (src_dir, tgt_dir) 统计 fan_in / fan_out / fan_out_external
    → 返回 DirCentrality(directory, fan_in, fan_out, fan_out_external)
```

## 数据结构

### DirCentrality
| 字段 | 类型 | 说明 |
|------|------|------|
| `directory` | `str` | 目录路径（POSIX 格式，如 `src/codesense_v1/data`） |
| `fan_in` | `int` | 依赖本目录的其他内部目录数量 |
| `fan_out` | `int` | 本目录依赖的其他内部目录数量 |
| `fan_out_external` | `int` | 本目录依赖的外部模块数量 |

### ArchitectureFeatures
| 字段 | 类型 | 说明 |
|------|------|------|
| `centrality` | `dict[str, DirCentrality]` | 每个目录的中心性指标 |
| `layers` | `list[list[str]]` | 拓扑分层，`layers[0]` = 基础层（叶子） |
| `cycles` | `list[list[str]]` | 多成员 SCC（> 1），即循环依赖 |
| `public_api` | `dict[str, list[str]]` | 每个目录被外部目录导入的符号列表 |
| `external_by_dir` | `dict[str, list[str]]` | 每个目录的外部依赖模块名列表 |

## 算法详解

### Tarjan SCC（迭代式）
- 实现位置：`_tarjan_sccs(adj)`
- 使用显式栈模拟 DFS，避免大图上的 Python 递归限制
- 被动提升 `sys.setrecursionlimit` 作为保险
- 返回所有 SCC，每个 SCC 内节点按字母序排序

### 拓扑分层
- 实现位置：`topological_layers(edges, modules, max_depth)`
- 先将目录级邻接图的 SCC 收缩为超节点（压缩 DAG）
- 在压缩 DAG 上迭代式后序 DFS 计算层号
- 层号公式：`layer(node) = 1 + max(layer(successors), default=-1)`
- Layer 0 = 无出边的叶子节点（基础/底层模块）

### Fan-in / Fan-out 计算
- 按去重目录统计（非边数）
- fan_out 仅内部边，fan_out_external 独立统计

### 跨目录公开 API
- 纯图推导：不依赖 `__all__`、`pub`、首字母大写等语言规则
- 跨语言一致：Python / TS / Go / Rust 统一逻辑
- 默认 symbol_kinds：`("function", "class", "method", "variable")`

## 实现约束清单

### 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_depth` | `None` | 目录聚合深度：`None`=完整路径，`1`=仅一级目录 |
| `max_per_dir` | `30` (public_api) / `20` (external) | 每目录返回的最大符号/依赖数 |
| `symbol_kinds` | `("function","class","method","variable")` | cross_dir_public_api 关注的符号类型 |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| Tarjan 实现 | 迭代式栈模拟 | 递归 DFS | 大图（万级目录）不爆栈 |
| 循环处理 | SCC 收缩为超节点 | 直接忽略循环 | 保证拓扑分层在循环图上也有良定义 |
| 公开 API 提取 | 纯图推导（跨目录 imports） | 语言规则解析 | 语言无关，Python/TS/Go 统一 |
| 目录划分 | `PurePosixPath(p).parts[:-1]` | 完整路径 | 文件本身不视为目录成员 |
