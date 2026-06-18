# CodeSense 实习生项目计划

## 项目概述

一个 Python MCP Server，读取 CodeGraph 已构建的代码知识图谱（符号、调用关系、文件依赖），用 LLM 把这些结构数据加工成架构层面的语义描述，再以 MCP Resource（打开项目时自动注入架构概览）和 MCP Tool（模块级别的整体理解）的形式给到 AI Agent。核心目标是让 AI 读代码的时候就能知道"这段代码在系统里处于什么位置、跟谁有关"，不需要它自己去一步步探索。

## 问题背景

AI 编程助手在修改代码时存在"浅层理解"问题：

- 只从关键词出发做点状搜索（grep/glob），缺乏全局视角
- 不理解模块边界和分层结构
- 不主动探索依赖关系，靠函数名猜测功能
- 即使有 CodeGraph 等工具，AI 仍可能因"惰性"不去调用

根本原因：AI 不缺工具（grep、LSP、CodeGraph 都有），缺的是**不需要主动性就能获得的架构认知**。

## 解决方案

### 核心思路

在 CodeGraph 的结构数据之上加一层语义理解层：

- CodeGraph 知道"谁调用谁"（结构）
- CodeSense 知道"这意味着什么"（语义）

### 工具设计

| 工具               | 类型           | 功能                  | AI 使用方式      |
| ---------------- | ------------ | ------------------- | ------------ |
| `project_map`    | MCP Resource | 项目整体架构概览            | 被动注入，AI 无需调用 |
| `explore_module` | MCP Tool     | 模块级整体理解（接口、内部结构、边界） | AI 主动调用      |

### 与现有工具的分工

```
抽象度高 ──────────────────────────────────────── 抽象度低

project_map → explore_module → codegraph_explore → codegraph_callers → grep/read_file
  全局鸟瞰      模块面           符号+邻域          单点关系          精确文本
 (被动注入)    (面级理解)        (点到邻域)         (点查询)          (原始文本)
```

- **project_map**：回答"项目有几个模块、整体怎么分层"
- **explore_module**：回答"这个模块对外暴露什么、内部怎么组织、跟谁交互"
- **codegraph_explore**：回答"这几个符号怎么关联、调用链是什么"
- **grep/read_file**：回答"这行代码具体写了什么"

### 持久化数据

CodeSense 会在项目中生成 `.codesense/` 目录：

```
.codesense/
├── project_map.md              # 项目整体架构摘要
├── modules/
│   ├── src_auth.json           # auth 模块的结构 + LLM 摘要
│   ├── src_user.json
│   └── src_api.json
└── meta.json                   # 生成时间、CodeGraph DB hash
```

使用 Lazy 检查策略：AI 调用工具时检查 CodeGraph DB 是否有变化，有变化才重新生成对应模块摘要。

## 技术架构

```
┌──────────────────────────────────────────────┐
│              AI Agent (Claude/Cursor)         │
│  ├── CodeGraph MCP (已有，符号级查询)          │
│  └── CodeSense MCP (新做，架构级理解)          │
└──────────────┬───────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│         CodeSense MCP Server (Python)         │
│                                               │
│  ┌─────────────┐  ┌──────────────────────┐   │
│  │ project_map │  │   explore_module     │   │
│  │ (Resource)  │  │   (Tool)             │   │
│  └──────┬──────┘  └──────────┬───────────┘   │
│         │                    │                │
│  ┌──────▼────────────────────▼───────────┐   │
│  │         Data Layer                     │   │
│  │  - 读 CodeGraph SQLite DB              │   │
│  │  - 目录结构分析                          │   │
│  │  - 跨模块依赖聚合                        │   │
│  └──────────────────┬────────────────────┘   │
│                     │                         │
│  ┌──────────────────▼────────────────────┐   │
│  │         LLM Layer                      │   │
│  │  - 架构摘要生成                          │   │
│  │  - 模块描述生成                          │   │
│  │  - 缓存管理                             │   │
│  └───────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────┐
│   .codegraph/codegraph.db (CodeGraph 生成)    │
│   .codesense/ (CodeSense 生成的缓存)          │
└───────────────────────────────────────────────┘
```

## 技术栈

- **语言**：Python 3.11+
- **MCP 框架**：mcp (Python SDK)
- **数据库**：SQLite（读 CodeGraph 的 DB）
- **LLM**：OpenAI API / Claude API
- **依赖管理**：uv 或 pip

## 周计划（6 周）

### Week 1：认知建立 + CodeGraph 体验

**目标**：理解 AI coding 的现状问题，亲身体验 CodeGraph 的价值和局限

测试项目：使用 CodeGraph 仓库本身（~15k 行 TypeScript，有清晰的模块划分：extraction、resolution、db、mcp、sync）

任务：

- [x] 学习 MCP 协议基础概念（Tool、Resource、Instruction 的区别和用途，Server/Client 交互模型）

- [x] 阅读 CodeGraph 文档，梳理其模块划分和数据流（源码 → AST 解析 → 符号提取 → 引用解析 → SQLite → MCP 查询）

- [x] 逐一调研 CodeGraph 的 CLI 命令和 MCP 工具，记录每个工具能做什么、输入输出是什么、粒度到哪一级

- [x] 设计一个跨模块修改任务（如"加一个新 CLI 命令"），分别在无 CodeGraph 和有 CodeGraph 环境下让 AI 完成，记录差异

- [x] 基于实验和调研，明确 CodeGraph 的能力边界：能回答什么问题、不能回答什么问题（特别是模块级/架构级的问题）

交付物：

- [x] CodeGraph 原理理解文档（能讲清楚：索引流程、数据模型、查询原理、局限性）
- [x] 对比实验报告（有/无 CodeGraph 的 AI 行为差异）
- [x] 差距分析文档（CodeGraph 能力边界 + CodeSense 设计动机）

### Week 2：项目搭建 + Data Layer

**目标**：搭建 CodeSense 项目骨架，能从 CodeGraph DB 提取结构数据

任务：

- [x] 搭建 Python 项目（结构、依赖管理、基础配置）
- [x] 学习 Python MCP SDK，跑通最简 MCP Server（能被 agent 连接）
- [x] 实现 Data Layer：从 CodeGraph DB 查询文件列表、目录结构、跨目录依赖、模块间调用关系
- [x] 验证：能对 CodeGraph 仓库输出"哪些目录依赖哪些目录"的结构化数据

交付物：

- [x] 可运行的 MCP Server 骨架（agent 能连接）
- [x] Data Layer 能输出项目的模块依赖关系数据

### Week 3：project_map + explore_module 实现

**目标**：实现两个核心功能

任务：

- [x] 设计 LLM prompt（输入结构数据 → 输出架构摘要）
- [x] 实现 project_map：LLM 调用 + 缓存 + 作为 MCP Resource 暴露
- [x] 实现 explore_module：模块边界检测、模块内符号提取、LLM 生成模块描述
- [x] .codesense/ 目录持久化
- [x] 在 CodeGrpah 仓库上测试生成质量，迭代 prompt

交付物：

- [x] project_map Resource 可工作
- [x] explore_module Tool 可工作
- [x] 在 CodeGraph仓库上生成的摘要准确且有用

### Week 4：Skill + MCP Instructions + 集成测试

**目标**：让 AI Agent 实际按预期使用 CodeSense

任务：

- [x] 编写 MCP Server Instructions（引导 AI 理解工具分工）
- [x] 编写 Skill 文件（定义"先看全局→再看模块→再看细节"的工作流）
- [x] 端到端集成测试：接入 CodeMaker
- [x] 观察 AI 行为：是否使用 explore_module？
- [x] 根据观察调整 instructions 和 skill 措辞

交付物：

- [x] Skill 文件
- [x] MCP Server Instructions
- [x] 集成测试记录（AI 行为观察日志）

### Week 5：效果评估 + 对比实验

**目标**：证明/证伪 CodeSense 的实际效果

任务：

- [ ] 设计对比实验：选 2-3 个跨模块修改任务，分三组跑：
  - 纯 grep/read（无 CodeGraph、无 CodeSense）
  - 有 CodeGraph、无 CodeSense
  - 有 CodeGraph + CodeSense
- [ ] 记录指标：AI 工具调用次数、是否正确识别模块边界、修改是否破坏依赖、代码是否符合现有模式
- [ ] 分析 project_map 和 explore_module 对 AI 决策的实际影响
- [ ] 根据实验结果调优 prompt 和 instructions（最后一轮迭代）
- [ ] 基本错误处理（CodeGraph DB 不存在时给清晰提示即可，不追求完美）

交付物：

- [ ] 三组对比的实验数据和分析
- [ ] 结论：CodeSense 在什么场景有效、什么场景无效

### Week 6：总结 + 汇报

**目标**：整理项目成果，完成汇报

任务：

- [ ] 整理项目文档（README、安装指南、设计思路）
- [ ] 制作汇报 Slides（HTML），逻辑线：
  1. AI coding 现状问题（Week 1 的实验数据）
  2. CodeGraph 做了什么、怎么做的、为什么不够
  3. CodeSense 的设计思路和实现
  4. 效果评估数据（三组对比）
  5. 结论和展望
- [ ] 内部 Demo 演示

交付物：

- [ ] 项目完整文档
- [ ] 汇报 Slides
- [ ] Demo 演示

## Stretch Goals（有额外时间再做）

- [x] **LSP Server 方案调研** — 探索能否用 LSP Server 替代 CodeGraph 作为数据源，实现相同功能
- [x] **CodeMap 方案调研** — 探索能否基于公司内部的 CodeMap 来实现相同功能，对比与 CodeGraph 方案的优劣
- [ ] **CodeGraph MCP 代理** — 合并为一个 server，用户只需配置一个 MCP
- [ ] **Watch 机制** — 守护进程监听变化，实时更新 .codesense 缓存
- [ ] **多粒度 explore** — 支持 explore_module 的递归展开（子模块）
- [ ] **交互式修正** — 人可以修正 LLM 生成的摘要，修正后优先使用

## 成功标准

1. **可工作**：MCP Server 能正常启动，AI Agent 能连接并使用
2. **有产出**：在真实项目上生成准确的架构摘要和模块描述
3. **有数据**：完成对比评估，能用数据说明效果（即使效果有限）
4. **有思考**：能清楚解释设计决策、权衡取舍、以及项目的局限性

## 风险和应对

| 风险                     | 影响       | 应对                            |
| ---------------------- | -------- | ----------------------------- |
| LLM 生成的摘要不准确           | 误导 AI    | 多项目测试 + prompt 迭代，实在不行加人工修正机制 |
| AI 不使用 explore_module  | 核心价值无法体现 | 重点打磨 instructions 和 skill 措辞  |
| CodeGraph DB schema 变化 | 查询失败     | 锁定测试用的 CodeGraph 版本           |
| 大项目生成摘要过慢/过贵           | 体验差      | 分层生成（先 top-level，按需展开子模块）     |

## 实习生能力收获

- Python Web 服务开发
- MCP 协议理解（AI Agent 生态核心协议）
- LLM Prompt Engineering（设计、迭代、评估）
- SQLite 数据查询和建模
- AI 产品设计思维（如何改变 AI 行为，而非仅提供数据）
- 技术方案评估能力（分析可行性、做权衡取舍）
