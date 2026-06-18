# LLM 模块界定实验记录

> 实验时间：2026-06-17  
> 对应实施文档：`doc/Week4/LLM模块界定实现.md`  
> 目的：验证 LLM 推断的模块划分在真实项目上的准确性，记录问题与结论

---

## 1. 实验设置

| 项目 | 语言 | 规模 | 目的 |
|------|------|------|------|
| CodeSense_V1（本项目） | Python | ~30 个源文件，11 个目录 | 用自身验证，答案完全已知 |
| codegraph-main | TypeScript | ~200+ 文件，多层嵌套目录 | 跨语言验证，考验语言无关能力 |

两次实验均使用 CodeMaker + CodeSense MCP Server，提问流程：
1. 读取 `codesense://project_map` 资源
2. 对感兴趣的模块调用 `explore_module`

---

## 2. 实验一：CodeSense_V1（Python）

### 2.1 LLM 输出的模块划分

| 模块名 | 职责描述 | 主要目录 |
|--------|---------|---------|
| 数据持久化层 | 管理缓存文件的读写、校验与失效逻辑 | `src/codesense_v1/cache` |
| 数据访问层 | 封装 CodeGraph 数据库的查询、节点/边迭代与模块依赖聚合 | `src/codesense_v1/data` |
| 错误处理模块 | 定义统一的自定义异常类型与错误消息 | `src/codesense_v1/errors` |
| LLM 调用模块 | 封装对大语言模型的外部调用接口 | `src/codesense_v1/llm` |
| 工具注册与调度 | 管理工具规范定义、装饰器及 JSON Schema 错误翻译与分发 | `src/codesense_v1/registry` |
| 资源管理 | 读取项目映射等静态资源配置 | `src/codesense_v1/resources` |
| 服务层 | 构建 MCP 服务器，暴露工具列表、调用、资源列表与读取接口 | `src/codesense_v1/server` |
| 摘要生成器 | 调用 LLM 生成项目地图摘要和模块摘要，解析与渲染 Markdown | `src/codesense_v1/summarizer` |
| 工具函数层 | 实现加法、模块探索、缓存列表等具体工具 | `src/codesense_v1/tools` |
| 测试层 | 覆盖各模块的单元测试与集成测试 | `tests` |

**依赖关系（LLM 输出）**：
- LLM 调用模块 → 错误处理模块
- 工具函数层 → 工具注册与调度、摘要生成器、错误处理模块
- 摘要生成器 → LLM 调用模块、数据持久化层、数据访问层、错误处理模块
- 服务层 → 工具注册与调度、资源管理
- 资源管理 → 摘要生成器、错误处理模块

### 2.2 人工对照评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 模块数量 | ✅ 合理 | 10 个模块覆盖了所有目录，粒度适中 |
| 模块命名 | ✅ 语义准确 | "数据持久化层"、"工具注册与调度"等命名准确表达职责 |
| 职责描述 | ✅ 准确 | 10 个模块的描述与实际代码职责高度吻合 |
| 依赖关系 | ✅ 准确 | 与实际 import 关系基本一致，无明显遗漏 |
| `explore_module` 公开接口 | ✅ 无幻觉 | 修复符号传递缺陷后，接口列表基于真实 CodeGraph 符号 |

**发现的问题**：

1. **测试层目录解析异常**：输出为 `覆盖各模块的单元测试与集成测试`（description 被误放入 directory 列）。原因是 `tests` 目录本身是顶层目录，LLM 在竖线分隔的文本中可能对 `tests` 的对应描述出现列混淆。对功能无影响，但说明 prompt 还有改进空间。

2. **第一版实现（JSON 格式）失败**：首次尝试时因 LLM 输出 JSON 遗漏逗号导致两次解析均失败，需要重新提问才成功。改为竖线分隔文本格式后解决。

---

## 3. 实验二：codegraph-main（TypeScript）

### 3.1 LLM 输出的模块划分

| 模块名 | 职责描述 | 主要目录 |
|--------|---------|---------|
| 核心库 | CodeGraph 主类、错误类型、文件系统工具与日志接口 | `src` |
| 测试工具集 | 测试辅助函数（临时目录、进程管理、文件感应） | `__tests__` |
| 安装脚本 | 加入语言支持包、验证、更新包脚本 | `scripts` |
| 网站组件库 | 网站 UI 组件 | `site/src/components` |
| 站点工具 | 数据格式化、星标计数函数 | `site/src/lib` |
| 页面路由 | 网站页面路由与布局 | `site/src/pages` |
| 遥测工作者 | 事件验证、清理、转发至 PostHog | `telemetry-worker/src` |

**依赖关系（LLM 输出）**：
- 测试工具集 → 核心库
- 网站组件库 → 站点工具
- 页面路由 → 站点工具 + 网站组件库

### 3.2 `explore_module("核心库")` 输出

LLM 输出了 **9 大类公开接口**，含：
- `CodeGraph`（主类）
- `ContextBuilder`, `createContextBuilder`
- `DatabaseConnection`, `QueryBuilder`, `createDatabase`
- `GraphQueryManager`, `GraphTraverser`
- `ExtractionOrchestrator`, `TreeSitterExtractor`
- `MCPServer`, `MCPEngine`, `MCPSession`, `ToolHandler`, `Daemon`
- `ReferenceResolver`, `createResolver`
- 错误类型：`CodeGraphError`, `FileError`, `ParseError`, `DatabaseError` 等 9 种
- 工具类：`FileLock`, `Mutex`, `MemoryMonitor`, `Telemetry`, `FileWatcher`, `LRUCache`

还输出了 **7 大子系统**的内部结构（`context/`, `db/`, `extraction/`, `graph/`, `mcp/`, `resolution/`, `sync/`）和 20+ 语言/框架支持的说明。

### 3.3 人工对照评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 语言无关性 | ✅ 通过 | TypeScript 项目无 `__init__.py`，改造后完全正常工作 |
| 模块划分合理性 | ✅ 合理 | `src`（核心）/ `__tests__`（测试）/ `scripts`（工具链）/ `site`（官网）/ `telemetry-worker`（独立服务）的划分符合 monorepo 常见结构 |
| 接口真实性 | ✅ 无幻觉 | 所列 TypeScript 类/函数均来自 CodeGraph 符号表，与实际 exports 一致 |
| 子系统描述 | ✅ 准确 | 20+ 语言提取器、20+ 框架解析器的描述与仓库实际内容吻合 |
| 依赖关系 | ✅ 准确 | 测试、脚本、网站均依赖核心库，符合实际 |

**发现的问题**：

1. **`src` 目录粒度粗**：codegraph-main 的 `src` 包含了 `extraction/`, `mcp/`, `graph/`, `resolution/` 等多个逻辑上独立的子系统，LLM 将它们合并为单个"核心库"模块。从工程角度这些子系统可以各自成模块，但 LLM 做了保守的合并——在 `explore_module` 层面通过子系统描述弥补了这一点。

2. **`site` 目录被拆成 3 个模块**（网站组件库、站点工具、页面路由），而不是合并为"官网"一个。这是合理的细粒度划分，但也可以接受合并为一个。说明 LLM 对"模块粒度"的判断不唯一，可通过 prompt 调整。

---

## 4. 结论

### 4.1 什么情况下 LLM 模块划分有效

- **中等规模项目**（10-200 个源文件）：粒度掌握较好，命名准确
- **模块边界清晰的项目**：有 monorepo 结构或明确的目录分层时，结果质量高
- **跨语言项目**：Python、TypeScript 均正常工作，符合语言无关设计目标
- **接口描述**（`explore_module`）：基于真实符号表，无幻觉，质量稳定

### 4.2 什么情况下效果有限

- **超大单目录**（如 `src` 包含数十个子系统）：LLM 倾向合并为单一模块，丢失内部结构。后续可通过"递归 explore"弥补
- **粒度不稳定**：同一项目重新生成时模块名和边界可能略有不同（LLM 输出非确定性）。缓存机制在 DB hash 不变时可固定划分
- **目录-描述列混淆**：偶发解析错误（实验一的测试层）。说明 prompt 和解析鲁棒性仍有改进空间

### 4.3 与原 `__init__.py` 方案的对比

| 对比项 | 原方案（Python 包检测） | 新方案（LLM 推断） |
|--------|----------------------|-----------------|
| 语言支持 | Python only | 任意语言 ✅ |
| 模块粒度 | 与 Python 包对齐（细） | LLM 自主判断（可粗可细） |
| 稳定性 | 确定性（`__init__.py` 有就成功） | 概率性（LLM 每次可能略有不同） |
| 描述质量 | 无（纯结构） | 有语义描述 ✅ |
| 依赖新项目配置 | 需要 `__init__.py` | 无需任何配置 ✅ |

---

## 5. 后续优化方向

1. **Prompt 调整**：加强"description 不要出现在 directory 列"的约束，防止列混淆
2. **递归 explore**：支持对大目录（如 `src`）进一步展开子模块（Stretch Goal）
3. **粒度控制**：在 prompt 中加入"每个模块不超过 N 个文件"等约束，引导细粒度划分
4. **人工修正机制**：允许用户编辑 `modules_index.json` 修正 LLM 划分（Stretch Goal）
