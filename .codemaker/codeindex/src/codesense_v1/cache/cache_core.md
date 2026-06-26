---
entity_names:
  constants:
    - name: "_CODESENSE_DIR"
      value: "\".codesense\""
      source: "src/codesense_v1/cache/cache.py"
retrieval_hints:
  - "如何判断项目架构缓存是否有效？"
  - "模块摘要缓存存在哪里？"
  - "module_hashes 是什么？"
  - "⚠️ 如果你要找的是 CodeGraph SQLite 数据库访问，不在这里，在 data 模块"
  - "新增缓存文件时必须在 cache.py 中新增对应的读写函数，不可在工具函数中直接操作文件系统"
architectural_role: "缓存读写层，封装 .codesense/ 目录 I/O"
---

## 对外接口

本子模块无对外接口（无协议/RPC/事件），仅供内部函数调用。

## 跨模块依赖

> 实现本子模块功能时，除本模块外还需引用的外部模块：无

> 反向依赖（谁调用了本子模块）：

| 调用方模块 | 调用场景 | 关键符号 |
|-----------|---------|---------|
| `tools` | explore_module/project_map 读取缓存判断命中 | `is_cache_valid`, `read_project_map`, `read_module`, `read_modules_index`, `read_module_hashes` |
| `summarizer` | submit_project_map/save_module_summary 写入缓存 | `write_module`, `db_hash` |

## 典型调用链

### 项目架构缓存读取
```
tools.project_map()
  → cache.is_cache_valid()  ← 比较 DB hash
    → 有效: cache.read_project_map() → 返回缓存内容
    → 失效: 返回生成指令
```

### 模块摘要缓存写入
```
tools.save_module_summary_tool(name, summary)
  → summarizer.save_module_summary(name, summary)
    → cache.write_module(name, summary)  ← 写入 .codesense/modules/{name}.md
    → 更新 module_hashes
```

## 实现约束清单

### 必须定义的常量/枚举

| 标识符 | 值 | 所在文件 | 说明 |
|-------|----|---------|------|
| `_CODESENSE_DIR` | `".codesense"` | `cache.py` | 缓存目录名，不可修改——影响所有缓存读写路径 |

### 缓存文件契约

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `meta.json` | JSON | DB hash，用于 project_map 缓存失效判断 |
| `modules_index.json` | JSON | 模块列表 + 辅助目录 |
| `project_map.md` | Markdown | 项目架构概览缓存 |
| `modules/{name}.md` | Markdown | 各模块摘要缓存 |
| `module_hashes.json` | JSON | 模块内容哈希，用于模块级缓存失效 |

### 设计决策

| 决策点 | 选定方案 | 备选方案 | 选定理由 |
|--------|---------|---------|---------|
| 缓存失效策略 | DB hash 比对 | 时间戳比对 | DB hash 更精确——代码变更即失效，无时钟漂移问题 |
| 模块级缓存 | module_hashes 独立管理 | 无模块级缓存 | 支持模块粒度增量更新，避免单模块变更导致全量重生成 |
