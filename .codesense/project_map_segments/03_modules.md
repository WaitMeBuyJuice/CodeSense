## 系统分层与模块列表

### 架构分层

```
第2层（入口层）: server, tools
第1层（中间层）: summarizer, registry
第0层（基础层）: data, cache, errors
```

### 模块详情

| 模块名 | 职责 | 路径 |
|--------|------|------|
| errors | 工具领域异常基类，定义统一错误层级 | src/codesense_v1/errors.py |
| cache | 管理 .codesense 缓存文件的读写、校验与失效 | src/codesense_v1/cache |
| data | CodeGraph 数据库查询、目录级依赖聚合与文件分析 | src/codesense_v1/data |
| registry | MCP 工具注册中心，管理工具元数据与参数校验 | src/codesense_v1/registry |
| server | MCP stdio 服务器入口，构建并启动服务 | src/codesense_v1/server |
| summarizer | 协调 Data Layer 与 Cache，生成架构摘要 Markdown | src/codesense_v1/summarizer |
| tools | MCP 工具实现层（project_map、explore_module 等） | src/codesense_v1/tools |