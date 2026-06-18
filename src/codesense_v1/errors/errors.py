class ToolError(Exception):
    """工具领域异常基类。所有可预期的业务/校验错误都应继承自此类。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self._message = message

    @property
    def message(self) -> str:
        return self._message


class ValidationError(ToolError):
    """JSON Schema 校验失败时抛出。由 registry 在调用 handler 前抛出。"""


class InvalidArgumentError(ToolError):
    """业务级非法参数（schema 校验通过但语义非法），如 NaN / Infinity / 溢出。
    由工具实现内部抛出。"""


class LLMError(ToolError):
    """LLM API 调用失败（网络错误、超时、非 200 响应、返回空内容等）。
    由 llm.py 抛出，经 registry 转为 isError=true 响应。"""
