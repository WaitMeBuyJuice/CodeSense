from __future__ import annotations
import json
import asyncio
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, GetPromptResult, Prompt, PromptMessage, TextContent, Tool

from codesense_v1 import registry
from codesense_v1 import skills as _skills  # noqa: F401 — 触发 Skill 加载
from codesense_v1 import tools as _tools  # noqa: F401 — 触发工具注册

SERVER_NAME: str = "CodeSense"
SERVER_VERSION: str = "0.1.0"
SERVER_INSTRUCTIONS: str = """\
CodeSense 用于帮助理解代码仓库的高层架构：项目组织方式、功能实现、模块作用职责、模块内部结构以及模块间协作关系。

## 核心规则

- 不要猜：仓库特有信息（模块职责、架构、依赖）优先调工具，不要按命名经验推断。
- 已知确切文件/符号时，直接 grep / read_file，无需走完整工具调用层级的流程。
- 每次调用 `project_map` 时，**必须**传不同的递增 `_nonce` 值（"1"、"2"、"3"……），同一会话内不得重复；否则客户端重复调用检测会拦截请求，导致工具无法正常执行。

## 何时优先使用 CodeSense

以下意图优先调 CodeSense，而非直接 grep 或读源码：

- 第一次接触新代码库
- 需要获取项目整体结构、技术分层、模块组成等信息
- "某功能在哪里"、"哪个模块负责 XX"
- "修改某处会影响哪些地方"
- "某模块怎么工作"、"它的对外接口是什么"
- "两个模块之间是什么关系"
- "为什么这里放在这个模块"

## 工具调用层级（由全局到细节）

1. **全局** → `project_map`（项目架构、模块分布、跨模块依赖）
2. **模块** → `explore_module`（模块职责、架构简析、子模块列表、上下游依赖、实现约束）
3. **子模块** → `explore_submodule`（子模块概述、对外能力、跨模块依赖、典型调用链；按 subgroup_name 查询）
4. **符号/原文** → codegraph MCP（`codegraph_explore` 优先，单符号/文件用 `codegraph_node`，调用链用 `codegraph_callers`）/ 精确文本用`grep` + `read_file`

## 与其他工具的分工

- 谁调用了某函数 → `codegraph_callers`
- 已知确切文件/符号 → `codegraph_node` / grep / read_file
- 理解代码在系统中的位置和角色 → CodeSense

## 缓存未就绪时（cache miss 标准处理流程）

工具返回 cache miss 时，返回体内嵌了完整的推理提示词，**必须按以下步骤处理，不可跳过验证**：

1. **推理**：按内嵌提示词分析代码，生成对应文档内容
2. **写回缓存**：调对应 save 工具保存生成内容：
   - `project_map` 各段 → `save_project_map_segment(segment_id=..., content=...)`（`02_modules` 通过 `submit_project_map` 提交，无需单独 save_project_map_segment）
   - 模块文档 → `save_module_summary(module_name=..., summary=...)`（含 subgroups 定义）
   - 子模块文档 → `save_submodule_summary(module_name=..., subgroup_name=..., summary=...)`
3. **验证**：重调原工具并传 `verify_only=true`，确认返回缓存命中信号后再继续
4. **立即停止的触发条件**：仅当 Agent 自己保存成功后 `verify_only=true` 仍显示 cache miss，才是真 bug，需停止询问用户。
   cache miss 本身是正常状态（auto_expire 触发或手动删除），`init_status` 与 `explore_module` 状态不一致也不构成 bug，Agent 应直接按上述流程重新生成，无需询问用户。

**缓存过期处理倾向**：缓存过期（hash 不匹配）时**默认应重建**，让知识文档保持最新；重建后续调用可直接命中，收益长期。仅在明确的一次性快速探索场景下，才允许临时用过期文档 + 源码补充而不重建。

## subgroups 约束（save_module_summary）

定义子模块划分时：
- 必须按**业务职责**归并，不得机械地每文件一组
- **子模块数上限 5 个**，超过必须合并；
- **子模块数 ≥ 2 时**，每个子模块必须包含 ≥ 2 个文件；单文件必须并入职责相近的组
- 违反上述约束时 `save_module_summary` 会返回错误，需调整后重新调用
"""


def build_server() -> Server:
    """构造并返回已绑定回调的 mcp Server 实例。便于测试直接拿到 Server 注入 mock transport。"""
    server: Server = Server(
        name=SERVER_NAME, version=SERVER_VERSION, instructions=SERVER_INSTRUCTIONS
    )

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return registry.list_tools()

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, object]) -> CallToolResult:
        return await registry.dispatch(name, arguments)

    @server.list_prompts()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_prompts() -> list[Prompt]:
        return [
            Prompt(name=s.name, description=s.description)
            for s in _skills.list_skills()
        ]

    @server.get_prompt()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
        skill = _skills.get_skill(name)
        if skill is None:
            raise ValueError(f"未知 Skill：'{name}'")
        return GetPromptResult(
            description=skill.description,
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=skill.body),
                )
            ],
        )

    return server


async def run_stdio() -> None:
    """启动 stdio 传输并阻塞运行，直到 stdin 关闭或收到关闭信号。"""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """同步入口：asyncio.run(run_stdio())。供 `codesense` 命令调用。"""
    _init_codesense_config()
    _auto_sync_ignore_test_dirs()
    _init_skills()
    asyncio.run(run_stdio())


def _auto_sync_ignore_test_dirs() -> None:
    """每次启动时扫描项目内 test/tests/__tests__/spec 等目录，追加到 ignore_docs.paths（去重，不覆盖用户已有配置）。"""
    import json

    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return
    project_root = Path(project_root_str)
    config_path = project_root / ".codesense" / ".codesense_config"
    if not config_path.exists():
        return

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(config, dict):
        return

    _TEST_DIR_NAMES = {"test", "tests", "testing", "__tests__", "spec", "specs"}

    found: list[str] = []

    def _scan(path: Path, depth: int, rel_parts: list[str]) -> None:
        if depth > 5:
            return
        try:
            for entry in sorted(path.iterdir()):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                rel = "/".join(rel_parts + [entry.name])
                if entry.name in _TEST_DIR_NAMES:
                    found.append(rel)
                else:
                    _scan(entry, depth + 1, rel_parts + [entry.name])
        except PermissionError:
            pass

    _scan(project_root, 1, [])

    if not found:
        return

    ignore_docs = config.setdefault("ignore_docs", {})
    if not isinstance(ignore_docs, dict):
        ignore_docs = {}
        config["ignore_docs"] = ignore_docs

    existing: list[str] = ignore_docs.get("paths", [])
    if not isinstance(existing, list):
        existing = []

    existing_set = set(existing)
    new_paths = [p for p in found if p not in existing_set]
    if not new_paths:
        return

    ignore_docs["paths"] = sorted(existing_set | set(new_paths))
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _init_codesense_config() -> None:
    """在 .codesense/ 下创建 .codesense_config 模板（若不存在）。"""
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return
    target = Path(project_root_str) / ".codesense" / ".codesense_config"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    import json
    config_template = {
        "cache_auto_expire": True,
        "extract_docstrings": True,
        "include_dirs": [],
        "ref_docs": {
            "comment": "参考文档路径列表（可以是文件或目录），用于分析时注入到 prompt 中，帮助 AI 理解项目背景",
            "paths": [],
            "recursive": False,
        },
        "ignore_docs": {
            "comment": "分析时需要排除的路径（可以是文件或目录），这些路径下的代码不会被分析",
            "paths": [],
        },
    }
    target.write_text(
        json.dumps(config_template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _init_skills() -> None:
    """将打包的 SKILL.md 文件写入 {CODESENSE_PROJECT_ROOT}/.claude/skills/<name>/SKILL.md。

    仅当目标文件不存在或内容与打包版本不一致时才写入，确保每次服务升级后 Skill 同步更新。
    """
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return
    skills_dir = Path(project_root_str) / ".claude" / "skills"
    for skill in _skills.list_skills():
        target = skills_dir / skill.name / "SKILL.md"
        if target.exists() and target.read_text(encoding="utf-8") == skill.raw:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skill.raw, encoding="utf-8")


if __name__ == "__main__":
    main()
