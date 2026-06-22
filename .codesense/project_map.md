# 项目架构概览

> 由 CodeSense 基于 CodeGraph 数据 + LLM 模块划分自动生成。

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| 公共异常 | 定义项目通用异常与错误类型 | `src/codesense_v1` |
| 缓存模块 | 提供系统数据缓存与读取加速机制 | `src/codesense_v1/cache` |
| 数据模块 | 定义核心数据结构并处理数据流转 | `src/codesense_v1/data` |
| 模型调用模块 | 封装大语言模型的请求与交互逻辑 | `src/codesense_v1/llm` |
| 注册中心模块 | 管理系统内部组件和工具的注册与发现 | `src/codesense_v1/registry` |
| 资源模块 | 负责静态资源文件和配置项的加载与管理 | `src/codesense_v1/resources` |
| 服务端模块 | 提供对外API接口并承载核心服务运行 | `src/codesense_v1/server` |
| 摘要模块 | 实现代码或文本内容的总结与提取 | `src/codesense_v1/summarizer` |
| 工具模块 | 提供跨模块调用的通用辅助函数与方法 | `src/codesense_v1/tools` |

## 模块间依赖

| 来源模块 | 依赖模块 | 依赖类型 |
|----------|----------|----------|
| 工具模块 | 公共异常 | imports |
| 工具模块 | 摘要模块 | imports |
| 工具模块 | 注册中心模块 | imports |
| 摘要模块 | 公共异常 | imports |
| 摘要模块 | 数据模块 | imports |
| 摘要模块 | 模型调用模块 | imports |
| 摘要模块 | 缓存模块 | imports |
| 服务端模块 | 注册中心模块 | imports |
| 服务端模块 | 资源模块 | imports |
| 模型调用模块 | 公共异常 | imports |
| 注册中心模块 | 公共异常 | imports |
| 资源模块 | 公共异常 | imports |
| 资源模块 | 摘要模块 | imports |