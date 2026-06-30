# CodeSense_V1 业务概念索引

> 按需求关键词直查，找到 module_id 后再读对应的 _overview.md。
> **每行都是独立可检索的业务映射**，避免跨行拼读。

| 业务概念/需求关键词 | module_id | 子文档 | 关键符号 | 一句话说明 |
|------------------|-----------|--------|---------|-----------|
| 项目架构概览/project_map/整体结构 | tools | `tools/tools_project_map.md` | `project_map` | 返回项目级架构 Markdown（定位+结构+模块+依赖），4 段懒加载拼接 |
| 模块深度理解/explore_module/模块怎么实现 | tools | `tools/tools_module.md` | `explore_module` | 返回单模块职责/对外接口/内部文件/上下游依赖，传模块名非路径 |
| 模块划分提交/submit_project_map/竖线文本 | summarizer | `summarizer/summarizer_project_map.md` | `submit_project_map`, `_parse_modules_text` | 解析"模块名\|职责\|目录"竖线文本，写 modules_index + 渲染 project_map |
| 模块摘要提示词/get_module_prompt | summarizer | `summarizer/summarizer_module.md` | `get_module_prompt` | 生成单模块摘要的 LLM 提示词（含符号/公开 API/docstrings） |
| 模块摘要保存/save_module_summary | summarizer | `summarizer/summarizer_module.md` | `save_module_summary`, `_compute_module_hash` | 写 modules/<safe_key>.md + per-module content hash |
| identity 段/仓库定位/技术栈提示词 | summarizer | `summarizer/summarizer_project_map.md` | `get_identity_segment_prompt` | project_map 的 01_identity 段提示词（仓库定位+技术栈） |
| project_map 段渲染/structure/dependencies 段 | summarizer | `summarizer/summarizer_project_map.md` | `render_structure_segment`, `render_dependencies_segment` | 02/04 段纯程序渲染（不调 LLM），由源数据 hash 驱动失效 |
| 模块划分提示词/get_modules_segment_prompt | summarizer | `summarizer/summarizer_project_map.md` | `get_project_map_prompt` | project_map 的 03_modules 段模块划分提示词 |
| save_project_map_segment/段落保存 | tools | `tools/tools_project_map.md` | `save_project_map_segment` | 保存 Agent 生成的 01_identity/03_modules 段，segment_id 限定两值 |
| CodeGraph DB 查询/文件/模块/依赖 | data | `data/data_query.md` | `CodeGraphDB`, `list_modules`, `module_dependencies` | 只读封装 codegraph.db，iter_files/iter_nodes/iter_edges + 聚合查询 |
| 目录依赖聚合/directory_dependencies/symbols | data | `data/data_query.md` | `directory_dependencies`, `directory_symbols` | 按目录聚合依赖边与符号（max_per_dir=50 防 token 超限） |
| 拓扑分层/环检测/中心度/架构分析 | data | `data/data_analysis.md` | `topological_layers`, `find_cycles`, `compute_centrality` | 模块依赖图分析：分层/找环/中心度/跨目录公开 API |
| 顶层目录分类/辅助目录/tests/scripts | data | `data/data_analysis.md` | `classify_top_dirs`, `auxiliary_category`, `AUXILIARY_DIR_NAMES` | 区分代码目录与辅助目录（tests/docs/build 等），L2 辅助目录归类 |
| 内容指纹/hash/缓存失效判断 | data | `data/data_analysis.md` | `compute_identity_hash`, `compute_structure_hash`, `compute_architecture_hash`, `compute_dependencies_hash` | 4 个 hash 驱动 segment 缓存失效，输入变化即重生成 |
| 项目身份信息/README/技术栈识别 | data | `data/data_context.md` | `collect_identity_sources`, `extract_tech_stack_hint`, `read_readme` | 聚合 README/manifest/配置文件供 01_identity 段 |
| docstring 提取/多语言文档字符串 | data | `data/data_context.md` | `extract_file_docstring`, `extract_symbol_docstrings`, `is_enabled` | 多语言文件/符号 docstring 提取，注入 LLM prompt 防幻觉 |
| ref_docs/参考文档注入 | data | `data/data_context.md` | `ref_docs_prompt_section` | 读取项目参考文档目录，拼入 LLM prompt 段落 |
| 缓存读写/.codesense/目录 | cache | `cache/cache_core.md` | `read_module`, `write_segment`, `render_project_map` | .codesense/ 读写：project_map 段 + 模块摘要 + meta，read 返 None/write 传播 OSError |
| 缓存失效/invalidate/prune/safe_key | cache | `cache/cache_core.md` | `invalidate`, `write_modules_index`, `safe_key` | 全量清空/增量清理；safe_key 替换非法文件名字符（非 sha1） |
| 工具注册/@tool 装饰器/ToolSpec | registry | `registry/registry_core.md` | `tool`, `list_tools`, `dispatch`, `ToolSpec` | @tool import 时注册到 _REGISTRY；list_tools/dispatch 分发 |
| 参数校验/jsonschema 错误翻译 | registry | `registry/registry_core.md` | `dispatch`, `_translate_jsonschema_error` | Draft202012Validator 校验，required/type/additionalProperties 翻中文 |
| 错误类型/ToolError/异常体系 | errors | `errors/errors_core.md` | `ToolError`, `ValidationError`, `InvalidArgumentError`, `LLMError` | 4 个异常类，registry 兜底捕获转 isError=true |
| MCP Server 启动/stdio/instructions | server | `server/server_core.md` | `build_server`, `run_stdio`, `SERVER_INSTRUCTIONS` | 构造 mcp Server + stdio + 回调绑定 + .codesenseignore 模板 |
| 项目根解析/CODESENSE_PROJECT_ROOT | tools | `tools/_overview.md` | `resolve_project_root` | 三级 fallback：env → MCP roots/list → CWD 向上找 codegraph.db |
| 缓存自动失效开关/CODESENSE_CACHE_AUTO_EXPIRE | summarizer | `summarizer/summarizer_module.md` | `is_auto_expire_enabled` | 默认 true 随 DB hash 失效；false 则始终返回旧缓存 |

> ⚠️ 名称易混淆提示：
> - **project_map**（项目级概览，4 段拼接）vs **explore_module**（模块级深度）— 前者先看全局，后者深入单模块
> - **get_module_prompt**（取模块摘要提示词）vs **get_modules_segment_prompt**（取模块划分提示词）— 前者单模块摘要，后者项目模块划分
> - **submit_project_map**（提交模块划分，写 03+04 段）vs **save_project_map_segment**（保存单段，仅 01/03）— 前者解析竖线文本，后者直接存 Markdown
> - **data**（DB 查询，只读）vs **cache**（.codesense/ 读写）vs **summarizer**（协调，产 prompt+渲染）— 三者职责不同，data 不写缓存，cache 不查 DB，summarizer 不直接调 LLM
