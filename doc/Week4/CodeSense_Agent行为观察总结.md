# CodeSense 集成测试 —— AI 行为观察日志

> **测试日期**：2026-06-16
> **测试模型**：Deepseek V4 Pro（1M 上下文）
> **被测项目**：CodeSense_V1
> **测试目的**：验证接入 CodeMaker 后，AI 是否按预期工作流
> （`project_map → explore_module → codegraph → grep/read_file`）探索代码，
> 重点观察 **AI 是否主动调用 `explore_module`**，以及 Skill 与 MCP Instructions 对其行为的影响。

---

## 一、测试场景

| 组别  | 场景  | Skill 状态               | MCP 服务                   | 任务                        |
| --- | --- | ---------------------- | ------------------------ | ------------------------- |
| 1   | 场景A | 开 `codesense-workflow` | codesense_v1 + codegraph | 理解 cache 模块并修改缓存失效策略      |
| 2   | 场景A | 未开                     | codesense_v1 + codegraph | 同上                        |
| 3   | 场景B | 开 `codesense-workflow` | codesense_v1 + codegraph | 新增 MCP Tool `list_cached` |

---

## 二、各组工具调用观察

### 组1 —— 场景A（开 Skill）

- **耗时/消耗**：203s / 260.8K tokens
- **工具调用**：共 20 次。关键探索链路 ——
  - `access_mcp_resource(project_map)` ×1 → 定位 cache 模块
  - `use_mcp_tool(explore_module)` ×1 → 理解 cache 公开接口与内部结构
  - `use_mcp_tool(codegraph_callers)` ×4 → 查 `is_cache_valid` / `invalidate` / `write_project_map` / `write_module` 的调用者
  - 再 `read_file` / `edit` 落到细节修改
- **行为评价**：**完整走通了"架构→模块→符号→细节"四层链路**，先理解边界再动代码，识别出 `summarizer/` 对缓存的隐含依赖。

### 组2 —— 场景A（未开 Skill）

- **耗时/消耗**：193s / 256.7K tokens
- **工具调用**：共 15 次。`access_mcp_resource(project_map)` ×1、`list_files_recursive` ×1、`read_file` ×4、`grep_search` ×1、`edit` ×3、`run_terminal_cmd` ×5
- **关键观察**：**全程未调用 `explore_module`**。AI 拿到 `project_map`（被动注入）后，直接用 `list_files_recursive` + `grep` + `read_file` 自行拼凑模块理解，跳过了模块级语义层。
- **行为评价**：任务结果仍正确（识别模块、未漏文件、符合现有模式），但探索方式回退到"点状搜索 + 文件遍历"，正是项目要解决的"浅层理解"模式。

### 组3 —— 场景B（开 Skill）

- **耗时/消耗**：272s / 489.8K tokens
- **工具调用**：共 29 次。`use_skill` ×1、`access_mcp_resource(project_map)` ×1、`search_tool` ×1、`use_mcp_tool(explore_module)` ×2、`read_file` ×7、`glob_search` ×2、`grep_search` ×1、`edit` ×3、`write` ×1、`run_terminal_cmd` ×10
- **行为评价**：新增 Tool 这类"对照现有实现模式"的任务，AI 对 `tools/`、`server` 模块各调用一次 `explore_module` 理解接口契约，正确发现需同步改 `schemas.py`、`tools/__init__.py`，而非只新建文件。

---

## 三、核心结论

### 1. `explore_module` 的调用强依赖 Skill

|                | project_map（Resource） | explore_module（Tool） |
| -------------- | --------------------- | -------------------- |
| 开 Skill（组1、组3） | ✅ 自动注入并使用             | ✅ 主动调用               |
| 未开 Skill（组2）   | ✅ 自动注入并使用             | ❌ **未调用**            |

- **被动注入的 `project_map` 无论是否开 Skill 都会被使用**——因为它不依赖 AI 主动性，这与设计预期一致。
- **需主动调用的 `explore_module` 则高度依赖 Skill 引导**。未开 Skill 时，仅靠 MCP Server Instructions（建议性措辞 "Prefer…/About to modify a module→…"）不足以稳定触发调用，AI 倾向用熟悉的 `grep` / 文件遍历替代。

### 2. 原因分析

差异本质是**指令强度**，而非信息有无：

- **MCP Instructions** 用的是建议性语言（"Prefer high-to-low abstraction"），AI 遵从率低。
- **Skill** 把工作流写成清单式强指令（"For every module you plan to read or modify, call `explore_module`"），并注入 System Prompt 高优先级位置，AI 遵从率显著更高。

这直接印证了项目计划中的风险条目 **"AI 不使用 explore_module → 核心价值无法体现 → 应对：重点打磨 instructions 和 skill 措辞"**。

### 3. 质量影响

三组任务结果均通过验收（正确识别模块、未漏关联文件、符合现有代码模式）。差异体现在**探索路径**：

- 开 Skill：架构层语义先行，决策有据，依赖关系识别更稳。
- 未开 Skill：结果可达但路径更"碰运气"，在更复杂/陌生的项目中风险更高。

---

## 四、后续可优化点

1. **MCP Instructions 措辞强化**：将建议性表述改为更明确的触发条件，缩小与 Skill 的引导差距，让未开 Skill 时也有基础保障。
2. **Week 5 量化验证**：在三组对比实验中，将"是否调用 `explore_module`""调用前后决策质量"作为核心指标量化，验证本日志的定性观察。
3. **保留 Skill 作为推荐用法**：当前数据表明 Skill 是稳定触发 `explore_module` 的关键，应在交付文档中明确推荐随项目一起启用。
