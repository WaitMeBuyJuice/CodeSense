# Week 4 需求文档

> 生成时间：2026-06-16
> 参考：`doc/vibecoding_rules/codesense-intern-project-plan.md` Week 4 章节

---

## 1. 背景与目标

Week 3 已实现 `project_map`（MCP Resource）和 `explore_module`（MCP Tool），功能层面完备。
Week 4 目标：**让 AI Agent 实际按预期使用 CodeSense**，即"先看全局 → 再看模块 → 再看细节"的工作流。

核心问题：工具存在不代表 AI 会用。需要通过 Instructions + Skill 两层引导，改变 AI 的行为模式。

---

## 2. 交付物清单

| #   | 交付物                     | 形式                      | 路径                                  |
| --- | ----------------------- | ----------------------- | ----------------------------------- |
| 1   | MCP Server Instructions | Python 代码（注入 Server 握手） | `src/codesense_v1/server/server.py` |
| 2   | CodeMaker Skill 文件      | Claude Skill XML 格式     | `doc/Week4/codesense_skill.md`      |
| 3   | 集成测试观察日志模板              | Markdown                | `doc/Week4/integration_test_log.md` |

---

## 3. 功能需求

### 3.1 MCP Server Instructions

**目标**：AI 连上 CodeSense Server 后，无需额外说明就能理解工具分工。

**内容要求**：

- 简洁引导型（3-5 句）
- 说明 `project_map`（Resource，被动注入）和 `explore_module`（Tool，主动调用）的定位
- 说明与其他工具（codegraph、grep/read_file）的抽象层次关系
- 不写操作步骤，让 AI 自行判断何时调用

**实现位置**：

```python
# src/codesense_v1/server/server.py
server = Server(name=SERVER_NAME, version=SERVER_VERSION, instructions="...")
```

**验收标准**：

- Instructions 字符串非空，内容符合上述要求
- `uv run pytest -q` 仍 111+ passed（不破坏现有测试）
- `mypy --strict` + `ruff check` 零错误

### 3.2 CodeMaker Skill 文件（Claude Skill 格式）

**目标**：用户激活 Skill 后，AI 在修改代码场景下主动遵循"全局→模块→细节"的探索顺序。

**格式**：Claude Skill XML，参考 CodeMaker `<activated_skill>` 标签约定：

```xml
<skill name="codesense-workflow">
<instructions>
...工作流描述...
</instructions>
</skill>
```

**内容要求**：

- 触发条件：当需要理解/修改代码时
- 步骤 1：读 `project_map` Resource，获取项目全局架构（通常已被动注入，确认已读）
- 步骤 2：对涉及的模块调用 `explore_module`，理解模块边界和对外接口
- 步骤 3：根据上述上下文，再 grep/read_file 精确定位具体代码
- 明确说明：修改前必须完成步骤 1-2，不得跳过直接 grep

**保存路径**：`doc/Week4/codesense_skill.md`

**验收标准**：

- XML 格式合法，`<instructions>` 内容清晰可读
- 步骤逻辑符合"抽象度从高到低"的工具分工设计

### 3.3 集成测试观察日志模板

**目标**：为用户提供结构化的观察记录模板，方便记录 AI 行为、对比是否按预期使用工具。

**内容要求**：

- 测试场景：在 CodeSense_V1 项目上提出跨模块修改任务
- 记录项：任务描述、AI 调用工具序列、是否使用 `explore_module`、决策质量评估
- 对比维度：激活 Skill 前 vs 后
- 格式：每次测试一条记录，便于积累

**保存路径**：`doc/Week4/integration_test_log.md`

**验收标准**：

- 模板结构清晰，用户填写时无歧义
- 包含至少 2 个预设测试场景（具体任务描述）

---

## 4. 非功能需求

| 项    | 要求                                                         |
| ---- | ---------------------------------------------------------- |
| 代码规范 | `mypy --strict` 零错误，`ruff check` 零警告                       |
| 测试   | 现有 111 个测试全部通过，Instructions 变更不需新增测试（非业务逻辑）                |
| 兼容性  | 现有 MCP 连接行为不变，Instructions 仅为附加信息                          |
| 语言   | Instructions 和 Skill 均用**英文**（AI 处理英文 system prompt 效果更稳定） |

---

## 5. 明确不做的事

- 不新增 MCP Tool 或 Resource
- 不修改 Data Layer / LLM / Cache 逻辑
- 不做自动化集成测试（由用户手动观察）
- Skill 文件格式以 Claude Skill XML 为准，不做 CodeMaker 私有格式适配

---

## 6. 任务依赖关系

```
T1: MCP Server Instructions（改 server.py）
  └─ 无依赖

T2: Skill 文件（新建 doc/Week4/codesense_skill.md）
  └─ 无依赖（与 T1 独立）

T3: 集成测试日志模板（新建 doc/Week4/integration_test_log.md）
  └─ 依赖 T1、T2 完成（需要知道 Instructions 和 Skill 内容）
```

---

## 7. 验收流程

1. `uv run pytest -q` → 111+ passed
2. `uv run mypy --strict src/codesense_v1/server/server.py` → 0 errors
3. `uv run ruff check src/codesense_v1/server/server.py` → 0 warnings
4. 人工审查 Instructions 内容是否简洁且准确描述工具分工
5. 人工审查 Skill 文件步骤是否清晰且可操作
6. 用户按日志模板进行实际集成测试，观察 AI 行为
