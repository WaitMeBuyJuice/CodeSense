# 任务列表 - server 模块

> 详细设计：`doc/design/server.md`
> 目标文件：`src/codesense_v1/server.py`

---

- [x] SV-1: 实现 `src/codesense_v1/server.py`
  - 输入: `doc/design/server.md` §2、§4、§5、§6
  - 输出: `src/codesense_v1/server.py`
  - 验收标准:
    - 声明 `SERVER_NAME: str = "CodeSense"`、`SERVER_VERSION: str = "0.1.0"`
    - `import codesense_v1.tools` 在模块顶层，先于 `build_server` 调用，触发注册
    - `build_server() -> Server`：创建 `mcp.server.Server`，绑定 `@server.list_tools()`、`@server.call_tool()` 回调，分别委派 `registry.list_tools()` / `await registry.dispatch(...)`
    - `call_tool` 回调按当前 mcp SDK 版本对返回签名做最薄适配（若 SDK 接受 `CallToolResult` 则直接返回；否则返回 `result.content`）
    - `async def run_stdio()`：用 `mcp.server.stdio.stdio_server()` + `server.run(...)`
    - `def main()`：`asyncio.run(run_stdio())`
    - `if __name__ == "__main__": main()`
    - 严禁 `print()`、stdout 日志
    - 严禁 import `errors` / `schemas` / `tools.add`
    - 全部公开符号带完整类型注解
    - `python -m codesense_v1.server` 与 `codesense` 命令均能启动进程，启动 2 秒不退出
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: R-1, T-2, B-1
