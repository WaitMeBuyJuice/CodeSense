## 问题 1：MCP Resource（`project_map`）的使用方式

### 背景

项目计划原本设计 `project_map` 为 **被动注入**——AI 连上 Server 时自动注入到上下文，无需调用。

### 当前实现

MCP 协议里 Resource 是 **pull-based**（客户端驱动），服务端无法强制推送，"自动注入"是 MCP 客户端的决策，CodeMaker 实测下来是 Agent 主动发起 `resources/read` 才拿到内容。

`project_map` 已改为 **主动调用** 模式：服务端只暴露资源清单，客户端读到 description 后自行决定是否调用 `resources/read`，与 Tool 的触发逻辑一致。

### 替代方案：服务端启动时 LLM 生成 → 嵌入 MCP Server Instructions 推送

理论上仍可以实现"被动注入"效果，服务端启动时先调 LLM 生成 `project_map`，把内容拼进 MCP Server Instructions 一起发给客户端。

但该方案存在以下问题：

| 问题      | 说明                                              |
| ------- | ----------------------------------------------- |
| 内容静态化   | 启动时生成`project_map`嵌入Instructions后，运行期项目代码变更无法反映 |
| 语义混淆    | Instructions 本身的职责是"如何使用工具"，混入项目架构内容会污染语义       |
| 生命周期不匹配 | Instructions 是会话级元信息，`project_map` 是项目级动态内容     |
| 启动阻塞    | 服务端启动时调 LLM 会阻塞首次握手，影响连接体验                      |
| 违背协议设计  | MCP 协议明确 Resource 是客户端驱动，绕过协议会埋下兼容性风险           |

### 待确认

- 是否认可保留 **主动调用** 模式（与协议一致、内容动态、与 Tool 行为统一）？

### ✅ 已确认（2026-06-17）

保留 **主动调用** 模式，与 MCP 协议一致，与 Tool 行为统一。

---

## 问题 2：Week 5 实验中 Skill 是否开启（Skill在CondeSense中的意义？）

### 背景

Week 4 已完成 `codesense-workflow` Skill 的开发，工作流（全局架构 → 模块接口 → 代码细节）和触发条件经测试验证有效。

### Week 5 任务约束

Week 5 要做三组对比实验：

- 组 1：纯 grep / read（无 CodeGraph、无 CodeSense）
- 组 2：有 CodeGraph、无 CodeSense
- 组 3：有 CodeGraph + CodeSense

### 待确认

- 组 3 实验时，`codesense-workflow` Skill 是否开启？
  - **开启**：测的是"CodeSense 完整产品形态（MCP + Skill）"的效果，最贴近真实使用
  - **不开启**：测的是"只靠 MCP Instructions + 工具 description"的效果，能隔离出 Skill 的边际贡献
  - **两组都做**：分成"组 3a 不开 Skill / 组 3b 开 Skill"，能定量刻画 Skill 的增益，但工作量翻倍

### ✅ 已确认（2026-06-17）

组 3 **不开启 Skill**。

重点探究：在无 Skill 的情况下，`project_map` 和 `explore_module` 是如何通过各自的 description 协作触发的——即 Agent 仅凭 MCP Instructions + 工具/资源 description 本身，能否形成"全局概览 → 模块探索"的自然工作流。

---

## 问题 3：模块的语义定义与通用性

### 现状

| #   | 事实                                                                                        |
| --- | ----------------------------------------------------------------------------------------- |
| 1   | 当前 `explore_module` **仅识别 Python 包**（依赖 `__init__.py` 是否存在）                               |
| 2   | Week 5 验证目标之一 codegraph-main 是 **TypeScript 项目**，无 `__init__.py`，`explore_module` 直接报错不可用 |
| 3   | CodeGraph 自身**没有"模块"概念**，最大粒度只到文件级（function / class / file）                               |
| 4   | CodeGraph 走的是  AST 解析路线，所有语言抽出"符号 + 边"的统一模型，刻意不引入模块层                                      |

### 问题与可选方案

#### A. 模块的通用定义是什么？

`explore_module` 是否要扩展到 **"任意代码组织单元"**（一个文件夹、若干文件）？还是保持 Python 包定义？

#### B. 若要支持非 Python 项目，模块识别规则怎么定？

#### 三种方案：

| 方案             | 规则                                                                                          | 优点                 | 缺点                         |
| -------------- | ------------------------------------------------------------------------------------------- | ------------------ | -------------------------- |
| B1：基于目录文件数     | 含至少 N 个源文件的目录 = 模块                                                                          | 完全语言无关             | 粒度可能不准（`src/` 既是模块也是模块的父级） |
| B2：每语言一套规则     | Python→`__init__.py` / TS→`package.json` 或 `index.ts` / Go→`go.mod` / Java→`package-info` 等 | 贴近各语言生态约定，模块边界更准   | 每加一种语言要写一套规则；混合语言项目需兜底     |
| B3：基于import 推断 | 内部 import 多、跨目录 import 少的目录 = 模块                                                            | 完全语言无关，不依赖任何文件命名约定 | 算法主观（阈值难定）、可解释性差，工作量大      |

### 待确认

1. 项目目标到底是 "**做出 Python 项目能用的工具**" 还是 "**做出语言通用的架构理解工具**"？
2. 如果要做通用，那采用哪种方案？
3. 如果只做 Python，Week 5 是否调整验证对象，**只在 CodeSense 上跑实验**，放弃 codegraph-main？

### ✅ 已确认（2026-06-17）

目标扩展为**语言通用的架构理解工具**。

**模块定义方式（暂定）**：不依赖语言级约定文件（`__init__.py` / `package.json` 等），改由 **LLM 来界定模块边界**。
具体思路：将 CodeGraph 提供的文件列表、符号信息、依赖关系作为上下文输入，通过提示词引导 LLM 输出"整体架构描述 + 模块划分 + 各模块的内容与作用"，以此替代基于文件命名约定的硬编码检测逻辑。

**后续需要做的验证实验**：使用 CodeGraph 的结构数据 + 提示词，实验 LLM 生成整体架构、识别模块边界、描述模块作用的效果，评估该方案在 Python 项目（CodeSense_V1）和 TypeScript 项目（codegraph-main）上的可行性与质量。
