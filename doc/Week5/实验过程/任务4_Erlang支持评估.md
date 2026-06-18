# 任务 4：codegraph 加 Erlang 语言支持评估（codegraph-main，复杂，评估类）

## 一、实验内容

**任务类型**：跨子系统功能新增评估（有 ground truth，测找全率，**仅输出评估清单不实际改代码**）

**任务描述**：
> 我想在 codegraph 现有的语言支持基础上，增加对 Erlang（`.erl` 和 `.hrl` 文件）的支持。请评估这个改动涉及哪些子系统、需要在哪几个地方分别做什么改动。**只列出框架性改动点和改动思路，不需要真实实现 tree-sitter 语法和提取逻辑。**

**涉及项目**：`E:\Python_Project\codegraph-main`

**为什么选这个任务**：
- 不在提示词出现"用 CodeSense"暗示
- "涉及哪些子系统、哪几个地方" 强烈命中 `project_map` 和 `explore_module` description
- 跨多个子系统（extraction / resolution / types），Agent 容易只改一个点就停（典型假饱和场景）
- 不实际改代码——避免在不熟悉的 TS 项目里验证改动正确性的高成本
- 难点：Agent 必须找到所有"已支持语言"的注册点模式（python/go 的实现可作参考）

**Ground Truth（已 grep 验证 python 注册点反推）**：

### 必须列出的核心改动点（共 4 个文件）：

| # | 文件 | 改动内容 |
|---|------|---------|
| 1 | `src/extraction/grammars.ts` | 添加 `erlang: 'tree-sitter-erlang.wasm'`、`.erl/.hrl` 扩展名映射、显示名 `erlang: 'Erlang'` |
| 2 | `src/types.ts` | 在语言枚举中添加 `'erlang'` |
| 3 | `src/extraction/languages/erlang.ts` | **新建**：实现 `erlangExtractor`（参考 `python.ts` / `go.ts`） |
| 4 | `src/extraction/languages/index.ts` | 导入 `erlangExtractor` 并注册到 `extractors` 映射 |

### 推荐列出的改动点（共 2 个文件）：

| # | 文件 | 改动内容 |
|---|------|---------|
| 5 | `src/resolution/import-resolver.ts` | 添加 Erlang 的 import 解析规则（`-include` 等） |
| 6 | `src/resolution/strip-comments.ts` | 添加 Erlang 的注释剥离（`%` 行注释） |

### 评分标准：

- **核心 4 个文件**（grammars / types / languages/erlang.ts / languages/index.ts）：算找全率分母
- **推荐 2 个文件**（import-resolver / strip-comments）：作为加分项，不算分母
- **不该提**：mcp/ 子系统（与语言扩展无关）、graph/ 子系统（与语言扩展无关）

**Ground Truth 找全率公式**：
- 核心找全率 = 命中核心文件数 / 4
- 加分项 = 是否提到 resolution 层的影响

**实验次数**：每组 3 次（关键任务）

---

## 二、如何进行实验

### 实验前

确认 MCP 配置中 `CODESENSE_PROJECT_ROOT` 已设为 `E:\Python_Project\codegraph-main`（组3/4 必须），VSCode 重启。

无代码改动，但仍要新开 CodeMaker 对话避免上下文污染。

### Phase 1 提示词（复制粘贴）

```
## 任务

在 codegraph 项目（路径 E:\Python_Project\codegraph-main）中，我想增加对 Erlang 语言（.erl 和 .hrl 文件）的支持。

请评估这个改动涉及哪些子系统、需要在哪几个地方分别做什么改动。

要求：
1. **只列出框架性改动点和改动思路，不需要真实实现 tree-sitter 语法和提取逻辑**
2. 给出文件路径 + 该文件要做的改动一句话
3. 越完整越好——遗漏注册点会导致 Erlang 实际不工作

## 要求

完成后，按照全局规则（.codemaker/rules/experiment-reporting.mdc）输出完整实验报告。改动文件清单填写为"提议的改动文件清单"（Agent 没有实际执行 edit，但要列出它建议改的文件）。
```

→ Agent 完成后，立刻抄 Token + 耗时。

### Phase 2 提示词（复制粘贴，同一会话）

```
## Ground Truth 对照

本任务的标准答案清单：

**核心必改文件（共 4 个）——找全率分母**：
1. src/extraction/grammars.ts（添加 erlang wasm 映射、.erl/.hrl 扩展名、显示名）
2. src/types.ts（语言枚举加 'erlang'）
3. src/extraction/languages/erlang.ts（新建 erlangExtractor，参考 python.ts/go.ts）
4. src/extraction/languages/index.ts（导入并注册 erlangExtractor）

**推荐提及的文件（共 2 个）——加分项，不算分母**：
5. src/resolution/import-resolver.ts（添加 -include 等 Erlang import 规则）
6. src/resolution/strip-comments.ts（添加 % 注释剥离）

**不该提的（与语言扩展无关）**：
- src/mcp/ 任何文件
- src/graph/ 任何文件

请基于你在 Phase 1 实际给出的改动建议，对照计算并输出：

| 指标 | 数值 |
|------|------|
| 核心 GT 总数 | 4 |
| 你提到的核心文件命中数（/4） | ? |
| 核心找全率 | ? |
| 你提到的推荐文件命中数（/2） | ? |
| 你提到的与语言扩展无关的文件数（误改） | ? |
| 漏提的核心文件清单 | ? |
| 误提的无关文件清单 | ? |
```

---

## 三、实验结果

### 3.1 过程指标汇总

| 指标 | 组1 第1次 | 组1 第2次 | 组1 第3次 | 组1 中位 | 组2 中位 | 组3 中位 | 组4 中位 |
|------|---|---|---|---|---|---|---|
| 检索数 | | | | | | | |
| 阅读数 | | | | | | | |
| project_map 调用 | N/A | N/A | N/A | N/A | N/A | | |
| explore_module 调用 | N/A | N/A | N/A | N/A | N/A | | |
| CodeGraph 调用 | N/A | N/A | N/A | N/A | | | |
| 总工具调用 | | | | | | | |
| Token | | | | | | | |
| 耗时（秒） | | | | | | | |

### 3.2 结果指标

| 指标 | 组1 第1次 | 组1 第2次 | 组1 第3次 | 组1 中位 | 组2 中位 | 组3 中位 | 组4 中位 |
|------|---|---|---|---|---|---|---|
| 核心找全率（/4） | | | | | | | |
| 推荐项加分（/2） | | | | | | | |
| 误提文件数 | | | | | | | |

### 3.3 关键观察：是否找到现有语言的注册模式

| 观察项 | 组1 | 组2 | 组3 | 组4 |
|-------|---|---|---|---|
| 是否查看 python.ts 或 go.ts 作为模板 | | | | |
| 是否找到 languages/index.ts 的注册位置 | | | | |
| 是否找到 grammars.ts 的 wasm 映射 | | | | |
| 是否找到 types.ts 的语言枚举 | | | | |
| 是否提到 resolution 层的影响（加分） | | | | |

### 3.4 假饱和重点观察

| 问题 | 组3 | 组4 |
|------|---|---|
| 读完 project_map 后是否对 extraction 模块用了 explore_module | | |
| 是否在没读 grammars.ts 源码的情况下凭印象给出建议 | | |
| 是否漏掉了 languages/index.ts 这个注册点（典型假饱和遗漏） | | |

### 3.5 质量评分（人工）

| 维度 | 组1 | 组2 | 组3 | 组4 |
|------|---|---|---|---|
| 改动建议正确性（1-5） | | | | |
| 引用具体度（1-5）——是否引用现有语言文件作参考 | | | | |
| 架构理解（1-5）——是否理解多子系统协作模式 | | | | |

### 3.6 备注

- 组1：
- 组2：
- 组3：
- 组4：
