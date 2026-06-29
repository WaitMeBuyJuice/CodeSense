---
name: codesense-flow
description: >
  适用场景：理解项目整体架构、模块职责、模块关系及功能归属、需要获取项目整体结构与模块功能组成等信息等探索类任务
  不适用场景：用户已明确给出文件路径、行号或具体符号名。
  激活后优先按"全局 → 模块 → 子模块 → 符号/原文"四层递进探索，满足跳过条件时可直接进入下一层。
compatibility: Requires CodeSense MCP and CodeGraph MCP.
---

# CodeSense 代码探索工作流
处理任何涉及理解或修改现有代码的任务前，一般遵循四层探索流程，但满足跳过条件时可直接进入下一层，然后再动代码。
---

## 流程步骤

### Step 1：全局定向 — `project_map`

调用 `project_map`，了解：

- 项目定位、技术栈
- 项目由哪些模块构成，各模块的职责、边界规则、上下游依赖
- 项目的关键流程
- 你要触及的功能大概落在哪个模块

**跳过条件**：若当前上下文已包含完成本层决策所需的信息，则跳过本层。

> 缓存未就绪时，工具返回体内嵌了初始化引导，按步骤完成后重新调用。
> 同一会话多次调用project_map工具时，`_nonce` 传不同递增值（"1"、"2"……）以避免客户端重复调用拦截。
> **注意**：初始化时可能需要两次调用 `project_map`：第一次完成 01_identity 和 03_modules，第二次完成边界规则 / 流程 / 概念索引段。

---

### Step 2：模块层 — `explore_module`

对每个计划探索、分析或修改的模块调用 `explore_module(module_name=<模块英文key>)`。

返回内容：
- 模块职责
- 公开接口（导出函数和类）
- 内部子模块及各子模块作用
- 模块的实现约束清单
- 模块的上下游依赖

**跳过条件**：若当前上下文已包含完成本层决策所需的信息，则跳过本层。

> `module_name` 是 `project_map` 中列出的模块英文 key（如 `cache`、`data`）。不知道有哪些模块时先做 Step 1。
>
> cache miss 时工具内嵌了推理 prompt，按 prompt 完成推理后调 `save_module_summary` 写回缓存。

---

### Step 3：子模块层 — `explore_submodule`

**触发条件**：需要深入理解某个具体子模块，修改模块内某个具体文件，或 explore_module 返回的信息不足以定位目标时。

调用 `explore_submodule(module_name=<模块英文key>, file_path=<完整相对路径>)`。

返回内容：
- 子模块职责
- 内部关键符号（函数、类）及其说明
- 子模块的典型调用链
- 子模块的上下游依赖

**跳过条件**：若当前上下文已包含完成本层决策所需的信息，则跳过本层。

> cache miss 时同样内嵌 prompt，推理完毕后调 `save_submodule_summary` 写回缓存。

---

### Step 4：符号/原文 — codegraph MCP + grep/read_file

**触发条件**：已知文件、符号或文本位置，需要定位具体源码时。

使用以下工具，优先使用语义工具（codegraph_explore、codegraph_node），仅在需要精确文本匹配或读取文件内容时使用 grep/read_file。

- **探索某区域或理解某段逻辑** → `codegraph_explore`（首选，自然语言或符号名，一次返回相关源码）
- **读单个文件或查单个符号** → `codegraph_node`
- **查询符号调用关系** → `codegraph_callers`
- **精确文本匹配** → `grep`
- **需要查看原文** → `read_file`

---

## 决策表

| 情况 | 行动 |
|------|------|
| 不熟悉代码库，刚开始任务 | Step 1：`project_map` |
| 要修改某模块 | Step 2：`explore_module` |
| 要深入某子模块实现 | Step 3：`explore_submodule` |
| 查某函数被谁调用 | `codegraph_callers` |
| 理解某段逻辑 / 探索某区域 | `codegraph_explore` |
| 已知文件路径 | 	`codegraph_node` / `read_file` | 
| 已知符号名 |  `codegraph_node` / `codegraph_callers` | 
| 已知文本内容 | 	`grep` | 

---

## 结束条件

满足以下任一情况即可停止继续向下探索：

- 已定位到需要修改的文件
- 已找到目标符号
- 已获得回答用户问题所需的信息

---

## save_* 工具使用时机

缓存未就绪（cache miss）时，工具返回体内嵌推理 prompt。流程：

1. 工具返回 cache miss + 内嵌 prompt
2. Agent 按 prompt 推理，生成文档内容
3. 调对应 save 工具写回缓存：
   - `save_module_summary` — 保存模块总览
   - `save_submodule_summary` — 保存子模块文档
   - `save_project_map_segment` — 保存 project_map 各段（01/03/04/05/06）
4. 重新调原工具，此时命中缓存正常返回

> `submit_project_map` 仅在 03_modules 段完成后调用，用于驱动 modules_index 更新。

---

## 示例

**输入**：帮我给缓存模块加一个过期时间配置项

1. `project_map` → 确认缓存模块位置与跨模块依赖
2. `explore_module("cache")` → 看公开接口和内部文件
3. `explore_submodule("cache", "src/codesense_v1/cache/cache.py")` → 看具体实现结构
4. `codegraph_node(file="cache.py")` → 读源码定位修改点
5. 修改

---

**输入**：`login()` 是谁调用的？

直接 `codegraph_callers(symbol="login")`，无需走完整流程（已知确切符号）。

---

**输入**：tools 层和 summarizer 层之间是什么关系？

1. `project_map` → 看两个模块间的依赖描述
2. 必要时 `explore_module("tools")` + `explore_module("summarizer")` → 看各自接口

---

**输入**：这个项目有哪些模块，整体架构是怎样的？

1. `project_map` → 直接获得模块列表、各模块职责、分层结构与跨模块依赖，问题已回答，停止。

---

