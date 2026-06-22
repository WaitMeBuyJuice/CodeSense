# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 公共异常 | 定义项目共享的异常类型与基础常量 | `src/codesense_v1` |
| 缓存模块 | 负责分析结果、LLM响应等数据的缓存管理、避免重复计算与调用 | `src/codesense_v1/cache` |
| 数据模块 | 定义核心数据模型、数据集加载与持久化接口 | `src/codesense_v1/data` |
| LLM模块 | 封装大语言模型调用、Prompt构建、结果解析与错误处理 | `src/codesense_v1/llm` |
| 注册管理模块 | 负责组件、模型与工具的注册、发现及生命周期管理 | `src/codesense_v1/registry` |
| 资源模块 | 管理配置文件、模板、静态资源等辅助文件 | `src/codesense_v1/resources` |
| 服务模块 | 对外提供HTTP/RPC服务接口及服务的启动与停止管理 | `src/codesense_v1/server` |
| 摘要模块 | 基于代码信息或LLM输出生成并输出摘要结果 | `src/codesense_v1/summarizer` |
| 工具模块 | 封装可调用工具集合及其执行、参数解析与结果返回 | `src/codesense_v1/tools` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| LLM模块 | 公共异常 | imports |
| 工具模块 | 公共异常 | imports |
| 工具模块 | 摘要模块 | imports |
| 工具模块 | 注册管理模块 | imports |
| 摘要模块 | LLM模块 | imports |
| 摘要模块 | 公共异常 | imports |
| 摘要模块 | 数据模块 | imports |
| 摘要模块 | 缓存模块 | imports |
| 服务模块 | 注册管理模块 | imports |
| 服务模块 | 资源模块 | imports |
| 注册管理模块 | 公共异常 | imports |
| 资源模块 | 公共异常 | imports |
| 资源模块 | 摘要模块 | imports |