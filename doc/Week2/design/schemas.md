# 详细设计 - schemas 模块

> 路径：`src/codesense_v1/schemas.py`  
> 层级：L4 基础设施  
> 概要设计参考：`doc/design/overview.md` §2、§5 D5

---

## 1. 模块功能说明

集中存放所有工具的 JSON Schema 常量。每个常量描述一个工具的 `inputSchema`（参数结构 + 校验规则）。仅作为数据声明，不执行任何校验逻辑。

为什么单独成模块：
- 与工具实现解耦，未来可被文档生成、客户端示例复用。
- 便于集中检查 schema 一致性（如 `additionalProperties: false`）。

---

## 2. 对外暴露的接口签名

本模块为纯数据模块，导出常量：

```python
from typing import Final

ADD_INPUT_SCHEMA: Final[dict] = {
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "加数 a"},
        "b": {"type": "number", "description": "加数 b"},
    },
    "required": ["a", "b"],
    "additionalProperties": False,
}
```

类型注解要点：
- 全部使用 `Final[dict]` 标注，禁止运行时修改。
- 命名约定：`<TOOL_NAME_UPPER>_INPUT_SCHEMA`。

---

## 3. 核心数据结构定义

`dict` 结构遵循 [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)（与 `jsonschema` 库 `Draft202012Validator` 一致）。

约定字段：
| 字段 | 必填 | 取值 | 说明 |
|------|------|------|------|
| `type` | 是 | `"object"` | 工具入参必为对象 |
| `properties` | 是 | dict | 每个参数一项，含 `type` 与 `description` |
| `required` | 是 | list[str] | 所有必填参数名 |
| `additionalProperties` | 是 | `False` | 禁止多余参数（对应 FR-5） |

---

## 4. 错误码与异常处理规范

本模块不抛出任何异常。`Final` 标注仅作静态提示，运行时若被修改也不在本模块负责。

---

## 5. 关键算法或业务逻辑说明

无。

---

## 6. 与其他模块的交互契约

| 调用方 | 用法 | 约束 |
|--------|------|------|
| `tools/add` | `from codesense_v1.schemas import ADD_INPUT_SCHEMA` 后传入 `@tool(input_schema=...)` | 不得就地修改 |
| `registry` | 间接持有 schema 引用（通过 `ToolSpec.input_schema`），用于 `jsonschema.validate` | 不得修改 |
| `errors`、`server` | 不交互 | —— |

依赖方向：本模块**零内部依赖**，是依赖图叶子节点。
