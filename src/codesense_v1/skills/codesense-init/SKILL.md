---
name: codesense-init
description: >
  适用场景：为项目初始化 CodeSense 知识文档，包括项目概览、模块文档、子模块文档的首次生成，或在缓存全部失效后重新生成。
  不适用场景：知识文档已存在且有效、只需查询项目结构（使用 codesense-flow）。
  激活后按"project_map 初始化 → 模块文档 → 子模块文档"三阶段引导完成全量知识文档生成。
---

# CodeSense 知识文档初始化工作流

本 Skill 引导完成 CodeSense 知识文档的全量生成。完成后可通过 `project_map`、`explore_module`、`explore_submodule` 正常查询。

---

## 前置条件

在开始前确认：

- 已在项目目录运行 `codegraph init -i`，`.codegraph/codegraph.db` 存在
- CodeSense MCP 服务已启动

若 `codegraph.db` 不存在，先执行 `codegraph init -i`，再继续。

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

### 1.1 首次调用 project_map

调用 `project_map`。

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
   - 同时在摘要末尾输出 `## subgroups（JSON）` 段，定义子模块划分（必须按业务职责归并，不要机械地每文件一组）
   - 调用 `save_module_summary(module_name=<模块名>, summary=<生成的摘要（含 subgroups 段）>)`
   - 重新调用 `explore_module(module_name=<模块名>)` 确认命中

> **推荐**：每个模块委派给子 Agent 处理（工具返回体中有现成的子 Agent 指令），避免大量文件读取污染主对话上下文。

---

## Phase 3：生成子模块文档

对 Phase 2 中处理过的每个模块，逐子模块生成子模块文档。

**子模块来源**：
- 从模块文档的「子模块列表」中获取各子模块名（如 `data_storage`、`cache_storage`）
- 每个子模块名对应一份子模块文档

**每个子模块的处理步骤**：

1. 调用 `explore_submodule(module_name=<模块名>, subgroup_name=<子模块名>)`
2. 若返回缓存命中的文档 → 跳过
3. 若返回"尚未生成文档"（cache miss）：
   - 工具返回体中包含完整分析提示词
   - 按提示词生成子模块 Markdown 文档，包含：
     - 子模块概述
     - 对外能力（该子模块对外提供什么能力；不列函数签名）
     - 跨模块依赖（上游/下游模块名）
     - 典型调用链（每条用三级标题命名）
   - 调用 `save_submodule_summary(module_name=<模块名>, subgroup_name=<子模块名>, summary=<生成的文档>)`

> **推荐**：同样委派给子 Agent 处理（工具返回体中有现成的子 Agent 指令）。

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
