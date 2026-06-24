# MCP资源 模块理解文档

## 一句话描述
定义并对外暴露可读的 MCP 资源。

## 对外接口
- `read_project_map() -> str`：读取并返回项目地图（project map）资源内容，供 MCP 服务端对外暴露为可读资源。

## 内部文件
- `src/codesense_v1/resources/__init__.py`：Python 包标识文件，将 `resources` 目录声明为子包（当前未显式定义符号）。
- `src/codesense_v1/resources/project_map.py`：实现 `read_project_map` 函数，负责生成或读取项目地图内容并以字符串形式返回。

## 依赖关系
- **上游（被依赖）**
  - `src/codesense_v1`：模块归属的顶层包，复用其公共配置与类型定义。
  - `src/codesense_v1/summarizer`：用于生成或获取项目地图所需的摘要数据。
- **下游（依赖方）**
  - `src/codesense_v1/server`：MCP 服务端注册并对外暴露本模块定义的可读资源。
  - `tests`：对本模块的资源读取逻辑进行单元/集成测试验证。
