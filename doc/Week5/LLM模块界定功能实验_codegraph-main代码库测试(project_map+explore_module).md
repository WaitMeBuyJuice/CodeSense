## 来自你的消息
我要看codesense://project_map
<environment_details>
# Current Time
6/17/2026, 6:35:27 PM (Asia/Shanghai, UTC+8:00)

# Mode
Currently in **build** mode. Write/edit tools are enabled. Disregard any previous "ask (read-only) mode" notice from earlier messages — that mode is no longer active.
</environment_details>


## 来自 CodeMaker 的消息
项目架构概览：

## 模块列表

| 模块 | 职责 | 主要目录 |
|------|------|---------|
| **核心库** | CodeGraph 主类、错误类型、文件系统工具与日志接口 | `src` |
| **测试工具集** | 测试辅助函数（临时目录、进程管理、文件感应） | `__tests__` |
| **安装脚本** | 加入语言支持包、验证、更新包脚本 | `scripts` |
| **网站组件库** | 网站 UI 组件 | `site/src/components` |
| **站点工具** | 数据格式化、星标计数函数 | `site/src/lib` |
| **页面路由** | 网站页面路由与布局 | `site/src/pages` |
| **遥测工作者** | 事件验证、清理、转发至 PostHog | `telemetry-worker/src` |

## 模块依赖关系

- 测试工具集 → 核心库
- 网站组件库 → 站点工具
- 页面路由 → 站点工具 + 网站组件库

需要深入探索某个模块？用 `explore_module` 工具即可。

## 来自你的消息
深入探索核心库
<environment_details>
# Current Time
6/17/2026, 6:36:24 PM (Asia/Shanghai, UTC+8:00)

# Mode
Currently in **build** mode. Write/edit tools are enabled. Disregard any previous "ask (read-only) mode" notice from earlier messages — that mode is no longer active.
</environment_details>


## 来自 CodeMaker 的消息
核心库全貌：

## 架构概要

**一句话**：定义 CodeGraph 主类、错误类型、文件系统工具与日志接口。**整个项目最底层模块**，被所有其他模块依赖。

---

## 对外接口（9大类）

| 分类 | 关键符号 |
|------|---------|
| **主入口** | `CodeGraph` (class) |
| **上下文构建** | `ContextBuilder`, `createContextBuilder` |
| **数据库** | `DatabaseConnection`, `QueryBuilder`, `createDatabase` |
| **图查询** | `GraphQueryManager`, `GraphTraverser` |
| **代码提取** | `ExtractionOrchestrator`, `TreeSitterExtractor` |
| **MCP 服务** | `MCPServer`, `MCPEngine`, `MCPSession`, `ToolHandler`, `Daemon` |
| **引用解析** | `ReferenceResolver`, `createResolver` |
| **错误类型** | `CodeGraphError`, `FileError`, `ParseError`, `DatabaseError`, `SearchError`, `VectorError`, `ConfigError`, `NotIndexedError`, `PathRefusalError` |
| **工具类** | `FileLock`, `Mutex`, `MemoryMonitor`, `Telemetry`, `FileWatcher`, `LRUCache` |

---

## 内部结构（7大子系统）

```
src/
├── index.ts              # CodeGraph 主类
├── errors.ts             # 错误类型 + 日志接口
├── utils.ts              # 通用工具
├── types.ts              # 共享类型
├── context/              # 上下文构建 (AI 问答场景)
├── db/                   # SQLite 数据库层 (连接、查询、迁移)
├── extraction/           # 代码提取引擎
│   ├── languages/        # 20+ 语言提取器 (TS/Python/Java/Go/Rust...)
│   └── *-extractor.ts    # 框架提取器 (Vue/Astro/Svelte...)
├── graph/                # 图查询 + BFS/DFS遍历
├── mcp/                  # MCP 协议实现 (服务器/引擎/会话/守护进程)
├── resolution/           # 引用解析
│   └── frameworks/       # 20+ 框架解析器 (React/Vue/NestJS/Laravel...)
├── search/               # 查询解析
├── sync/                 # 文件监听 + Git钩子
├── installer/            # 多目标安装 (Claude/Cursor/Gemini...)
└── bin/                  # CLI 入口
```

---

## 依赖关系

- **上游**：无外部依赖（最底层）
- **下游**：`__tests__`、`scripts`、`site`、`telemetry-worker` 全部依赖它

需要我深入探索某个子系统（如 `extraction`、`mcp`、`graph`）或查看具体文件？