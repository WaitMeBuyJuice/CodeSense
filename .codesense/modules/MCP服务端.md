# MCP服务端 模块理解文档

## 1. 一句话描述
启动MCP服务并协调请求、工具与资源调度。

## 2. 对外接口
基于 Python 语言惯例（非下划线开头为公开接口），该模块对外暴露以下函数：

- **`build_server`** (`() -> Server`)：构建并返回 MCP Server 实例。
- **`run_stdio`** (`() -> None`)：启动标准输入输出（stdio）模式的 MCP 服务。
- **`main`** (`() -> None`)：模块的主入口函数，用于触发服务启动。

*(注：`_list_tools`, `_call_tool`, `_list_resources`, `_read_resource` 以下划线开头，视为内部回调实现，不作为对外公开接口。)*

## 3. 内部文件
- `src/codesense_v1/server/__init__.py`：包初始化文件，用于将该目录标识为 Python 包。
- `src/codesense_v1/server/__main__.py`：模块直接运行入口，支持通过 `python -m` 方式启动服务。
- `src/codesense_v1/server/server.py`：核心服务实现文件，包含 MCP 服务构建、工具/资源回调处理及 stdio 运行逻辑。

## 4. 依赖关系
- **上游（该模块依赖的目录）**：
  - `src/codesense_v1/registry`
  - `src/codesense_v1/resources`
- **下游（依赖该模块的目录）**：
  - （无）
