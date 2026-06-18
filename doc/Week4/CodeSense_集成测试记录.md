# CodeSense 集成测试记录

> 测试目标：观察 AI 在 CodeSense_V1 项目上修改代码时，是否按"project_map → explore_module → grep/read_file"顺序探索代码。
> 
> 测试方式：手动在 CodeMaker 中向 AI 提出任务，记录 AI 的工具调用序列和决策质量。 

---

## 预设测试场景

### 场景 A：修改缓存失效逻辑

**任务描述**：

> 告诉我CodeSense_V1代码仓库中缓存模块的作用和缓存失效策略，
> 
> 然后将缓存失效策略改为"DB hash 变化时保留模块级缓存，清楚其他缓存"。
> 
> 修改完成后自动验证。
> 
> 注意：
> 
> 1.任务结束后进行总结。
> 
> 2.统计此次任务使用的工具以及次数以及使用的理由（若使用MCP服务工具use_mcp_toll、命令行工具run_terminal_cmd，请标注具体工具名称）。
> 
> 3.说明此次任务的执行流程

**期望 AI 行为**：

1. 查看 project_map，定位 `cache/` 模块
2. 对 `cache/` 调用 `explore_module`，理解 `invalidate()` 接口和缓存结构
3. 检查哪些地方调用了 `invalidate()`，评估改动影响范围

**关键验收点**：

- AI 是否通过 `explore_module` 理解了 `.codesense/` 的目录结构（而非直接 grep 猜测）
- AI 是否找到了 `summarizer/` 也依赖缓存这一隐含依赖 

---

### 场景 B：新增 MCP Tool

**任务描述**：

> 在 CodeSense_V1 项目中新增一个 MCP Tool，名为 `list_cached`，
> 
> 功能为返回当前 `.codesense/modules/` 目录下的所文件。
> 
> 修改完成后自动验证。
> 
> 注意：
> 
> 1.任务结束后进行总结。
> 
> 2.统计此次任务使用的工具以及次数以及使用的理由（若使用MCP服务工具use_mcp_toll、命令行工具run_terminal_cmd，请标注具体工具名称）。
> 
> 3.说明此次任务的执行流程

**期望 AI 行为**：

1. 查看 project_map，定位 `tools/`、`cache/`、`schemas/`、`registry/` 模块
2. 对 `tools/explore_module.py` 和 `cache/cache.py` 调用 `explore_module`，理解现有 Tool 实现模式
3. 按照 `schemas.py → tools/<name>.py → tools/__init__.py` 的步骤新增 Tool

**关键验收点**：

- AI 是否发现需要同时改 `schemas.py`、`tools/__init__.py`（不只是新建一个文件）
- AI 是否使用了 `explore_module` 而非直接 grep 

---

## 测试记录

---

### 场景A（开Skill）

| 项             | 内容                        |
| ------------- | ------------------------- |
| **日期**        | 2026.06.16                |
| **使用模型**      | Deepseek V4 Pro，1M上下文窗口   |
| **Skill 状态**  | 激活，codesense_workflow     |
| **MCP 服务**    | 激活，codesense_v1，codegraph |
| **任务描述**      | 见场景A中任务描述                 |
| **任务时间**      | 203s                      |
| **Token消耗**   | 260.8K                    |
| **Skill使用情况** | codesense-workflow        |
| **MCP服务使用情况** | codesense_v1，codegraph    |

**任务Token消耗&时间：**

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-11-23-image.png)

**工具调用情况**：

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-11-43-image.png)

**Skill&MCP服务工具调用情况**：

| 服务           | 工具                 | 备注                                                               |
| ------------ | ------------------ | ---------------------------------------------------------------- |
| Skill        | codesense-workflow | 引导按"架构→模块→细节"顺序探索                                                |
| codesense_v1 | project_map        | 获取项目全局架构概览，定位 cache 模块                                           |
| codesense_v1 | explore_module     | 探索 cache 模块的公开接口和内部结构                                            |
| codegraph    | codegraph_callers  | 查找 is_cache_valid、invalidate、write_project_map、write_module 的调用者 |

**Agent执行流程**：

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-14-23-image.png)

**任务结果：**

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-14-46-image.png)

**Agent执行质量评估**：

- [x] 正确识别了需要修改的模块
- [x] 没有遗漏相关联的文件
- [x] 改动符合现有代码模式（命名、结构等）

---

### 场景A（未开Skill）

| 项             | 内容                        |
| ------------- | ------------------------- |
| **日期**        | 2026.06.16                |
| **使用模型**      | Deepseek V4 Pro，1M上下文窗口   |
| **Skill 状态**  | 无                         |
| **MCP 服务**    | 激活，codesense_v1，codegraph |
| **任务描述**      | 见场景A中任务描述                 |
| **任务时间**      | 193s                      |
| **Token消耗**   | 256.7K                    |
| **Skill使用情况** | 无                         |
| **MCP服务使用情况** | codesense_v1              |

**任务Token消耗&时间：**

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-18-55-02-image.png)

**工具调用情况**：

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-18-53-19-image.png)

**MCP服务工具使用情况**：

| 服务           | 工具          | 备注                    |
| ------------ | ----------- | --------------------- |
| codesense_v1 | project_map | 获取项目整体架构概览（模块列表、依赖关系） |

**Agent执行流程**：

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-18-53-53-image.png)

**任务结果：**

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-18-53-41-image.png)

**Agent执行质量评估**：

- [x] 正确识别了需要修改的模块
- [x] 没有遗漏相关联的文件
- [x] 改动符合现有代码模式（命名、结构等）

### 场景B（开Skill）

| 项             | 内容                        |
| ------------- | ------------------------- |
| **日期**        | 2026.06.16                |
| **使用模型**      | Deepseek V4 Pro，1M上下文窗口   |
| **Skill 状态**  | 激活，codesense-workflow     |
| **MCP 服务**    | 激活，codesense_v1，codegraph |
| **任务描述**      | 见场景B中任务描述                 |
| **任务时间**      | 272s                      |
| **Token消耗**   | 489.8K                    |
| **Skill使用情况** | codesense-workflow        |
| **MCP服务使用情况** | codesense_v1，codegraph    |

**任务Token消耗&时间：**

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-20-52-image.png)

**工具调用情况**：

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-22-00-image.png)

**Skill&MCP服务工具调用情况**：

| 服务           | 工具                 | 备注                   |
| ------------ | ------------------ | -------------------- |
| Skill        | codesense-workflow | 引导按"架构→模块→细节"顺序探索    |
| codesense_v1 | project_map        | 获取项目全局架构概览           |
| codesense_v1 | explore_module     | 理解 tools、server 模块接口 |

**Agent执行流程**：

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-21-40-image.png)

**任务结果：**

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-16-19-21-51-image.png)

**Agent执行质量评估：**

- [x] 正确识别了需要修改的模块
- [x] 没有遗漏相关联的文件
- [x] 改动符合现有代码模式（命名、结构等）

---
