# 详细设计 — `llm` 模块

> 对应文件：`src/codesense_v1/llm.py`
> 层级：L7 基础设施层
> 依赖：`codesense_v1.errors`、`openai`（第三方）、标准库

---

## 1. 模块功能说明

封装对 OpenAI 兼容 API 的异步调用。从环境变量读取配置，提供单一公开函数 `call_llm(prompt)`，屏蔽 API 客户端细节。调用失败时抛 `LLMError`。

---

## 2. 对外暴露的接口签名

```python
async def call_llm(prompt: str) -> str:
    """Send a single user message to the LLM and return the response text.

    Raises:
        LLMError: if the API call fails for any reason.
    """
```

> 内部仅此一个公开符号。模块不暴露客户端实例或配置对象。

---

## 3. 核心数据结构定义

无自定义数据结构。配置通过以下常量在模块加载时从环境变量读取：

```python
_BASE_URL: str   # os.environ.get("CODESENSE_LLM_BASE_URL", "https://api.gemai.cc/v1")
_API_KEY: str    # os.environ["CODESENSE_LLM_API_KEY"]（缺失时 KeyError → 启动时暴露）
_MODEL: str      # os.environ.get("CODESENSE_LLM_MODEL", "deepseek-v4-flash")
```

> `_API_KEY` 缺失时在首次 `call_llm` 调用时抛 `LLMError`（而非模块加载时崩溃）。

---

## 4. 错误码与异常处理规范

```python
class LLMError(ToolError): ...   # 定义在 errors.py，此处仅使用
```

触发场景：
- 环境变量 `CODESENSE_LLM_API_KEY` 未设置
- API 返回非 200 响应
- 网络超时或连接失败
- 响应内容为空

错误文案格式：`"内部错误：LLMError — <原始错误描述>"`（不泄漏 API Key）。

---

## 5. 关键算法或业务逻辑说明

1. 模块顶层读取 3 个环境变量（`_BASE_URL`、`_API_KEY`、`_MODEL`）。
2. `call_llm(prompt)` 内部：
   a. 若 `_API_KEY` 为空字符串（环境变量值为空），抛 `LLMError("CODESENSE_LLM_API_KEY 未设置")`。
   b. 构造 `AsyncOpenAI(base_url=_BASE_URL, api_key=_API_KEY)` 客户端实例（每次调用新建，避免全局状态）。
   c. 调用 `client.chat.completions.create(model=_MODEL, messages=[{"role":"user","content":prompt}])`。
   d. 取 `response.choices[0].message.content`；若为 `None` 或空，抛 `LLMError("LLM 返回空内容")`。
   e. 返回 stripped 字符串。
   f. 任意异常（`openai.APIError`、`openai.APIConnectionError` 等）包装成 `LLMError`，原始消息附后。
3. 不做重试（按需求 FR-3.4）。

---

## 6. 与其他模块的交互契约

| 调用方 | 使用方式 |
|--------|---------|
| `summarizer.py` | `await llm.call_llm(prompt)` → `str`；若抛 `LLMError` 则向上传播 |

`llm.py` 不 import 任何内部模块（除 `errors.py`），不调用 `cache`、`data`、`summarizer`。
