# 总体进度

> 子任务完成数 / 总数；模块全部完成方可勾选。
> 执行顺序遵守任务依赖（任务内 `依赖:` 字段）。

---

- [x] bootstrap (3/3)
- [x] errors (1/1)
- [x] schemas (1/1)
- [x] registry (1/1)
- [x] tools (2/2)
- [x] server (1/1)
- [x] tests (3/3)

合计：12/12

---

## 推荐执行顺序（按依赖拓扑）

1. B-1 → B-2 → B-3
2. E-1（errors）
3. S-1（schemas）
4. R-1（registry）
5. T-1 → T-2（tools）
6. SV-1（server）
7. TS-1（test_registry）→ TS-2（test_add）→ TS-3（test_mcp_integration）
