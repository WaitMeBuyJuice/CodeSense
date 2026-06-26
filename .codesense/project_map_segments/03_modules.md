## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|----------|
| 错误定义 | 统一工具与业务异常层次 | src/codesense_v1/errors.py |
| 数据层 | 构建代码图谱(CodeGraph DB)并聚合目录/符号/依赖信息 | src/codesense_v1/data |
| 缓存层 | 管理 .codesense 缓存文件读写与失效 | src/codesense_v1/cache |
| 工具注册 | 声明工具规格并通过 jsonschema 校验与分发 | src/codesense_v1/registry |
| 摘要生成 | 协调数据层与缓存层生成架构/模块 Markdown 摘要 | src/codesense_v1/summarizer |
| 工具实现 | MCP 工具入口实现与项目根解析 | src/codesense_v1/tools |
| 服务入口 | 构建 stdio MCP 服务并加载工具 | src/codesense_v1/server |