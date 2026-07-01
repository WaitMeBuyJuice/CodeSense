"""MCP Tool: init_status — reports CodeSense initialization progress across all three phases."""

from __future__ import annotations

from typing import Final

from codesense_v1 import cache
from codesense_v1.registry import tool
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_SEGMENT_IDS: tuple[str, ...] = (
    "01_identity",
    "03_modules",
    "04_constraints",
    "05_flows",
    "06_concepts",
    "07_dependencies",
)

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="init_status",
    description=(
        "返回 CodeSense 三阶段初始化的完成情况：\n"
        "- Phase 1：project_map 6 个段落的生成状态\n"
        "- Phase 2：所有模块文档的生成状态\n"
        "- Phase 3：所有子模块文档的生成状态\n\n"
        "在以下场景调用：\n"
        "- 初始化开始前，了解当前进度，避免重复生成\n"
        "- 初始化中断后恢复，确认从哪个阶段继续\n"
        "- 不确定某模块/子模块是否已生成时\n\n"
        "无需入参，直接调用即可。"
    ),
    input_schema=_SCHEMA,
)
async def init_status() -> str:
    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / _CODESENSE_DIR
    lines: list[str] = ["## CodeSense 初始化状态\n"]

    # ── Phase 1: project_map segments ────────────────────────────────────────
    seg_done = [sid for sid in _SEGMENT_IDS if cache.read_segment(codesense_dir, sid) is not None]
    seg_missing = [sid for sid in _SEGMENT_IDS if sid not in seg_done]
    lines.append(f"### Phase 1：项目概览（{len(seg_done)}/{len(_SEGMENT_IDS)} 段落完成）")
    for sid in _SEGMENT_IDS:
        mark = "✅" if sid in seg_done else "❌"
        lines.append(f"- {mark} {sid}")
    lines.append("")

    # ── Phase 2 & 3: modules and subgroups ───────────────────────────────────
    modules_index = cache.read_modules_index(codesense_dir)
    if modules_index is None:
        lines.append("### Phase 2：模块文档")
        lines.append("❌ modules_index 不存在，请先完成 Phase 1（03_modules 段落）。")
        lines.append("")
        lines.append("### Phase 3：子模块文档")
        lines.append("❌ 依赖 Phase 2，暂无数据。")
        return "\n".join(lines)

    raw_modules = modules_index.get("modules") or []
    modules_list = [m for m in raw_modules if isinstance(m, dict)]
    total_modules = len(modules_list)

    p2_done: list[str] = []
    p2_missing: list[str] = []
    for m in modules_list:
        mname = str(m.get("name", ""))
        mkey = cache.safe_key(mname)
        if cache.read_module(codesense_dir, mkey) is not None:
            p2_done.append(mname)
        else:
            p2_missing.append(mname)

    lines.append(f"### Phase 2：模块文档（{len(p2_done)}/{total_modules} 模块完成）")
    if p2_done:
        lines.append("✅ " + " / ".join(p2_done))
    if p2_missing:
        lines.append("❌ 未生成：" + " / ".join(p2_missing))
    lines.append("")

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    total_sgs = 0
    total_sgs_done = 0
    p3_lines: list[str] = []

    for m in modules_list:
        mname = str(m.get("name", ""))
        mkey = cache.safe_key(mname)
        subgroups = [sg for sg in (m.get("subgroups") or []) if isinstance(sg, dict)]
        if not subgroups:
            continue

        sg_done: list[str] = []
        sg_missing: list[str] = []
        for sg in subgroups:
            sg_name = str(sg.get("name", ""))
            file_key = f"{mkey}_{sg_name}"
            if cache.read_submodule(codesense_dir, mkey, file_key) is not None:
                sg_done.append(sg_name)
            else:
                sg_missing.append(sg_name)

        total_sgs += len(subgroups)
        total_sgs_done += len(sg_done)
        status = "✅" if not sg_missing else f"{len(sg_done)}/{len(subgroups)}"
        missing_str = f"（缺 {', '.join(sg_missing)}）" if sg_missing else ""
        p3_lines.append(f"- {mname}：{status} {missing_str}")

    lines.append(f"### Phase 3：子模块文档（{total_sgs_done}/{total_sgs} 子模块完成）")
    lines.extend(p3_lines if p3_lines else ["（无模块定义了子模块划分）"])

    return "\n".join(lines)
