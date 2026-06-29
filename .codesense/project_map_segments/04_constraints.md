## 模块边界规则

### 层次约束

项目采用严格三层架构，单向依赖：

```
入口层 (server / tools) → 中间层 (summarizer / registry) → 基础层 (data / cache / errors)
```

- 基础层（第0层）不依赖任何项目内模块
- 中间层（第1层）只能依赖基础层
- 入口层（第2层）可依赖中间层和基础层
- 严禁反向依赖（如 data 调用 summarizer）

### 访问禁忌

- **tools 禁止直接操作 `.codesense/` 目录**：所有缓存读写必须通过 cache 模块
- **tools 禁止直接调用 CodeGraphDB 查询**：所有数据查询必须通过 data 模块
- **cache 禁止导入 data 或 summarizer**：cache 是纯 I/O 层
- **data 禁止写入任何缓存文件**：data 只读文件系统 + CodeGraph DB，不产生副作用
- **server 禁止直接调用 data/cache**：server 只能通过 registry 分发到 tools

### 职责边界

| 模块 | 唯一职责 |
|------|---------|
| errors | 定义异常类型，无业务逻辑 |
| cache | `.codesense/` 目录下所有文件的 CRUD + 校验 + 失效 |
| data | 代码仓库静态分析（文件扫描、符号提取、目录依赖聚合、CodeGraph DB 查询） |
| registry | MCP 工具元数据注册 + jsonschema 参数校验 + 工具调用路由 |
| summarizer | 组合 data + cache 的输出，生成/渲染 Markdown 架构摘要 |
| server | MCP stdio 生命周期管理，启动/停止服务器 |
| tools | 每个文件一个 MCP 工具实现，解析参数后委托给 summarizer |

### 新增代码约束

- 新增 MCP 工具：在 `tools/` 下新建文件，实现 `async def xxx(args) -> list[TextContent]`，然后在 `registry/registry.py` 中注册
- 新增异常类型：继承 `errors.ToolError`，不得直接使用 `Exception`
- 缓存键命名：使用 `cache.module_key()` 和 `cache.safe_key()` 生成，不要手写路径
- 类型注解：所有公开函数必须有完整类型注解（mypy strict 模式）