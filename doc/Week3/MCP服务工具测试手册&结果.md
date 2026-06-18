# Week 3 成果测试手册

> 目标：在 `E:/Python_Project/CodeSense_V1` 仓库上验证 `project_map` Resource 和 `explore_module` Tool 可以正常工作。

---

## 前置检查

```bat
cd /d E:\Python_Project\CodeSense_V1
uv run pytest -q
```

应输出 `111 passed`，若有失败先解决。

---

## 步骤一：为当前仓库构建 CodeGraph 索引

Week 3 功能依赖 `.codegraph/codegraph.db`，需要先用 CodeGraph 对当前仓库建立索引：

```bat
cd /d E:\Python_Project\CodeSense_V1
codegraph init -i
```

成功后会生成 `.codegraph/codegraph.db`，可用以下命令确认：

```bat
dir .codegraph\codegraph.db
```

---

## 步骤二：启用 MCP Server

MCP 配置文件路径：

```
C:\Users\leikaixin\AppData\Roaming\Code\User\globalStorage\techcenter.codemaker\settings\codemaker_mcp_settings.json
```

当前 `codesense_v1` 段已配置好环境变量，只需将 `"disabled"` 改为 `false`：

```json
"codesense_v1": {
  "command": "codesense_v1",
  "env": {
    "CODESENSE_PROJECT_ROOT": "E:/Python_Project/CodeSense_V1",
    "CODESENSE_LLM_API_KEY": "sk-0M3b4zj6lj8tvtegdDqB2LUGw4ueiFLWDMJ1JbU5Ghv566Dz",
    "CODESENSE_LLM_BASE_URL": "https://api.gemai.cc/v1",
    "CODESENSE_LLM_MODEL": "deepseek-v4-flash"
  },
  "args": [],
  "timeout": 60,
  "type": "stdio",
  "disabled": false,
  "autoApprove": true
}
```

---

## 步骤三：验证 Server 启动正常

构建工具环境

```
uv tool install --editable "E:\Python_Project\CodeSense_V1" --reinstall
```

在 CodeMaker 的 MCP 面板确认 `codesense_v1` 出现，点击启用，应不报错。

工具列表应包含：

- `add`
- `explore_module`

如需手动验证，在终端运行（进程持续运行不退出即正常，Ctrl+C 退出）：

```bat
codesense_v1
```

---

## 步骤四：测试 `project_map` Resource

在 CodeMaker 对话框输入：

> 请读取 codesense://project_map 资源，告诉我这个项目的整体架构

**预期结果**：

- Agent 读取到 Markdown 格式的项目架构概览
- 内容包含模块列表（如 `codesense_v1.data`、`codesense_v1.tools` 等）和模块间依赖关系
- 首次调用会触发 LLM 生成（需要数秒），之后命中缓存秒级返回

**验证缓存已生成**：

```bat
dir E:\Python_Project\CodeSense_V1\.codesense\
```

应看到：

```
.codesense/
├── project_map.md
└── meta.json
```

---

## 步骤五：测试 `explore_module` Tool

在 CodeMaker 对话框输入：

> 调用 explore_module 工具，查询模块 "src/codesense_v1/data" 的架构信息

**预期结果**：

- `isError=false`，返回该模块的 Markdown 描述
- 内容包含：一句话描述、对外接口列表（`list_files`、`directory_tree`、`list_modules` 等）、内部文件、依赖模块

**也可测试其他模块**：

| 输入 module_path               | 说明          |
| ---------------------------- | ----------- |
| `src/codesense_v1`           | 顶层包（含所有子模块） |
| `src/codesense_v1/tools`     | Tools 包     |
| `src/codesense_v1/data`      | Data Layer  |
| `src/codesense_v1/resources` | Resource 层  |

**验证缓存已生成**：

```bat
dir E:\Python_Project\CodeSense_V1\.codesense\modules\
```

应看到对应的 `*.json` 文件。

---

## 步骤六：测试错误路径

**不存在的模块路径**：

> 调用 explore_module，module_path 为 "src/nonexistent"

预期：`isError=true`，文案含"模块路径不存在"。

**不是 Python 包的目录**（无 `__init__.py`）：

> 调用 explore_module，module_path 为 "doc"

预期：`isError=true`，文案含"不是 Python 包"。

---

## 步骤七：测试缓存失效

重新运行 `codegraph init -i`（更新 DB），再次调用任一工具，观察是否触发 LLM 重新生成（`.codesense/` 内容被清空后重写）。

---

## 常见问题

**Q：调用 explore_module 报"CodeGraph 数据库不存在"**
→ 先执行步骤一：`codegraph init -i`

**Q：调用工具报"LLM 调用失败"**
→ 检查网络、确认 `CODESENSE_LLM_API_KEY` 正确、确认 `CODESENSE_LLM_BASE_URL` 可访问

**Q：project_map Resource 显示"CODESENSE_PROJECT_ROOT 未设置"**
→ 确认 MCP 配置中 `env` 字段有 `CODESENSE_PROJECT_ROOT`，且已重启 VSCode

**Q：修改源码后如何生效**
→ 因为是 `--editable` 安装，重启 VSCode（重启 MCP Server 进程）即生效，无需重新 `uv tool install`

# 测试结果

## 步骤三

codesense_v1 MCP服务可正常启动，能够读取到工具

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-15-14-21-54-image.png)

<img title="" src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-22-18-image.png" alt="" width="822">

## 步骤四

可读取到项目整体架构

<img src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-54-16-image.png" title="" alt="" width="629"><img src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-54-32-image.png" title="" alt="" width="692">

## 步骤五

可返回查询模块的信息，其中包含一句话描述、对外接口列表（`list_files`、`directory_tree`、`list_modules` 等）、内部文件、依赖模块

<img title="" src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-35-02-image.png" alt="" width="703"><img title="" src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-35-18-image.png" alt="" width="681">

并将该模块信息缓存在E:\Python_Project\CodeSense_V1.codesense\modules\文件夹下

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-15-14-39-44-image.png)

再次查询相同模块沿用模块信息缓存

![](C:\Users\leikaixin\AppData\Roaming\marktext\images\2026-06-15-14-34-14-image.png)

## 步骤六

错误参数测试

<img src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-38-58-image.png" title="" alt="" width="637"><img src="file:///C:/Users/leikaixin/AppData/Roaming/marktext/images/2026-06-15-14-39-05-image.png" title="" alt="" width="613">
