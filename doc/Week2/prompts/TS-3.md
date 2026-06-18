# TS-3: 实现 tests/test_mcp_integration.py

## 任务背景

`src/codesense_v1/server.py`（SV-1）已实现，提供 stdio MCP 服务进程入口。

- 命令行入口：`uv run codesense` 或 `uv run python -m codesense_v1.server`
- 服务名：`CodeSense`，版本：`0.1.0`
- 暴露 1 个工具：`add(a: number, b: number) -> str`

需要端到端集成测试：以子进程方式拉起 server，通过官方 mcp Python client 完成 `initialize` 握手 → `tools/list` → `tools/call`，覆盖需求 FR-1 ~ FR-5。

### 需求验收点

| 需求 | 用例 |
|------|------|
| FR-1 服务可启动 | 子进程拉起 2 秒不退出 |
| FR-2 stdio MCP 协议 | `initialize` 握手成功 |
| FR-3 暴露工具列表 | `tools/list` 返回长度 1，name == "add"，inputSchema.required 含 a/b |
| FR-4 add 正常调用 | `add(3,5)="8"`、`add(-1,1)="0"`、`add(1.5,2.5)="4.0"` |
| FR-5 完整错误处理 | 缺失/类型/多余参数三种异常 `isError=True` 且进程仍存活 |

### 官方 mcp client 用法（参考）

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="python",
    args=["-m", "codesense_v1.server"],
)
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("add", {"a": 3, "b": 5})
```

**实现注意**：mcp SDK 版本若 API 名称略有差异（如 `list_tools().tools`、`call_tool` 返回字段），以实际安装版本为准。本任务允许子 Agent 根据 `pip show mcp` 或源码微调，但必须保证以下断言可执行。

### pytest 配置

- `asyncio_mode = "auto"`（异步用例无需装饰器）

---

## 实现目标

编写端到端集成测试，启动真实子进程 + 官方 mcp client，覆盖上述 FR-1~FR-5 验收点。

---

## 需要实现的文件

- `tests/test_mcp_integration.py`

---

## 测试用例要求

### Fixture：session（建议 module 级共享子进程减少启动开销）

```python
import pytest
import sys
from collections.abc import AsyncIterator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@pytest.fixture
async def session() -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "codesense_v1.server"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            yield s
```

> 使用 `sys.executable` 确保子进程用同一 Python 解释器（避免 PATH 上 `python` 与测试运行环境不一致）。
> 若 SDK 不支持上述上下文管理器形式，按实际 API 调整；核心要求是测试体内能拿到一个完成 `initialize` 的 session 对象。

### 用例列表

1. **test_initialize**（FR-2）：fixture 进入即等同验证；用例体内可断言 `session` 非 None；附加：拉起后 `await asyncio.sleep(1)` 再断言子进程未退出（如能拿到进程句柄）

2. **test_list_tools**（FR-3）：
   - `tools = await session.list_tools()`
   - 提取工具列表（SDK 不同字段名可能为 `tools.tools` 或直接可迭代）
   - 断言长度 == 1
   - 断言 `tools[0].name == "add"`
   - 断言 `tools[0].inputSchema["required"]` 包含 `"a"` 与 `"b"`
   - 断言 `tools[0].inputSchema["properties"]["a"]["type"] == "number"`

3. **test_call_add_normal**（FR-4），参数化 3 组：
   - `(3, 5, "8")`
   - `(-1, 1, "0")`
   - `(1.5, 2.5, "4.0")`
   - 调用 `result = await session.call_tool("add", {"a": a, "b": b})`
   - 断言 `result.isError is False`（或等效字段）
   - 断言 `result.content[0].text == expected`

4. **test_call_add_missing_arg**（FR-5）：
   - `result = await session.call_tool("add", {"a": 1})`
   - 断言 `result.isError is True`
   - 断言文案含 `"缺失必填参数"` 与 `"'b'"`

5. **test_call_add_type_error**（FR-5）：
   - `result = await session.call_tool("add", {"a": "x", "b": 1})`
   - 断言 `result.isError is True`
   - 断言文案含 `"期望 number"`

6. **test_call_add_extra_arg**（FR-5）：
   - `result = await session.call_tool("add", {"a": 1, "b": 2, "c": 3})`
   - 断言 `result.isError is True`
   - 断言文案含 `"不允许的多余参数"` 与 `"'c'"`

7. **test_process_alive_after_errors**（FR-1 + FR-5 联合）：
   - 串行执行用例 4/5/6 后，再发起一次正常 `add(1,1)` → `"2"` 仍成功
   - 证明异常路径未导致进程崩溃

### 健壮性约束

- 所有 fixture 必须在 `finally` / 上下文退出时正确关闭 session 与子进程
- 测试不得依赖外部网络
- Windows 平台兼容（`sys.executable` 已避免 PATH 问题）

---

## 验收标准

- `uv run pytest tests/test_mcp_integration.py -v` 全部通过
- `uv run mypy --strict tests/test_mcp_integration.py` 零错误
- `uv run ruff check tests/test_mcp_integration.py` 零警告
- 测试运行结束后无遗留 python 子进程
- 全部测试函数与 fixture 带完整类型注解

---

## 范围约束

- **仅** 创建 `tests/test_mcp_integration.py`
- 严禁修改 `src/` 下任何文件、`pyproject.toml`、其他 `tests/*.py`
- 若发现 SDK API 与本文档示例不符，仅在测试文件内适配，**不**修改 server / registry
- 若必须修改其他文件方能通过，立即停止并向主 Agent 报告
