# multica-mcp (Python)

Python implementation of the **Multica MCP Server**. Local coding agents
(Cursor, Claude Code, OpenCode, Codex, …) can read and write Multica workspace
resources through the [Model Context Protocol](https://modelcontextprotocol.io/).

- Targets Multica REST API **v0.3.31**
- this repo is the standalone Python package
- Package version: **0.2.0** (`pyproject.toml` / `src/multica_mcp/version.py`)
- Requires **Python ≥ 3.11**

中文说明：[README-ZH.md](README-ZH.md) 

---

## Capabilities

### MCP surface

| Area | Detail |
|------|--------|
| Tools | **16** total — **9** read + **7** write |
| Read-only mode | `MULTICA_READ_ONLY=true` omits all write tools from the MCP catalog |
| Dry-run | Mutating tools that create/update accept `dry_run` (validate / preview, no persist) |
| Transports | `stdio` (IDE default) and `http` (SSE at `/mcp`) |
| HTTP auth | Optional `MCP_API_KEY` (Bearer); IP login throttle: **5** failures / **60s** → ban **15 min** |
| Workspace | `MULTICA_WORKSPACE_SLUG` > `MULTICA_WORKSPACE_ID` > auto-detect if exactly one workspace |
| Observability | Structured JSON logging (`python-json-logger`); levels `debug` / `info` / `warn` / `error` |

### Platform / client behavior

| Capability | Detail |
|------------|--------|
| Auth to Multica | `Authorization: Bearer <MULTICA_TOKEN>` |
| Client identity | Every request sends `X-Client-Platform: mcp` and `X-Client-Version` |
| Workspace headers | `X-Workspace-Slug` or `X-Workspace-ID` on scoped APIs |
| Assignee inference | If `assignee_type` omitted, match ID against agent list → else `member` |
| Lead default | `create_project` with `lead_id` and no `lead_type` → `member` |
| Task enrichment | `get_task` also loads comments + child issues (subtasks) |
| Project search | `list_projects` with `query` uses project search API |
| Task search | Text query on list/search uses issue search (title / description / comments) |
| Stage barriers | Optional `stage` (≥ 1) groups sibling sub-issues for ordered barriers |
| Agent control | `suppress_run`, `handoff_note`, `/note` comments, `suppress_agent_ids`, trigger previews |
| Project resources | Create project can attach Git repos (`url` / `label` / `ref` / `default_branch_hint`) |
| Local planning | `plan_task_breakdown` builds a subtask plan **in-process** (no API writes) |
| Docker | Image defaults to HTTP on `:8080`, Asia/Shanghai TZ, TCP healthcheck |

### Domain enums (accepted values)

| Kind | Values |
|------|--------|
| Task status | `backlog`, `todo`, `in_progress`, `in_review`, `done`, `blocked`, `cancelled` |
| Project status | `planned`, `in_progress`, `paused`, `completed`, `cancelled` |
| Priority | `none`, `urgent`, `high`, `medium`, `low` |
| Assignee / lead type | `member`, `agent`, `squad` |

---

## Installation

```bash
cd multica-mcp-py
pip install -e .
```

With dev tools:

```bash
pip install -e ".[dev]"
```

Entry points:

- CLI: `multica-mcp`
- Module: `python -m multica_mcp`

---

## Configuration

See [`.env.example`](.env.example).

| Variable | Required | Default | Description |
|---|---|---|---|
| `MULTICA_BASE_URL` | yes | — | Multica instance root URL |
| `MULTICA_TOKEN` | yes | — | PAT (usually `mul_` prefix) |
| `MULTICA_WORKSPACE_ID` | no\* | auto | Workspace UUID |
| `MULTICA_WORKSPACE_SLUG` | no\* | — | Slug; takes precedence over ID |
| `MCP_TRANSPORT` | no | `stdio` | `stdio` or `http` |
| `MCP_HTTP_PORT` | no | `8080` | HTTP listen port |
| `MCP_API_KEY` | no | — | HTTP Bearer token (HTTP mode only) |
| `LOG_LEVEL` | no | `info` | `debug` / `info` / `warn` / `error` |
| `MULTICA_READ_ONLY` | no | `false` | Disable all write tools |

\* Provide a workspace ID/slug, or ensure the token sees exactly one workspace.

---

## Usage

### IDE (stdio)

```bash
multica-mcp
# or
python -m multica_mcp
```

#### Cursor `~/.cursor/mcp.json` example

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

Prefer an absolute path to `python.exe` on Windows if `python` is not on the MCP process PATH. Reload MCP / restart the agent after edits.

### HTTP server

```bash
MCP_TRANSPORT=http MCP_HTTP_PORT=8080 MCP_API_KEY=secret multica-mcp
```

Clients connect to `http://<host>:8080/mcp`. With `MCP_API_KEY` set:

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

## MCP Tools

### Read tools (9)

| Tool | Capability |
|---|---|
| `multica_list_projects` | List projects; optional `query` name filter |
| `multica_get_project` | Project details by ID |
| `multica_list_tasks` | Filter by `project_id` / `status` / `assignee` / `query`; optional `limit` (default 100) |
| `multica_get_task` | Task + description/status/assignee + **comments** + **subtasks**; accepts ID or `MUL-123` |
| `multica_search_tasks` | Full-text search (`query` required); optional `project_id` / `status` / `limit` |
| `multica_list_agents` | List workspace agents; optional `project_id` |
| `multica_plan_task_breakdown` | Local subtask plan from title/description (+ optional `project_context`); **no writes** |
| `multica_preview_comment_triggers` | Preview which agents a comment would trigger (`task_id`, `content`, optional `parent_id`) |
| `multica_preview_issue_triggers` | Preview agent runs for prospective create/update (`issue_ids`, `is_create`, assignee/status fields) |

### Write tools (7)

| Tool | Capability |
|---|---|
| `multica_create_project` | Create project (`title` required); `status` / `priority` / `lead_*` / dates; optional Git `resources`; `dry_run` |
| `multica_create_task` | Create task in a project; assignee (+ inferred type), `stage`, `dry_run` |
| `multica_create_subtask` | Create child under parent; inherits project; `stage`, `dry_run` |
| `multica_update_task` | Update title/description/status/priority/assignee/stage; `clear_stage`, `suppress_run`, `handoff_note`, `dry_run` |
| `multica_add_comment` | Markdown comment; `/note` skips agent triggers; `parent_id` threads; `suppress_agent_ids` |
| `multica_assign_task` | Assign to `member` / `agent` / `squad` |
| `multica_create_task_with_subtasks` | Parent + subtasks in one call; shared assignee; `dry_run` |

#### `multica_create_project` resources

```json
[
  {
    "url": "https://git.example.com/group/svc.git",
    "label": "service-name",
    "ref": "feat-xxx",
    "default_branch_hint": "feat-xxx"
  }
]
```

For TAPD-driven project creation, prefer skill **`multica-create-project`**: title `【group】TAPD title`; description = TAPD URL + `分支：<branch>`; each service as a resource with `ref` = branch.

---

## Project layout

```
multica-mcp-py/
├── pyproject.toml
├── README.md
├── README-ZH.md
├── 接入WorkBuddy.md
├── Dockerfile
├── .env.example
├── tests/
└── src/multica_mcp/
    ├── main.py              # entry; stdio / HTTP
    ├── config.py            # env loading
    ├── version.py           # VERSION + MULTICA_API
    ├── logging_setup.py     # JSON logging
    ├── domain/              # Pydantic models & enums
    ├── multica/             # REST client (httpx)
    ├── app/                 # use cases + assignee inference
    ├── mcp/                 # MCP server + tool handlers
    └── middleware/          # HTTP API key + IP throttle
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy src/
```

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No `multica_*` tools in Cursor | `mcp.json` path/JSON; Reload MCP; `python -m multica_mcp` imports |
| Workspace errors | Set `MULTICA_WORKSPACE_SLUG` or `ID`; multi-workspace needs an explicit choice |
| 401 / 403 | PAT expired/permissions; HTTP mode `MCP_API_KEY` mismatch |
| Write tools missing | `MULTICA_READ_ONLY=true` |
| Code changes ignored | `pip show multica-mcp` Editable path → this repo; then Reload MCP |

---

## License

MIT (see `pyproject.toml`).
