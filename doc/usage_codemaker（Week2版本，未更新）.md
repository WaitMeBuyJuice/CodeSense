# CodeSense_V1 MCP 服务 — CodeMaker 使用指南

## 1. 服务命名速查

| 项                     | 名称                                    |
| --------------------- | ------------------------------------- |
| 项目目录                  | `e:\Python_Project\CodeSense_V1`      |
| Python 包              | `codesense_v1`                        |
| `pyproject.toml` 项目名  | `codesense-v1`                        |
| MCP `SERVER_NAME`（握手） | `CodeSense`                           |
| 命令行入口                 | `codesense_v1`                        |
| 暴露工具                  | `add(a: number, b: number) -> string` |

---

## 2. 准备环境（首次安装）

在项目根执行一次，将 `codesense_v1` 注册为全局命令：

```bat
uv tool install --editable "e:\Python_Project\CodeSense_V1"
```

完成后 `codesense_v1` 会出现在 `C:\Users\<你的用户名>\.local\bin\codesense_v1.exe`。

> **说明**：`--editable` 模式下，修改 `src/codesense_v1/` 下的源码**无需重新安装**，下次启动进程即生效。

可选烟雾测试（在项目目录下）：

```bat
cd /d e:\Python_Project\CodeSense_V1
uv sync
uv run pytest -q
```

应输出 `38 passed`。

---

## 3. 配置 CodeMaker

配置文件路径：

```
c:\Users\<你的用户名>\AppData\Roaming\Code\User\globalStorage\techcenter.codemaker\settings\codemaker_mcp_settings.json
```

在 `mcpServers` 内新增 `codesense_v1` 段，**不要动**已有的 `codesense` / `codegraph`：

```json
"codesense_v1": {
  "command": "codesense_v1",
  "args": [],
  "timeout": 60,
  "type": "stdio",
  "disabled": false,
  "autoApprove": true
}
```

完整示例（参考）：

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph",
      "args": ["serve", "--mcp"],
      "timeout": 60,
      "type": "stdio",
      "disabled": true,
      "autoApprove": true
    },
    "codesense": {
      "command": "codesense",
      "args": [],
      "timeout": 60,
      "type": "stdio",
      "disabled": true,
      "autoApprove": true
    },
    "codesense_v1": {
      "command": "codesense_v1",
      "args": [],
      "timeout": 60,
      "type": "stdio",
      "disabled": false,
      "autoApprove": true
    }
  }
}
```

> **无需路径**：`uv tool install --editable` 已将 `codesense_v1.exe` 注册到系统 PATH，与 `codegraph`/`codesense` 用法完全一致。其他用户只需在自己机器执行同一条安装命令即可。

---

## 4. 启用与重启

1. 保存 `codemaker_mcp_settings.json`
2. **完全关闭并重启 VSCode**（MCP 配置仅在启动时加载）

---

## 5. 验证服务已被识别

重启 VSCode 后：

- CodeMaker 工具/MCP 面板应出现 `codesense_v1`，工具列表含 `add`

- 若未出现，在终端手动验证：
  
  ```bat
  codesense_v1
  ```
  
  进程持续运行不退出即正常（按 Ctrl+C 终止）

---

## 6. 使用示例

在 CodeMaker 对话框输入：

> 帮我用 codesense_v1 算一下 3 加 5

Agent 调用 `add(a=3, b=5)`，返回 `"8"`。

| 调用                   | 返回                                      |
| -------------------- | --------------------------------------- |
| `add(3, 5)`          | `"8"`                                   |
| `add(-1, 1)`         | `"0"`                                   |
| `add(1.5, 2.5)`      | `"4.0"`                                 |
| `add(a=1)`（缺 b）      | `isError`：`"参数错误：缺失必填参数 'b'"`           |
| `add(a="x", b=1)`    | `isError`：`"参数错误：'a' 期望 number，收到 str"` |
| `add(a=1, b=2, c=3)` | `isError`：`"参数错误：不允许的多余参数 'c'"`         |

---

## 7. 常见问题

**Q1：CodeMaker 面板没出现 `codesense_v1`**

- 是否完全重启 VSCode？
- 执行 `where codesense_v1`，确认命令在 PATH 中
- 若不在，重跑 `uv tool install --editable "e:\Python_Project\CodeSense_V1"`

**Q2：源码改动后是否需要重新操作？**

- 不需要。`--editable` 安装后，改 `src/codesense_v1/` 下的代码，重启 MCP 进程（重启 VSCode）即生效，无需重新 `uv tool install`

**Q3：想暂时关闭服务**

- JSON 中把 `"disabled": false` 改回 `true`，重启 VSCode

**Q4：其他用户如何使用？**

1. 拿到项目目录（git clone 或拷贝）
2. 执行 `uv tool install --editable "<项目绝对路径>"`
3. 配置文件追加 `codesense_v1` 段，重启 VSCode
4. 无需改任何路径

---

## 8. 卸载

```bat
uv tool uninstall codesense-v1
```

然后从 JSON 中删除 `codesense_v1` 段并重启 VSCode。
