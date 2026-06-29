"""MCP Tool: get_submodule_prompt — returns the LLM prompt for a specific file sub-module doc."""

from __future__ import annotations

from typing import Final

from codesense_v1 import cache
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.ref_docs import ref_docs_prompt_section
from codesense_v1.errors import InvalidArgumentError
from codesense_v1.registry import tool
from codesense_v1.summarizer.summarizer import _build_submodule_prompt, _is_single_file_module
from codesense_v1.tools._project_root import project_root_not_found_error, resolve_project_root

_CODESENSE_DIR = ".codesense"

_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_name": {
            "type": "string",
            "description": "project_map 中列出的模块名（精确名称）",
        },
        "file_path": {
            "type": "string",
            "description": "模块内某个文件的相对路径（如 src/codesense_v1/cache/cache.py）",
        },
    },
    "required": ["module_name", "file_path"],
    "additionalProperties": False,
}


@tool(
    name="get_submodule_prompt",
    description=(
        "返回用于生成指定文件子模块文档的分析提示词文本。\n\n"
        "仅在 explore_submodule 返回生成步骤引导时使用，通常委派给子 Agent 执行。\n"
        "正常使用时无需主动调用本工具。\n\n"
        "module_name 必须是 project_map 返回的模块名之一。\n"
        "file_path 为该模块内文件的相对路径。\n"
        "获取提示词后，生成 Markdown 格式的子模块文档，"
        "再调用 save_submodule_summary 保存结果。"
    ),
    input_schema=_SCHEMA,
)
async def get_submodule_prompt_tool(module_name: str, file_path: str) -> str:
    module_name = module_name.strip()
    file_path = file_path.strip().replace("\\", "/")

    if not module_name:
        raise InvalidArgumentError("参数错误：module_name 不能为空")
    if not file_path:
        raise InvalidArgumentError("参数错误：file_path 不能为空")

    project_root = await resolve_project_root()
    if project_root is None:
        return project_root_not_found_error()

    codesense_dir = project_root / _CODESENSE_DIR
    db_path = project_root / ".codegraph" / "codegraph.db"

    if not db_path.exists():
        return (
            "# 错误\n\n"
            f"CodeGraph 数据库不存在（项目路径：{project_root}）。\n\n"
            "请先在该目录下运行 `codegraph init -i`。"
        )

    # Validate module existence
    index = cache.read_modules_index(codesense_dir)
    if index is None:
        raise InvalidArgumentError(
            "参数错误：尚未生成模块划分，请先调用 project_map 生成模块划分"
        )
    raw_modules = index.get("modules")
    modules_list: list[dict[str, object]] = (
        [m for m in raw_modules if isinstance(m, dict)]
        if isinstance(raw_modules, list)
        else []
    )
    norm_name = module_name.strip().lower()
    entry: dict[str, object] | None = None
    for m in modules_list:
        if str(m.get("name", "")).strip().lower() == norm_name:
            entry = m
            break
    if entry is None:
        available = [str(m.get("name", "")) for m in modules_list]
        raise InvalidArgumentError(
            f"参数错误：模块 '{module_name}' 不存在。可用模块：{', '.join(available)}"
        )

    # Single-file module check
    if _is_single_file_module(entry):
        name = str(entry.get("name", module_name))
        raise InvalidArgumentError(
            f"参数错误：模块「{name}」是单文件模块，请使用 get_module_prompt 获取该模块的分析提示词。"
        )

    # Validate file_path in module
    files_raw = entry.get("files")
    module_files = [str(f).replace("\\", "/") for f in (files_raw if isinstance(files_raw, list) else [])]
    if file_path not in module_files:
        raise InvalidArgumentError(
            f"参数错误：文件 '{file_path}' 不在模块「{module_name}」的文件列表中。"
            f"可用文件：{', '.join(sorted(module_files))}"
        )

    # Fetch file nodes and edges from DB
    with CodeGraphDB(project_root) as db:
        file_nodes = [
            node
            for node in db.iter_nodes(kinds=("function", "class", "method"))
            if node.file_path.replace("\\", "/") == file_path
        ]
        # Build node-id→file mapping so we can resolve imports/calls edge endpoints.
        node_id_to_file: dict[str, str] = {}
        for node in db.iter_nodes():
            node_id_to_file[node.id] = node.file_path.replace("\\", "/")

        out_files_set: set[str] = set()
        in_files_set: set[str] = set()
        for edge in db.iter_edges(kinds=("imports", "calls")):
            src_file = node_id_to_file.get(edge.source, edge.source).replace("\\", "/")
            tgt_file = node_id_to_file.get(edge.target, edge.target).replace("\\", "/")
            if src_file == file_path and edge.kind == "imports":
                out_files_set.add(tgt_file)
            if tgt_file == file_path and edge.kind == "imports":
                in_files_set.add(src_file)

    ref_docs = ref_docs_prompt_section(project_root)
    return _build_submodule_prompt(
        module_entry=entry,
        file_path=file_path,
        file_nodes=file_nodes,
        outbound_edges=[],
        inbound_edges=[],
        ref_docs_section=ref_docs,
        out_files=sorted(out_files_set),
        in_files=sorted(in_files_set),
    )
