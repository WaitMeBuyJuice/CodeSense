---
name: codesense-workflow
description: 代码架构探索工作流。当需要理解、阅读或修改现有代码（尤其是不熟悉的代码库、定位功能所在模块、改动某个模块前），自动激活，引导按"全局架构 → 模块接口 → 代码细节"的顺序使用 CodeSense / CodeGraph 工具，避免一上来就 grep。
---

# CodeSense Code Understanding Workflow

When working on any coding task that involves understanding or modifying existing code,
follow this structured exploration workflow before writing or changing code.

## Instructions

### Step 1: Orient with project_map (Global View)
The `project_map` resource from the CodeSense MCP server is auto-injected into your context.
You already have it — consult it to understand:
- Which modules exist and what each one does
- How modules depend on each other
- Where the feature or code you need to touch likely lives

Skip this step only if you are already confident about the module structure from prior context.

### Step 2: Explore relevant modules with explore_module (Module View)
For every module you plan to read or modify, call `explore_module` with the module's
directory path (relative to the project root, e.g. `src/codesense_v1/cache`).

This gives you:
- The module's one-line purpose
- Its public interface (exported functions and classes)
- Internal files and their roles
- Which other modules it depends on

Call `explore_module` for each distinct module involved in your task before touching any code.

### Step 3: Drill into specifics (Detail View)
Only after completing Steps 1–2, use lower-level tools to find exact code:
- CodeGraph MCP tools — for symbol definitions, call chains, callers
- `grep` / `read_file` — for exact code text and line numbers

### Decision Guide

| Situation | Recommended action |
|-----------|-------------------|
| Starting a new task, unfamiliar with codebase | Step 1: consult project_map |
| About to modify a module | Step 2: call explore_module first |
| Need to find who calls a function | CodeGraph MCP tools |
| Need exact implementation of a known function | grep / read_file |
| Already know the exact file and symbol | Direct read_file is fine |

## Examples

输入：帮我给 cache 模块加一个过期时间配置项
输出：
1. （已注入的 project_map）确认 cache 模块位置与依赖 → 它被哪些模块引用
2. explore_module("src/codesense_v1/cache") → 看公开接口和内部文件
3. read_file 定位具体实现 → 修改
（先理解边界，再动代码）

输入：login() 这个函数是谁调用的？
输出：直接用 CodeGraph MCP 工具查 callers，无需走完整流程（已知确切符号）

## Notes

- `explore_module` 的 `module_path` 是相对于项目根目录的目录路径，且该目录须包含 `__init__.py`（Python 包）。
- 本工作流的价值：花 2 分钟做架构定向，省 20 分钟调试。它防止三类常见错误——改错模块、漏掉模块接口契约、破坏跨模块依赖。
- 已知确切文件和符号时，可直接 read_file，无需强制走完整流程。

## 安装方式

CodeMaker 官方 Skill 格式要求文件名为 `SKILL.md`，放在以技能名命名的目录下：

```
codesense-workflow/
└── SKILL.md      # 即本文件内容
```

安装时将本文件复制并重命名为 `codesense-workflow/SKILL.md`。
