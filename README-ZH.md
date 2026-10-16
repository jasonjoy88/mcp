# multica-mcp（Python）

基于 **Model Context Protocol（MCP）** 的 Multica 服务端实现（Python）。  
本地编码 Agent（Cursor、Claude Code、OpenCode、Codex 等）可通过本服务读写 Multica 工作区资源。

- 对齐 Multica REST API **v0.3.31**
- 包版本：**0.2.0**（`pyproject.toml` / `src/multica_mcp/version.py`）
- 要求 **Python ≥ 3.11**

英文说明：[README.md](README.md)

---

## 能力总览

### MCP 面

| 能力 | 说明 |
|------|------|
| 工具数量 | **16** 个：`9` 读 + `7` 写 |
| 只读模式 | `MULTICA_READ_ONLY=true` 时从 MCP 目录中移除全部写工具 |
| 演练模式 | 创建/更新类写工具支持 `dry_run`（校验/预览，不落库） |
| 传输方式 | `stdio`（IDE 默认）与 `http`（SSE，路径 `/mcp`） |
| HTTP 鉴权 | 可选 `MCP_API_KEY`（Bearer）；按 IP 节流：**60s 内失败 5 次 → 封禁 15 分钟** |
| 工作区 | `MULTICA_WORKSPACE_SLUG` > `MULTICA_WORKSPACE_ID` > 仅一个工作区时自动探测 |
| 可观测性 | 结构化 JSON 日志；级别 `debug` / `info` / `warn` / `error` |

### 平台 / 客户端行为

| 能力 | 说明 |
|------|------|
| Multica 鉴权 | `Authorization: Bearer <MULTICA_TOKEN>` |
| 客户端标识 | 每个请求携带 `X-Client-Platform: mcp`、`X-Client-Version` |
| 工作区头 | 作用域 API 发送 `X-Workspace-Slug` 或 `X-Workspace-ID` |
| 指派类型推断 | 未传 `assignee_type` 时，先对照 Agent 列表，命中为 `agent`，否则 `member` |
| 负责人默认 | 建项带 `lead_id` 且未传 `lead_type` → 默认 `member` |
| 任务详情补全 | `get_task` 额外拉取评论与子任务（child issues） |
| 项目检索 | `list_projects` 带 `query` 走项目搜索 API |
| 任务检索 | 列表/搜索带文本时走 issue 全文搜索（标题/描述/评论） |
| Stage 屏障 | 可选 `stage`（≥ 1），对同级子问题做有序屏障分组 |
| Agent 管控 | `suppress_run`、`handoff_note`、`/note` 评论、`suppress_agent_ids`、触发预览 |
| 项目资源 | 建项可挂 Git 仓库（`url` / `label` / `ref` / `default_branch_hint`） |
| 本地拆解 | `plan_task_breakdown` **进程内**生成子任务方案，不写 Multica |
| Docker | 镜像默认 HTTP `:8080`、Asia/Shanghai 时区、TCP 健康检查 |

### 领域枚举（合法取值）

| 类型 | 取值 |
|------|------|
| 任务状态 | `backlog`、`todo`、`in_progress`、`in_review`、`done`、`blocked`、`cancelled` |
| 项目状态 | `planned`、`in_progress`、`paused`、`completed`、`cancelled` |
| 优先级 | `none`、`urgent`、`high`、`medium`、`low` |
| 指派/负责人类型 | `member`、`agent`、`squad` |

典型场景：Cursor 中列项目/查任务、TAPD 建项挂仓库、拆子任务、指派 Agent、预览评论触发等。

---

## 安装

```bash
cd multica-mcp-py
pip install -e .
```

开发依赖：

```bash
pip install -e ".[dev]"
```

入口：

- 命令：`multica-mcp`
- 模块：`python -m multica_mcp`

---

## 配置

环境变量示例见 [.env.example](.env.example)。

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `MULTICA_BASE_URL` | 是 | — | Multica 实例根地址 |
| `MULTICA_TOKEN` | 是 | — | 个人访问令牌（PAT，多为 `mul_` 前缀） |
| `MULTICA_WORKSPACE_ID` | 否\* | 自动 | 工作区 UUID |
| `MULTICA_WORKSPACE_SLUG` | 否\* | — | 工作区 slug，**优先于** ID |
| `MCP_TRANSPORT` | 否 | `stdio` | `stdio` 或 `http` |
| `MCP_HTTP_PORT` | 否 | `8080` | HTTP 监听端口 |
| `MCP_API_KEY` | 否 | — | HTTP Bearer；仅 HTTP 模式 |
| `LOG_LEVEL` | 否 | `info` | `debug` / `info` / `warn` / `error` |
| `MULTICA_READ_ONLY` | 否 | `false` | `true` 时关闭写工具 |

\* 需配置工作区 ID 或 slug；若账号下仅有一个工作区，可省略并自动探测。

---

## 使用方式

### IDE 集成（stdio，推荐）

```bash
multica-mcp
# 或
python -m multica_mcp
```

#### Cursor：`~/.cursor/mcp.json` 示例

```json
{
  "mcpServers": {
    "multica": {
      "command": "python",
      "args": ["-m", "multica_mcp"],
      "env": {
        "MULTICA_BASE_URL": "https://your-multica.example.com",
        "MULTICA_TOKEN": "mul_xxxxx",
        "MULTICA_WORKSPACE_SLUG": "your-slug",
        "MCP_TRANSPORT": "stdio",
        "LOG_LEVEL": "info",
        "MULTICA_READ_ONLY": "false"
      }
    }
  }
}
```

Windows 上若 MCP 进程找不到 `python`，请改用 `python.exe` 绝对路径。修改后需 **Reload MCP / 重启 Agent**。

### HTTP 服务

```bash
MCP_TRANSPORT=http MCP_HTTP_PORT=8080 MCP_API_KEY=secret multica-mcp
```

客户端连接 `http://<host>:8080/mcp`；若设置了 `MCP_API_KEY`：

```http
Authorization: Bearer <MCP_API_KEY>
```

### Docker

```bash
docker build -t multica-mcp:py .
docker run -d --name multica-mcp -p 8080:8080 \
  -e MULTICA_BASE_URL=https://your-multica.example.com \
  -e MULTICA_TOKEN=mul_xxxxx \
  -e MULTICA_WORKSPACE_SLUG=your-slug \
  -e MCP_TRANSPORT=http \
  -e MCP_API_KEY=your-secret \
  multica-mcp:py
```

---

## MCP 工具一览

### 读工具（9）

| 工具 | 能力 |
|------|------|
| `multica_list_projects` | 列出工作区项目；可选 `query` 按名称过滤 |
| `multica_get_project` | 按项目 ID 获取详情 |
| `multica_list_tasks` | 按 `project_id` / `status` / `assignee` / `query` 过滤；可选 `limit`（默认 100） |
| `multica_get_task` | 任务详情 + **评论** + **子任务**；支持 ID 或 `MUL-123` |
| `multica_search_tasks` | 全文搜索（必填 `query`）；可选 `project_id` / `status` / `limit` |
| `multica_list_agents` | 列出工作区 Agent；可选 `project_id` |
| `multica_plan_task_breakdown` | 按标题/描述（及可选 `project_context`）本地拆解子任务方案；**不写库** |
| `multica_preview_comment_triggers` | 预览评论将触发哪些 Agent（`task_id`、`content`，可选 `parent_id`） |
| `multica_preview_issue_triggers` | 预览创建/更新 issue 将触发的 Agent 运行（`issue_ids`、`is_create`、指派/状态等） |

### 写工具（7）

| 工具 | 能力 |
|------|------|
| `multica_create_project` | 创建项目（必填 `title`）；可设状态/优先级/负责人/起止日期；可选 Git `resources`；`dry_run` |
| `multica_create_task` | 在项目中建任务；支持指派（可推断类型）、`stage`、`dry_run` |
| `multica_create_subtask` | 在父任务下建子任务（继承项目）；`stage`、`dry_run` |
| `multica_update_task` | 更新标题/描述/状态/优先级/指派/阶段；`clear_stage`、`suppress_run`、`handoff_note`、`dry_run` |
| `multica_add_comment` | Markdown 评论；`/note` 不触发 Agent；`parent_id` 楼中楼；`suppress_agent_ids` |
| `multica_assign_task` | 指派给 `member` / `agent` / `squad` |
| `multica_create_task_with_subtasks` | 一次创建父任务 + 多个子任务；可共用指派；`dry_run` |

#### 建项资源与 TAPD 约定

`resources` 示例：

```json
[
  {
    "url": "https://git.example.com/group/svc.git",
    "label": "服务名",
    "ref": "feat-xxx",
    "default_branch_hint": "feat-xxx"
  }
]
```

从 TAPD 建项时建议配合 Skill **`multica-create-project`**：

- **标题**：`【用户组】TAPD标题`
- **描述**：第一行 TAPD 链接，第二行 `分支：<分支名>`
- **资源**：每个服务一条仓库；`ref` 必须为指定分支（勿只写 `default_branch_hint`）

---

## 项目结构

```
multica-mcp-py/
├── pyproject.toml
├── README.md              # 英文说明
├── README-ZH.md           # 本文件
├── 接入WorkBuddy.md       # WorkBuddy HTTP 接入
├── Dockerfile
├── .env.example
├── tests/
└── src/multica_mcp/
    ├── main.py            # 入口；stdio / HTTP
    ├── config.py          # 环境变量加载
    ├── version.py         # VERSION + MULTICA_API
    ├── logging_setup.py   # JSON 日志
    ├── domain/            # Pydantic 模型与枚举
    ├── multica/           # REST 客户端（httpx）
    ├── app/               # 业务用例 + 指派推断
    ├── mcp/               # MCP Server 与工具注册
    └── middleware/        # HTTP API Key + IP 节流
```

---

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy src/
```

---

## 排障速查

| 现象 | 排查方向 |
|------|----------|
| Cursor 无 `multica_*` 工具 | 检查 `mcp.json`；Reload MCP；确认 `python -m multica_mcp` 可导入 |
| workspace 相关错误 | 配置 `MULTICA_WORKSPACE_SLUG` 或 `ID`；多工作区不可依赖自动探测 |
| 401 / 403 | PAT 失效或权限不足；HTTP 模式核对 `MCP_API_KEY` |
| 写工具缺失 | 是否设置了 `MULTICA_READ_ONLY=true` |
| 改代码不生效 | `pip show multica-mcp` 的 Editable 路径须指向本仓，再 Reload MCP |

---

## 许可证

MIT（与 `pyproject.toml` 声明一致）。
