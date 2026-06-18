# 任务列表 — cache

## 模块说明
新建 `src/codesense_v1/cache.py`，管理 `.codesense/` 目录读写。

---

- [x] 任务ID: CACHE-1 — 实现 `cache.py` 及其单元测试
  - 输入: `doc/Week3/design/cache.md`
  - 输出:
    - `src/codesense_v1/cache.py`
    - `tests/test_cache.py`
  - 验收标准:
    - `db_hash(db_path)` 正常路径：文件存在 → 返回 64 位 hex 字符串
    - `db_hash(db_path)` 异常路径：文件不存在 → 抛 `FileNotFoundError`
    - `is_cache_valid` 正常路径：hash 匹配 → True；不匹配 → False；meta.json 不存在 → False
    - `read_project_map` / `write_project_map`：写后读回内容一致；write 同时创建 meta.json
    - `read_module` / `write_module`：写后读回 summary 一致；write 同时更新 meta.json
    - `invalidate`：调用后 read_project_map/read_module 均返回 None；is_cache_valid 返回 False
    - `module_key`：路径分隔符统一转为 `_`
    - `mypy --strict` 零错误
    - `ruff check` 零警告
    - `uv run pytest -q` 全部通过
  - 依赖: 无（无内部依赖）

---

## 缺陷记录
