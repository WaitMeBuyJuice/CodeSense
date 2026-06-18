# Week 4 — 描述对齐与 MCP Resource 行为修正

## 背景

在 Week 4 集成测试中观察到两个问题：

1. **Skill 触发不稳定**：用户给出"先了解某模块作用、再修改其策略"这类组合任务时，Agent 没有激活 `codesense-workflow` skill，直接走 grep 定位。
2. **`project_map` 行为偏离设计**：项目计划文档原本设计为"被动注入，AI 无需调用"，但实测下来，Agent 是**主动**调用 `resources/read` 才拿到内容的，并非连接时自动注入。

由此引出两条工作主线：

- **描述对齐**：把 Skill / Tool / Resource / SERVER_INSTRUCTIONS 的描述统一改造成"适用场景 / 不适用场景"结构，提高触发准确度。
- **MCP Resource 行为修正**：澄清"自动注入"在 MCP 协议层面无法由服务端实现，统一全项目口径为"Agent 主动读取"。

---

## 一、关键技术发现：MCP Resource 不是被动注入

### MCP 协议规范

Resource 在 MCP 协议里是 **pull-based** 的，协议只规定三个接口：

| 接口                                | 方向              | 说明                  |
| --------------------------------- | --------------- | ------------------- |
| `resources/list`                  | Client → Server | 获取可用资源清单            |
| `resources/read`                  | Client → Server | 读取某个资源内容            |
| `notifications/resources/updated` | Server → Client | 通知资源变更（客户端自行决定是否重读） |

**协议没有任何"服务端推送内容到 AI 上下文"的机制。** 是否实现"自动注入"完全是 MCP 客户端的产品决策，服务端无法强制。

### CodeMaker 的实际行为

实测验证：用户问"你能看到 codesense 提供的 project_map 资源内容吗"时：

- CodeMaker 客户端发起 `resources/read codesense://project_map` 请求
- 这是 Agent 根据上下文判断"需要读取"后主动发起的，**不是连接时自动读取**
- 结论：CodeMaker 支持 Resource 读取，但触发方式是 **Agent 主动**

### 这与原设计的偏差

项目计划文档（`doc/vibecoding_rules/codesense-intern-project-plan.md`）工具设计表里写：

| 工具               | 类型           | AI 使用方式      |
| ---------------- | ------------ | ------------ |
| `project_map`    | MCP Resource | 被动注入，AI 无需调用 |
| `explore_module` | MCP Tool     | AI 主动调用      |

**实际能落地的状态是：两者都由 Agent 根据 description 主动决定是否调用**，区别只剩下：

- 协议层面：`resources/read` vs `tools/call`
- 语义约定：数据（无副作用）vs 操作（可能有副作用）

### 为什么不强行实现"被动注入"

考虑过三种实现自动注入的方案：

| 方案                        | 说明                                      | 评估                                        |
| ------------------------- | --------------------------------------- | ----------------------------------------- |
| A. 嵌入 SERVER_INSTRUCTIONS | 启动时把 project_map 内容拼进 `instructions` 字段 | ❌ 启动阻塞 LLM 调用、内容静态无法刷新、混淆 instructions 语义 |
| B. 依赖客户端自动读取              | 等 CodeMaker 实现"连接后自动读取 Resource"        | ⚠️ 需跨团队推动                                 |
| C. 维持现状                   | Agent 通过 description 主动决定               | ✅ 已工作、代价最小                                |

**当前选 C，作为终态。** 真正的自动注入留作 stretch goal。

---

## 二、描述对齐：从功能罗列到场景导向

### 改造原则

所有描述统一改成：

1. **一句话功能说明**（保持简洁）
2. **适用场景**（什么时候用）
3. **不适用场景**（什么时候别用，并指向替代方案）
4. **参数/必要约束**（仅 Tool 需要）

这样 Agent 能直接根据用户意图匹配描述，决策更准确。

### 修改清单

#### 1. Skill: `codesense-workflow`

**位置**：`.codemaker/skills/codesense-workflow/SKILL.md`

**改动一：description**

迭代过程：

1. 旧版描述太宽泛，"修改现有代码"会导致即使是"改第 42 行"这种明确任务也激活 Skill
2. 第一次修改增加"已知具体路径/符号时不激活"的边界
3. Week 4 集成测试发现：当用户问"模块作用 + 改其策略"这类组合任务时仍未激活 Skill。补充触发信号词

**最终版**：

```
代码架构探索工作流。适用场景：探索代码库、理解某模块结构、询问某模块的作用或策略、定位某个功能归属模块、在理解某模块后对其进行修改。不适用场景：用户已明确给出文件路径、行号或具体符号名。激活后引导按"全局架构 → 模块接口 → 代码细节"三步走。
```

**改动二：Step 1 内容**

去掉过时的"auto-injected into your context. You already have it"措辞，改为"Read it via the MCP `resources/read` mechanism"，与协议事实对齐。

**改动三：Examples**

把"（已注入的 project_map）确认 cache 模块位置"改为"读取 project_map → 确认 cache 模块位置"。

#### 2. Tool: `explore_module`

**位置**：`src/codesense_v1/tools/explore_module.py`

**旧版**：只描述功能，缺触发边界。

**最终版**：

```
返回指定模块的架构理解：一句话描述、对外接口、内部子模块、依赖模块。
适用场景：询问某模块的作用或策略、改动某模块前需先了解其结构和接口契约、理解模块间依赖关系。
不适用场景：仅需定位模块位置（用 project_map 即可）、已知确切文件路径或符号名（直接 grep/read_file）。
参数：module_path 为相对于 CODESENSE_PROJECT_ROOT 的目录路径，如 'src/auth'，目录中须存在 __init__.py。
```

关键改进：明确把 `project_map` 和 `grep/read_file` 的边界写进不适用场景，避免 Agent 用 `explore_module` 解决用更轻量工具就能办到的事。

#### 3. Resource: `project_map`

**位置**：`src/codesense_v1/resources/project_map.py`

**最终版**：

```python
RESOURCE_DESCRIPTION: str = (
    "项目整体架构概览（模块列表、一句话描述、跨模块依赖关系）。"
    "适用场景：初次接触代码库时定向、定位某个功能属于哪个模块、判断改动会影响哪些模块。"
    "不适用场景：需要了解模块内部结构或接口细节（改用 explore_module）。"
)
```

中间一版曾写过"已自动注入上下文，无需主动调用"，确认 MCP 协议无此机制后删除，避免误导 Agent。

#### 4. SERVER_INSTRUCTIONS

**位置**：`src/codesense_v1/server/server.py`

两处过时表述被修正：

- `project_map (Resource, auto-injected)` → `project_map (Resource)`
- `You already have this in context — consult it...` → `Read this resource whenever...`
- `consult project_map (already in context)` → `read project_map resource first`

---

## 三、最终一致性核对表

| 文件                                                               | 关键描述                             | 触发方式表述      |
| ---------------------------------------------------------------- | -------------------------------- | ----------- |
| `.codemaker/skills/codesense-workflow/SKILL.md`                  | description / Step 1 / Examples  | 主动读取 / 主动调用 |
| `src/codesense_v1/server/server.py` SERVER_INSTRUCTIONS          | "Read this resource whenever..." | 主动读取        |
| `src/codesense_v1/resources/project_map.py` RESOURCE_DESCRIPTION | 适用/不适用场景，无"自动注入"措辞               | 主动读取        |
| `src/codesense_v1/tools/explore_module.py` description           | 适用/不适用场景 + 参数说明                  | 主动调用        |

整个项目对外口径统一：**Resource 和 Tool 都由 Agent 根据 description 主动决定是否调用**，不再有任何"自动注入"暗示。

---

## 四、对项目计划文档的建议修订

`doc/vibecoding_rules/codesense-intern-project-plan.md` 中以下两处与现实不符，建议在 Week 4 成果章节补充修订说明：

### 修订点 1：项目概述

> "再以 MCP Resource（**打开项目时自动注入架构概览**）和 MCP Tool（模块级别的整体理解）的形式给到 AI Agent。"

建议改为：

> "再以 MCP Resource（项目整体架构概览，可被 Agent 按需读取）和 MCP Tool（模块级别的整体理解）的形式给到 AI Agent。"

### 修订点 2：工具设计表

| 工具               | 类型           | 功能       | AI 使用方式（旧）   | AI 使用方式（修订）                  |
| ---------------- | ------------ | -------- | ------------ | ---------------------------- |
| `project_map`    | MCP Resource | 项目整体架构概览 | 被动注入，AI 无需调用 | **AI 根据 description 判断按需读取** |
| `explore_module` | MCP Tool     | 模块级整体理解  | AI 主动调用      | AI 主动调用（不变）                  |

并补充一段说明：

> **关于"被动注入"的设计偏差**：原设计假设 MCP Resource 可由客户端在连接时自动注入到 Agent 上下文。Week 4 实施阶段调研 MCP 协议规范及 CodeMaker 客户端实际行为后确认：MCP 协议中 Resource 是 pull-based 的，"自动注入"是客户端可选实现，并非协议保证；CodeMaker 当前行为是 Agent 根据 Resource 的 description 主动 `resources/read`。结合实现成本与代价，最终方案是通过强引导描述（适用/不适用场景）让 Agent 在合适时机主动读取，效果与"自动注入"的设计意图基本一致。真正的客户端侧自动注入留作 stretch goal。

### 修订点 3：与现有工具的分工图

```
project_map → explore_module → codegraph_explore → codegraph_callers → grep/read_file
  全局鸟瞰      模块面           符号+邻域          单点关系          精确文本
 (被动注入)    (面级理解)        (点到邻域)         (点查询)          (原始文本)
```

把 `(被动注入)` 改为 `(按需读取)` 或 `(全局鸟瞰)`。
