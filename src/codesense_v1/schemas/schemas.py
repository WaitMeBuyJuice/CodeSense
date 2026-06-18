from typing import Final

ADD_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "加数 a"},
        "b": {"type": "number", "description": "加数 b"},
    },
    "required": ["a", "b"],
    "additionalProperties": False,
}

EXPLORE_MODULE_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "module_name": {
            "type": "string",
            "description": "project_map 中列出的模块名（如 '缓存层'）",
        }
    },
    "required": ["module_name"],
    "additionalProperties": False,
}

LIST_CACHED_MODULES_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

LIST_CACHED_INPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
