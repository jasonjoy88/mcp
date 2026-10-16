# multica-mcp (Python)

Python implementation of the **Multica MCP Server** — lets local coding agents
(Cursor, Claude Code, OpenCode, Codex, …) read and write Multica workspace
resources through the Model Context Protocol.

Feature parity with Multica API **v0.3.31**. Originally ported from the Go
implementation ([multica-mcp](../multica-mcp)); this repository is the standalone
Python package.

## Features

- 15 MCP tools (9 read + 6 write)
- `stdio` transport (for IDE integration) and `http`/SSE transport (for remote deployments)
- Read-only mode (`MULTICA_READ_ONLY=true`)
- `dry_run` support on all mutating tools
- API key authentication with IP-based login throttling (HTTP mode)
- Workspace auto-detection when only one workspace exists

## Installation

```bash
cd multica-mcp-python
pip install -e .
```

With dev tools:

```bash
pip install -e ".[dev]"
```

## Configuration

Set the following environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `MULTICA_BASE_URL` | yes | — | Multica instance root URL |
| `MULTICA_TOKEN` | yes | — | PAT (usually `mul_` prefix) |
| `MULTICA_WORKSPACE_ID` | no\* | auto | Workspace UUID |
| `MULTICA_WORKSPACE_SLUG` | no\* | — | Slug; takes precedence over ID |
| `MCP_TRANSPORT` | no | `stdio` | `stdio` or `http` |
| `MCP_HTTP_PORT` | no | `8080` | HTTP port |
| `MCP_API_KEY` | no | — | HTTP Bearer token (HTTP mode only) |
| `LOG_LEVEL` | no | `info` | debug / info / warn / error |
| `MULTICA_READ_ONLY` | no | `false` | Disable all write tools |

\* Either a workspace ID/slug or a single auto-detectable workspace is required.

## Usage

### IDE integration (stdio, default)

```bash
multica-mcp
```

Or:

```bash
python -m multica_mcp
```

### HTTP server

```bash
MCP_TRANSPORT=http MCP_HTTP_PORT=8080 MCP_API_KEY=secret multica-mcp
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

## MCP Tools

### Read tools

| Tool | Description |
|---|---|
| `multica_list_projects` | List projects (optional name filter) |
| `multica_get_project` | Project details |
| `multica_list_tasks` | List tasks by project / status / assignee / query |
| `multica_get_task` | Task details with comments and subtasks |
| `multica_search_tasks` | Full-text search |
| `multica_list_agents` | List workspace agents |
| `multica_plan_task_breakdown` | Generate subtask plan locally (no writes) |
| `multica_preview_comment_triggers` | Preview which agents a comment would trigger |
| `multica_preview_issue_triggers` | Preview runs for issue create/update |

### Write tools

| Tool | Description |
|---|---|
| `multica_create_task` | Create a task (supports `stage`, `dry_run`) |
| `multica_create_subtask` | Create a subtask |
| `multica_update_task` | Update fields (`suppress_run`, `handoff_note`, `clear_stage`, …) |
| `multica_add_comment` | Add a comment (`/note`, `parent_id`, `suppress_agent_ids`) |
| `multica_assign_task` | Assign to member / agent / squad |
| `multica_create_task_with_subtasks` | Create parent + subtasks in one call |

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy src/
```

## Project layout

```
multica-mcp-python/
├── pyproject.toml
├── README.md
├── Dockerfile
├── .env.example
├── tests/
└── src/multica_mcp/
    ├── main.py              # entry point
    ├── config.py            # env var loading
    ├── version.py
    ├── domain/              # Pydantic models
    ├── multica/             # REST API client (httpx)
    ├── app/                 # business use cases
    ├── mcp/                 # MCP server + tool handlers
    └── middleware/          # HTTP auth + throttle
```
