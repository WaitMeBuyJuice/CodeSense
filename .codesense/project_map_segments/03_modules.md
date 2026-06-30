## 模块划分

依据 `src/codesense_v1/` 顶层目录结构划分，对应架构图 L1-L7 分层。每个模块给出英文名 key、中文名、一句话职责、文件路径。

| 英文名 key | 中文名 | 职责 | 文件路径 |
|------------|--------|------|----------|
| server | 入口层（L1） | MCP stdio 服务入口，实现 list_tools / call_tool / list_prompts / get_prompt | src/codesense_v1/server/ |
| registry | 注册分发层（L2） | @tool 装饰器注册、JSON Schema 校验、工具派发 | src/codesense_v1/registry/ |
| tools | 工具层（L3） | project_map / explore_module / explore_submodule / save_* / submit_* 等 MCP 工具实现 | src/codesense_v1/tools/ |
| data | 数据层（L4） | 查询 CodeGraph SQLite（modules / architecture / docstrings / files 等） | src/codesense_v1/data/ |
| summarizer | 摘要层（L6） | 将 Data Layer 结构数据拼装为 Markdown prompt | src/codesense_v1/summarizer/ |
| cache | 基础设施层（L7） | .codesense/ 读写、DB hash 计算、缓存失效判断 | src/codesense_v1/cache/ |
| skills | 内置 Skills | 内置 Skill 文件（启动时写入 .claude/skills/，MCP Prompts 协议备用） | src/codesense_v1/skills/ |
| errors | 统一异常 | ToolError 异常体系 | src/codesense_v1/errors.py |

### 模块文件清单

- **server**: src/codesense_v1/server/
- **registry**: src/codesense_v1/registry/
- **tools**: src/codesense_v1/tools/__init__.py, _project_root.py, explore_module.py, explore_submodule.py, project_map.py, save_module_summary.py, save_project_map_segment.py, save_submodule_summary.py, submit_project_map.py
- **data**: src/codesense_v1/data/
- **summarizer**: src/codesense_v1/summarizer/
- **cache**: src/codesense_v1/cache/
- **skills**: src/codesense_v1/skills/
- **errors**: src/codesense_v1/errors.py