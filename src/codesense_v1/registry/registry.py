from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

import jsonschema
from mcp.types import CallToolResult, TextContent, Tool

from codesense_v1.errors import ToolError

ToolHandler = Callable[..., str | Awaitable[str]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, object]
    handler: ToolHandler


_REGISTRY: Final[dict[str, ToolSpec]] = {}


def tool(
    name: str,
    description: str,
    input_schema: dict[str, object],
) -> Callable[[ToolHandler], ToolHandler]:
    """装饰器：将被装饰函数注册为 MCP 工具。

    重复注册同名工具抛出 RuntimeError（启动期错误，非运行期）。
    被装饰函数原样返回，不做包装，便于单元测试直接调用。
    """

    def deco(fn: ToolHandler) -> ToolHandler:
        if name in _REGISTRY:
            raise RuntimeError(f"tool '{name}' already registered")
        _REGISTRY[name] = ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=fn,
        )
        return fn

    return deco


def list_tools() -> list[Tool]:
    """返回所有已注册工具的 mcp.types.Tool 列表（用于响应 tools/list）。"""
    return [
        Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
        )
        for spec in _REGISTRY.values()
    ]


def _error(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=msg)],
        isError=True,
    )


def _translate_jsonschema_error(error: jsonschema.ValidationError) -> str:
    validator = error.validator
    if validator == "required":
        # error.message 形如 "'b' is a required property"
        field = error.message.split("'")[1]
        return f"参数错误：缺失必填参数 '{field}'"
    if validator == "type":
        path = list(error.absolute_path)
        field = str(path[-1]) if path else "unknown"
        expected = str(error.validator_value)
        actual = type(error.instance).__name__
        return f"参数错误：'{field}' 期望 {expected}，收到 {actual}"
    if validator == "additionalProperties":
        # error.message 形如 "Additional properties are not allowed ('c' was unexpected)"
        msg = error.message
        start = msg.find("'")
        end = msg.find("'", start + 1)
        if start != -1 and end != -1:
            field = msg[start + 1 : end]
        else:
            instance: Any = error.instance
            schema: Any = error.schema
            properties: dict[str, Any] = schema.get("properties", {})
            extra = set(instance.keys()) - set(properties.keys())
            field = next(iter(extra), "unknown")
        return f"参数错误：不允许的多余参数 '{field}'"
    return f"参数错误：{error.message}"


async def dispatch(name: str, arguments: dict[str, object]) -> CallToolResult:
    """调用名为 name 的工具，返回 mcp.types.CallToolResult。
    永不抛异常：所有错误转为 isError=True 的结果。
    """
    spec = _REGISTRY.get(name)
    if spec is None:
        return _error(f"未知工具：'{name}'")

    schema_validator = jsonschema.Draft202012Validator(spec.input_schema)
    first_error = next(schema_validator.iter_errors(arguments), None)
    if first_error is not None:
        msg = _translate_jsonschema_error(first_error)
        return _error(msg)

    try:
        raw = spec.handler(**arguments)
        result: str
        if inspect.isawaitable(raw):
            result = await raw
        else:
            result = str(raw)
    except ToolError as e:
        return _error(e.message)
    except Exception as e:
        return _error(f"内部错误：{type(e).__name__}")

    return CallToolResult(
        content=[TextContent(type="text", text=str(result))],
        isError=False,
    )
