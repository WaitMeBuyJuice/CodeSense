# 任务列表 — resources/project_map

## 模块说明
新建 `src/codesense_v1/resources/project_map.py` 及包 `__init__.py`，并扩展 `server.py` 绑定 Resource 回调。

---

- [x] 任务ID: RES-1 — 实现 `resources/project_map.py` 及单元测试
  - 输入: `doc/Week3/design/resources_project_map.md`
  - 输出:
    - `src/codesense_v1/resources/__init__.py`
    - `src/codesense_v1/resources/project_map.py`
    - `tests/test_resources_project_map.py`
  - 验收标准:
    - `read_project_map()` 正常路径：mock summarizer，返回 Markdown 字符串
    - `CODESENSE_PROJECT_ROOT` 未设置 → 返回含错误说明的 Markdown（不抛异常）
    - `FileNotFoundError` → 返回含错误说明的 Markdown
    - `LLMError` → 返回含错误说明的 Markdown
    - 常量 `RESOURCE_URI`、`RESOURCE_NAME`、`RESOURCE_MIME_TYPE` 存在且值正确
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过
  - 依赖: SUM-1（需要 summarizer 接口稳定）

- [x] 任务ID: RES-2 — 扩展 `server.py` 绑定 Resource 回调
  - 输入: `doc/Week3/design/resources_project_map.md`（server 绑定方式）、现有 `src/codesense_v1/server.py`
  - 输出: `src/codesense_v1/server.py`（新增 `list_resources` / `read_resource` 回调）
  - 验收标准:
    - `build_server()` 返回的 server 能响应 `resources/list` 请求，返回含 `codesense://project_map` 的列表
    - `resources/read` 请求 `codesense://project_map` 能返回 Markdown 内容（mock summarizer）
    - 现有 Tool 测试 `tests/test_mcp_integration.py` 全部通过（不破坏 Tool 功能）
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过
  - 依赖: RES-1

---

## 缺陷记录
