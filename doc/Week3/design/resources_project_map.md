# 详细设计 — `resources/project_map` 模块

> 对应文件：`src/codesense_v1/resources/project_map.py`
> 层级：L5 Resource 层
> 依赖：`codesense_v1.summarizer`、`codesense_v1.errors`、标准库

---

## 1. 模块功能说明

实现 MCP Resource `codesense://project_map` 的读取逻辑。读取 `CODESENSE_PROJECT_ROOT` 环境变量，调用 `summarizer.project_map_summary` 获取内容，处理错误并返回 Markdown 字符串（错误情况也返回 Markdown 而非抛 MCP 错误）。

---

## 2. 对外暴露的接口签名

```python
RESOURCE_URI: str  # = "codesense://project_map"
RESOURCE_NAME: str  # = "Project Architecture Map"
RESOURCE_DESCRIPTION: str  # = "项目整体架构概览（模块列表、依赖关系）"
RESOURCE_MIME_TYPE: str    # = "text/markdown"

async def read_project_map() -> str:
    """Read the project map resource content.

    Reads CODESENSE_PROJECT_ROOT from environment.
    Returns Markdown string — on error, returns a Markdown error description
    instead of raising.
    """
```

---

## 3. 核心数据结构定义

无自定义数据结构。仅常量和一个异步函数。

---

## 4. 错误码与异常处理规范

`read_project_map()` 捕获所有已知错误，返回 Markdown 格式的错误描述：

| 异常 | 返回 Markdown |
|------|--------------|
| `CODESENSE_PROJECT_ROOT` 未设置 | `"# 错误\n\n环境变量 `CODESENSE_PROJECT_ROOT` 未设置。请在 MCP 配置的 env 中添加该变量。"` |
| `FileNotFoundError`（DB 不存在） | `"# 错误\n\nCodeGraph 数据库不存在：{e}\n\n请先在目标项目中运行 `codegraph init -i`。"` |
| `LLMError` | `"# 错误\n\nLLM 调用失败：{e}\n\n请检查 `CODESENSE_LLM_API_KEY` 等环境变量配置。"` |
| 其他 `Exception` | `"# 错误\n\n内部错误：{type(e).__name__}: {e}"` |

---

## 5. 关键算法或业务逻辑说明

```python
async def read_project_map() -> str:
    project_root_str = os.environ.get("CODESENSE_PROJECT_ROOT", "")
    if not project_root_str:
        return _error_md("环境变量 `CODESENSE_PROJECT_ROOT` 未设置...")
    project_root = Path(project_root_str)
    try:
        return await summarizer.project_map_summary(project_root)
    except FileNotFoundError as e:
        return _error_md(f"CodeGraph 数据库不存在：{e}...")
    except LLMError as e:
        return _error_md(f"LLM 调用失败：{e}...")
    except Exception as e:
        return _error_md(f"内部错误：{type(e).__name__}: {e}")
```

---

## 6. 与其他模块的交互契约

| 依赖 | 使用方式 |
|------|---------|
| `summarizer` | `await summarizer.project_map_summary(project_root)` |
| `errors` | `LLMError`（用于 except 分支匹配） |

`server.py` 中绑定方式（L1 扩展）：

```python
from mcp.types import Resource, ReadResourceResult, TextResourceContents
from codesense_v1.resources import project_map as _pm

@server.list_resources()   # type: ignore[no-untyped-call, untyped-decorator]
async def _list_resources() -> list[Resource]:
    return [
        Resource(
            uri=AnyUrl(_pm.RESOURCE_URI),
            name=_pm.RESOURCE_NAME,
            description=_pm.RESOURCE_DESCRIPTION,
            mimeType=_pm.RESOURCE_MIME_TYPE,
        )
    ]

@server.read_resource()    # type: ignore[no-untyped-call, untyped-decorator]
async def _read_resource(uri: AnyUrl) -> ReadResourceResult:
    content = await _pm.read_project_map()
    return ReadResourceResult(
        contents=[TextResourceContents(uri=uri, mimeType=_pm.RESOURCE_MIME_TYPE, text=content)]
    )
```

> `list_resources` / `read_resource` 装饰器同样无 type stub，需 `# type: ignore`。
