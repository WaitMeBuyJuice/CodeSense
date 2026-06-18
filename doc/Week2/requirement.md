# CodeSense_V1 需求文档

## 1. 项目背景与目标

### 1.1 背景
用户希望搭建一个最小可运行的 MCP（Model Context Protocol）服务，用于验证 Agent 客户端能否发现并调用 MCP 服务暴露的工具。

### 1.2 目标
- 提供一个最小框架的 MCP 服务进程。
- 提供 1 个 demo 工具 `add(a, b)`，用于端到端打通"Agent → MCP Server → 工具执行 → 结果返回"链路。
- 服务可被 CodeMaker Agent 通过其 `codemaker_mcp_settings.json` 配置加载并调用。

### 1.3 非目标（明确不做）
- 不实现 Resources、Prompts 等其他 MCP 能力。
- 不实现鉴权、限流、持久化。
- 不做跨平台适配，仅保证 Windows 可用。
- 不做日志记录。
- 不做性能指标承诺。

---

## 2. 用户角色与使用场景

### 2.1 用户角色
| 角色 | 说明 |
|------|------|
| 开发者（项目作者） | 搭建并调试 MCP 服务，将其配置进 CodeMaker。 |
| CodeMaker Agent | 实际调用方，通过 stdio 启动 MCP 服务进程，发起 `list_tools` 与 `call_tool` 请求。 |

### 2.2 使用场景
1. **场景 A：注册服务**  
   开发者将本服务的启动命令写入 `codemaker_mcp_settings.json`，重启 CodeMaker 后能在工具列表中看到 `add`。
2. **场景 B：调用工具（正常路径）**  
   开发者在 CodeMaker 中提问"算一下 3 加 5"，Agent 调用 `add(3, 5)`，返回 `8`。
3. **场景 C：调用工具（异常路径）**  
   Agent 传入非法参数（如字符串、缺失参数），服务返回结构化错误信息，Agent 能解析并向用户提示失败原因。

---

## 3. 功能需求（按优先级排序）

> 编号格式 `FR-x`，每条均可写成测试用例。

### P0（必须，MVP）

**FR-1 服务可启动**  
- 输入：在 Windows 命令行执行启动命令（如 `uv run python -m codesense_v1.server`）。  
- 输出：进程持续运行，不退出；stdout 仅输出 MCP 协议帧，不输出其他内容。  
- 验收：进程启动后 2 秒内未异常退出，返回码非负。

**FR-2 通过 stdio 传输 MCP 协议**  
- 输入：stdin 接收符合 JSON-RPC 2.0 + MCP 规范的请求帧。  
- 输出：stdout 返回符合规范的响应帧。  
- 验收：使用官方 `mcp` 客户端通过 stdio 连接，可完成 `initialize` 握手。

**FR-3 暴露工具列表**  
- 输入：MCP `tools/list` 请求。  
- 输出：返回包含且仅包含 1 个工具 `add` 的列表；该工具携带名称、描述、JSON Schema 参数定义（`a: number`、`b: number`，均为必填）。  
- 验收：响应 JSON 中 `tools` 数组长度为 1，且 `tools[0].name == "add"`，`inputSchema` 中 `required` 包含 `a` 和 `b`。

**FR-4 add 工具正常调用**  
- 输入：`tools/call`，name=`add`，arguments=`{"a": 数字, "b": 数字}`（含整数、浮点、负数）。  
- 输出：返回 `a + b` 的数值结果，作为 MCP `content` 文本块返回。  
- 验收用例：  
  - `add(3, 5) == 8`  
  - `add(-1, 1) == 0`  
  - `add(1.5, 2.5) == 4.0`

**FR-5 add 工具完整错误处理**  
所有错误必须通过 MCP 工具错误机制返回（`isError: true` + 文本说明），不得让服务进程崩溃。需覆盖：  
- 缺失参数（缺 `a` 或 `b`）→ 返回错误，文案包含缺失参数名。  
- 参数类型非法（字符串、布尔、null、数组、对象）→ 返回错误，文案说明期望类型。  
- 多余参数 → 返回错误或按 schema 校验失败处理（二选一，需在实现中一致）。  
- 数值溢出 / 非有限数（NaN、Infinity） → 返回错误，文案说明原因。  
- 验收：上述每种异常各对应至少 1 个测试用例，断言 `isError == true` 且 `process.poll() is None`（进程仍存活）。

### P1（应做）

**FR-6 提供 CodeMaker 配置示例**  
- 输出：`README` 或 `doc/` 中给出可直接粘贴到 `codemaker_mcp_settings.json` 的配置片段（含命令、参数、cwd）。  
- 验收：按示例配置后，CodeMaker 重启能识别到 `add` 工具。

### P2（可选）

- 暂无。

---

## 4. 非功能需求

| 类别 | 要求 | 验收方式 |
|------|------|----------|
| 性能 | 不设硬性指标 | —— |
| 安全/鉴权 | 不实现鉴权；假设运行在本地受信任进程上下文 | 代码中无鉴权逻辑 |
| 兼容性 | 仅需在 Windows + Python 3.14 + 当前 CodeMaker 版本下运行 | Windows 上执行测试套件全部通过 |
| 可维护性 | 项目结构清晰：`src/`、`tests/`、`pyproject.toml`、`doc/` 分离 | 目录结构 review |
| 日志 | 不输出业务日志；stdout 严格只出协议帧 | 启动后人工/脚本观察 stdout，仅为 JSON-RPC 帧 |
| 依赖管理 | 通过 `uv` + `pyproject.toml` 锁定依赖 | `uv sync` 可一键安装 |
| 测试 | pytest 全部通过，含 MCP 协议集成测试（启动子进程，走真实 stdio 握手 + 调用） | `uv run pytest` 退出码为 0 |

---

## 5. 输入 / 输出定义

### 5.1 服务级

| 项 | 定义 |
|----|------|
| 启动方式 | 命令行启动子进程，无命令行参数 |
| 输入通道 | stdin（JSON-RPC 2.0 over MCP，逐行 / 帧） |
| 输出通道 | stdout（JSON-RPC 2.0 响应） |
| 错误通道 | stderr（保留，但当前不写入任何内容） |
| 退出条件 | stdin 关闭或收到 MCP 关闭信号时正常退出，返回码 0 |

### 5.2 工具：`add`

**inputSchema**
```json
{
  "type": "object",
  "properties": {
    "a": { "type": "number", "description": "加数 a" },
    "b": { "type": "number", "description": "加数 b" }
  },
  "required": ["a", "b"],
  "additionalProperties": false
}
```

**正常输出**
```json
{
  "content": [
    { "type": "text", "text": "8" }
  ],
  "isError": false
}
```

**错误输出（示例：缺失参数 b）**
```json
{
  "content": [
    { "type": "text", "text": "参数错误：缺失必填参数 'b'" }
  ],
  "isError": true
}
```

---

## 6. 交付物清单

- `pyproject.toml`（uv 管理）
- `src/codesense_v1/server.py`（MCP 服务入口）
- `src/codesense_v1/tools/add.py`（add 工具实现）
- `tests/test_add.py`（工具单元测试）
- `tests/test_mcp_integration.py`（MCP 协议集成测试）
- `doc/stack.md`、`doc/requirement.md`
- CodeMaker 配置示例片段
