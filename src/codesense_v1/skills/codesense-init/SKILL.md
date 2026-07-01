---
name: codesense-init
description: >
  适用场景：用户需要为项目初始化 CodeSense 知识文档，或在缓存全部失效后重新生成。
  不适用场景：知识文档已存在且有效、只需查询项目结构（使用 codesense-flow）。
  激活后按"project_map 初始化 → 模块文档 → 子模块文档"三阶段引导完成全量知识文档生成。
---

# CodeSense 知识文档初始化工作流

本 Skill 引导完成 CodeSense 知识文档的全量生成。完成后可通过 `project_map`、`explore_module`、`explore_submodule` 正常查询。

---

## Phase 0：初始化项目配置

在开始生成知识文档前，先配置 `.codesense/.codesense_config`。

### 0.1 检查配置文件是否已存在

读取 `{project_root}/.codesense/.codesense_config`（若不存在，服务启动时已自动生成默认模板）。

### 0.2 询问参考文档（ref_docs）

询问用户：
> 项目是否有需要辅助分析的参考文档（需求文档、设计文档等）？请输入文件或目录路径（多条用逗号分隔），或直接跳过。

若用户提供路径：
- 解析为路径列表，填入 `ref_docs.paths`
- 若路径中包含目录，询问是否递归扫描子目录，更新 `ref_docs.recursive`

### 0.3 询问忽略路径（ignore_docs）

询问用户：
> 是否有在分析时需要忽略的目录或文件？请输入路径（多条用逗号分隔），或直接跳过。

若用户提供路径：
- 填入 `ignore_docs.paths`

### 0.4 写入配置文件

将 `ref_docs.paths`、`ref_docs.recursive`、`ignore_docs.paths` 更新写入 `.codesense/.codesense_config`（保留其他字段不变）。

完成后输出确认：
> ✅ 配置已写入 `.codesense/.codesense_config`，继续 Phase 1。

---

## Phase 1：生成 project_map（项目概览）

> **进度确认**：若不确定当前初始化到哪个阶段，可先调用 `init_status()` 查看三阶段完成情况，再决定从哪里开始。

### 1.1 首次调用 project_map

调用 `project_map(_nonce="1")`。

- 若返回完整项目概览 → Phase 1 完成，直接跳到 Phase 2
- 若返回"需生成以下段落" → 按下方步骤处理

### 1.2 生成 01_identity 和 03_modules（可并行）

`project_map` 返回的步骤中会内嵌各段分析提示词，按以下顺序处理：

**生成 01_identity**（仓库定位 + 技术栈）：
1. 按返回的提示词生成内容
2. 调用 `save_project_map_segment(segment_id="01_identity", content=<生成内容>)`

**生成 03_modules**（模块划分，其他段依赖此段，优先完成）：
1. 按返回的提示词生成模块划分，格式：每行 `模块名|一句话职责|目录路径`（多目录用英文逗号分隔）
2. **模块名必须使用英文**（如 `data`、`cache`、`summarizer`），不得使用中文
3. 调用 `submit_project_map(response=<模块划分文本>)`

> `02_structure` 和 `07_dependencies` 由程序自动生成，无需 Agent 处理。

### 1.3 第二次调用 project_map

`03_modules` 完成后，调用 `project_map(_nonce="2")`。

此时会返回 `04_constraints`、`05_flows`、`06_concepts` 的生成步骤（含各段提示词）。

**生成 04_constraints**（模块边界规则）：
1. 按提示词生成内容
2. 调用 `save_project_map_segment(segment_id="04_constraints", content=<生成内容>)`

**生成 05_flows**（关键流程描述）：
1. 按提示词生成内容
2. 调用 `save_project_map_segment(segment_id="05_flows", content=<生成内容>)`

**生成 06_concepts**（概念索引）：
1. 按提示词生成内容
2. 调用 `save_project_map_segment(segment_id="06_concepts", content=<生成内容>)`

### 1.4 验证

调用 `project_map(_nonce="3")`，返回完整 Markdown 概览则 Phase 1 完成。

---

## Phase 2：生成模块文档

从 project_map 返回的模块列表中，逐个处理每个模块（辅助目录跳过）。

**每个模块的处理步骤**：

1. 调用 `explore_module(module_name=<模块名>)`
2. 若返回缓存命中的模块文档 → 跳过，处理下一个模块
3. 若返回"尚未生成摘要"（cache miss）：
   - 工具返回体中包含完整分析提示词
   - 按提示词生成模块 Markdown 摘要，包含：
     - 一句话定位
     - 架构简析
     - 子模块列表（子模块名 | 职责 | 包含文件）
     - 上下游关系
     - 实现约束清单
   - 同时在摘要末尾输出 `## subgroups（JSON）` 段，定义子模块划分（必须按业务职责归并，不要机械地每文件一组；**当子模块数 ≥ 2 时，每个子模块必须包含 ≥ 2 个文件**，单文件必须并入职责相近的组，否则 `save_module_summary` 会返回错误；**files 字段必须使用完整相对路径**，与 explore_module 返回的路径格式一致，如 `src/main/java/com/tongji/auth/api/AuthController.java`）
   - 调用 `save_module_summary(module_name=<模块名>, summary=<生成的摘要（含 subgroups 段）>)`
   - 重新调用 `explore_module(module_name=<模块名>, verify_only=true)` 确认命中

> **推荐**：每个模块委派给子 Agent 处理（工具返回体中有现成的子 Agent 指令），避免大量文件读取污染主对话上下文。

**小模块例外**：若某模块的文件 ≤ 3 条，由主 Agent 直接处理（按工具返回的「方式 2：主 Agent 直接执行」），不派发子 Agent。子 Agent 启动开销大于上下文污染成本。

> 例：`errors`（仅 1 个 errors.py）、`registry`（仅 1 个 registry.py）、`skills`（2-3 个文件）均属小模块，直接处理即可。

---

## Phase 3：生成子模块文档

对 Phase 2 中处理过的每个**多子模块**模块，**每个模块派发 1 个子 Agent** 批处理其全部子模块，避免重复读取共享文件。

**子模块来源**：
- 从 Phase 2 生成的模块文档「子模块列表」中获取所有子模块名（如 `storage`、`api`）

**派发模式**：

为每个模块创建 1 个子 Agent，传入以下任务清单：

> 你是负责生成模块 `<模块名>` 全部子模块文档的子 Agent。该模块包含子模块：`<sub1>`、`<sub2>`……
>
> **注意**：`explore_submodule`、`save_submodule_summary` 工具已在 CodeSense MCP 服务器注册，可直接调用，无需先激活。
>
> 依次处理每个子模块：
> 1. 调用 `explore_submodule(module_name="<模块名>", subgroup_name="<子模块名>")`
> 2. 若缓存命中 → 跳过，处理下一个
> 3. 若返回"尚未生成文档"（cache miss）：
>    - 按返回的分析提示词生成子模块 Markdown 文档，包含：
>      - 子模块概述
>      - 对外能力（该子模块对外提供什么能力；不列函数签名）
>      - 跨模块依赖（上游/下游模块名）
>      - 典型调用链（每条用三级标题命名）
>    - 调用 `save_submodule_summary(module_name="<模块名>", subgroup_name="<子模块名>", summary=<生成的文档>)`
>    - 调用 `explore_submodule(module_name="<模块名>", subgroup_name="<子模块名>", verify_only=true)` 确认命中
> 4. 全部完成后回复"已完成"

**优势**：
- 共享文件（如 `db.py`、`modules.py`）只读取一次
- 子 Agent 启动次数 = 模块数（不是子模块数）
- 同模块内子模块上下文连贯，文档风格统一

**小模块例外**：若某模块的子模块数 ≤ 2，由主 Agent 直接处理，不派发子 Agent。

> 例：`errors`（1 个子模块）、`config`（2 个子模块）属于小模块，直接处理；`auth`（4 个子模块）、`data`（5 个子模块）则应派发子 Agent。

---

## 整体进度追踪

| 阶段 | 内容 | 完成标志 |
|------|------|---------|
| Phase 0 | 配置 ref_docs + ignore_docs | `.codesense_config` 写入成功 |
| Phase 1 | project_map 7 段全部生成 | `project_map` 返回完整 Markdown |
| Phase 2 | 所有模块文档生成 | 每个 `explore_module` 均命中缓存 |
| Phase 3 | 所有子模块文档生成 | 每个 `explore_submodule` 均命中缓存 |

---

## 注意事项

- `_nonce` 每次调用 `project_map` 时传递不同递增值（"1"、"2"、"3"……），避免客户端重复调用拦截
- Phase 1 中 `01_identity` 与 `03_modules` 可并行，但 `04/05/06` 必须等 `03_modules` 完成后再生成
- Phase 2 和 Phase 3 可以按模块串行，也可以批量派发多个子 Agent 并行处理不同模块，加快初始化速度
- 初始化完成后，知识文档保存在 `.codesense/` 目录下，后续按需自动失效刷新，无需手动重跑本流程
- **遇到工具返回非预期结果时（如段落保存成功但下次调用仍显示缺失、hash 不匹配等），立即停止并向用户说明问题，不要自行读取源码排查根因**
