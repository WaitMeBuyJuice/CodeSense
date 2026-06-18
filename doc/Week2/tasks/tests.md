# 任务列表 - tests 模块

> 参考：`doc/design/overview.md` §2 测试模块表、`doc/requirement.md` FR-1~FR-5
> 每个测试文件 = 独立任务（用户决策）

---

- [x] TS-1: 实现 `tests/test_registry.py`
  - 输入: `doc/design/registry.md`
  - 输出: `tests/test_registry.py`
  - 验收标准（测试用例必须覆盖）:
    - `tool` 装饰器：注册成功后 `_REGISTRY[name]` 存在；同名重复注册抛 `RuntimeError`
    - `list_tools()`：返回 `list[mcp.types.Tool]`，包含已注册工具的 name/description/inputSchema
    - `dispatch` 未知工具：`isError=True`，文案含 `"未知工具"`
    - `dispatch` 校验失败：缺失必填 → 文案匹配 `"参数错误：缺失必填参数 'b'"` 模板
    - `dispatch` 校验失败：类型错 → 文案匹配 `"参数错误：'a' 期望 number，收到 str"` 模板
    - `dispatch` 校验失败：多余参数 → 文案匹配 `"参数错误：不允许的多余参数 'c'"` 模板
    - `dispatch` 工具内 raise `ToolError`：文案 = `e.message`
    - `dispatch` 工具内 raise 任意 `Exception`：文案 = `"内部错误：<type 名>"`，不含堆栈
    - `dispatch` 支持同步与异步 handler 两种返回
    - 任何路径 `isinstance(result, CallToolResult)` 且 `len(result.content) >= 1`
    - 测试隔离：使用 `monkeypatch` 替换 `_REGISTRY` 避免全局污染
    - `pytest` 全部通过
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: R-1, B-3

- [x] TS-2: 实现 `tests/test_add.py`
  - 输入: `doc/design/tools.md`、`doc/requirement.md` FR-4、FR-5
  - 输出: `tests/test_add.py`
  - 验收标准（必须覆盖）:
    - 直接调用 `add` handler：
      - `add(3, 5) == "8"`
      - `add(-1, 1) == "0"`
      - `add(1.5, 2.5) == "4.0"`
      - `add(float('nan'), 1)` 抛 `InvalidArgumentError`，文案含 `"'a' 不能为 NaN"`
      - `add(1, float('inf'))` 抛 `InvalidArgumentError`，文案含 `"'b' 不能为 Infinity"`
      - 触发结果溢出场景（如 `1e308 + 1e308`）抛 `InvalidArgumentError`，文案含 `"结果溢出"`
    - 通过 `registry.dispatch("add", {...})` 调用：
      - 正常路径 `isError=False`，`content[0].text == "8"`
      - 缺失 `b` → `isError=True`，文案含 `"缺失必填参数 'b'"`
      - 类型非法（`{"a":"x","b":1}`）→ `isError=True`，文案含 `"期望 number"`
      - 多余参数 `{"a":1,"b":2,"c":3}` → `isError=True`，文案含 `"不允许的多余参数 'c'"`
    - `pytest` 全部通过
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: T-2, B-3

- [x] TS-3: 实现 `tests/test_mcp_integration.py`
  - 输入: `doc/requirement.md` FR-1~FR-5、`doc/design/server.md`
  - 输出: `tests/test_mcp_integration.py`
  - 验收标准（端到端，子进程 + 官方 mcp client）:
    - 通过 `mcp.client.stdio.stdio_client` 以子进程拉起 `python -m codesense_v1.server`
    - 完成 `initialize` 握手（FR-2）
    - `tools/list` 返回长度为 1，`tools[0].name == "add"`，`inputSchema.required` 含 `a`、`b`（FR-3）
    - `tools/call add {a:3,b:5}` → 内容文本 `"8"`，`isError=False`（FR-4）
    - `tools/call add {a:-1,b:1}` → `"0"`
    - `tools/call add {a:1.5,b:2.5}` → `"4.0"`
    - 异常路径（FR-5），每用例断言 `isError=True` 且进程仍存活（`proc.poll() is None`）：
      - 缺失参数 `{a:1}`
      - 类型非法 `{a:"x",b:1}`
      - 多余参数 `{a:1,b:2,c:3}`
    - 用例间复用同一子进程或每个用例独立子进程均可，但必须在 `finally` 中正常关闭
    - 测试标记 `@pytest.mark.asyncio`（依赖 `asyncio_mode = "auto"` 可省略）
    - `pytest` 全部通过
    - `mypy --strict` 零错误
    - `ruff check` 零警告
  - 依赖: SV-1, B-3
