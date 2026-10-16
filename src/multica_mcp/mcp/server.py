"""MCP server implementation with Multica tools.

Mirrors the Go version's ``internal/mcp/server.go``.

Uses the official Python MCP SDK (``mcp`` package).
Tool definitions are registered via ``@server.list_tools()`` and
dispatched via ``@server.call_tool()``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

from ..app import UseCase
from ..domain import (
    AddCommentInput,
    AssignTaskInput,
    CreateProjectInput,
    CreateSubtaskInput,
    ProjectResourceDef,
    CreateTaskInput,
    CreateTaskWithSubtasksInput,
    GetProjectInput,
    GetTaskInput,
    ListAgentsInput,
    ListProjectsInput,
    ListTasksInput,
    PlanTaskBreakdownInput,
    PreviewCommentTriggersInput,
    PreviewIssueTriggersInput,
    SearchTasksInput,
    SubtaskDef,
    UpdateTaskInput,
)
from ..version import VERSION

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schema helpers
# ---------------------------------------------------------------------------


def _string_prop(name: str, description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _number_prop(name: str, description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _boolean_prop(name: str, description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _array_prop(name: str, description: str, item_type: str = "string") -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": item_type},
        "description": description,
    }


def _tool_schema(
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _make_tool(name: str, description: str, input_schema: dict[str, Any]) -> Tool:
    return Tool(name=name, description=description, inputSchema=input_schema)


# ---------------------------------------------------------------------------
# Tool definitions (match Go version exactly)
# ---------------------------------------------------------------------------


def _build_tools(read_only: bool) -> list[Tool]:
    """Build the list of MCP tools.

    When *read_only* is True, the 6 write tools are omitted.
    """
    tools: list[Tool] = []

    # ---- read tools ----

    tools.append(_make_tool(
        "multica_list_projects",
        "List projects in the Multica workspace. Optionally filter by name query.",
        _tool_schema(
            {"query": _string_prop("query", "Optional search query to filter projects by name")},
            required=None,
        ),
    ))

    tools.append(_make_tool(
        "multica_get_project",
        "Get detailed information about a specific project by ID.",
        _tool_schema(
            {"project_id": _string_prop("project_id", "Project ID")},
            required=["project_id"],
        ),
    ))

    tools.append(_make_tool(
        "multica_list_tasks",
        "List tasks in a project with optional filters for status, assignee, and text query.",
        _tool_schema(
            {
                "project_id": _string_prop("project_id", "Project ID to filter tasks"),
                "status": _string_prop("status", "Filter by status: backlog, todo, in_progress, in_review, done, blocked, cancelled"),
                "assignee": _string_prop("assignee", "Filter by assignee ID"),
                "query": _string_prop("query", "Optional text search query"),
                "limit": _number_prop("limit", "Maximum number of tasks to return (default 100)"),
            },
            required=None,
        ),
    ))

    tools.append(_make_tool(
        "multica_get_task",
        "Get a task with its description, status, assignee, comments, and subtasks.",
        _tool_schema(
            {"task_id": _string_prop("task_id", "Task ID or identifier (e.g. MUL-123)")},
            required=["task_id"],
        ),
    ))

    tools.append(_make_tool(
        "multica_search_tasks",
        "Search tasks by text across titles, descriptions, and comments.",
        _tool_schema(
            {
                "query": _string_prop("query", "Search query text"),
                "project_id": _string_prop("project_id", "Optional project ID to scope the search"),
                "status": _string_prop("status", "Optional status filter"),
                "limit": _number_prop("limit", "Maximum results to return"),
            },
            required=["query"],
        ),
    ))

    tools.append(_make_tool(
        "multica_list_agents",
        "List available agents in the workspace.",
        _tool_schema(
            {"project_id": _string_prop("project_id", "Optional project ID to filter agents")},
            required=None,
        ),
    ))

    tools.append(_make_tool(
        "multica_plan_task_breakdown",
        "Generate a structured plan of subtasks based on a task description. Does NOT create any tasks.",
        _tool_schema(
            {
                "title": _string_prop("title", "Task title"),
                "description": _string_prop("description", "Task description"),
                "project_context": _string_prop("project_context", "Optional project context for more relevant breakdown"),
            },
            required=["title", "description"],
        ),
    ))

    tools.append(_make_tool(
        "multica_preview_comment_triggers",
        "Preview which agents a comment would trigger before posting it.",
        _tool_schema(
            {
                "task_id": _string_prop("task_id", "Task ID"),
                "content": _string_prop("content", "Comment text to evaluate"),
                "parent_id": _string_prop("parent_id", "Optional parent comment ID for thread replies"),
            },
            required=["task_id", "content"],
        ),
    ))

    tools.append(_make_tool(
        "multica_preview_issue_triggers",
        "Preview which agent runs would start for a prospective issue create or update (assignee/status changes).",
        _tool_schema(
            {
                "issue_ids": _array_prop("issue_ids", "Issue IDs to evaluate for updates"),
                "is_create": _boolean_prop("is_create", "If true, preview a not-yet-created issue using assignee/status fields"),
                "assignee_type": _string_prop("assignee_type", "Prospective assignee type: member, agent, or squad"),
                "assignee_id": _string_prop("assignee_id", "Prospective assignee ID"),
                "status": _string_prop("status", "Prospective status for create or update preview"),
            },
            required=None,
        ),
    ))

    if read_only:
        return tools

    # ---- write tools ----

    resource_schema = {
        "type": "array",
        "description": "Optional git repos to attach (service warehouses). Prefer skill multica-create-project.",
        "items": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Git repository URL"},
                "label": {"type": "string", "description": "Service / display name"},
                "ref": {"type": "string", "description": "Checkout branch (required for feature branches)"},
                "default_branch_hint": {
                    "type": "string",
                    "description": "Optional; defaults to ref when omitted",
                },
            },
            "required": ["url"],
        },
    }

    tools.append(_make_tool(
        "multica_create_project",
        "Create a Multica project. For TAPD-driven creates, follow skill multica-create-project "
        "(title 【用户组】TAPD标题; description = TAPD URL + 分支：xxx; resources with ref=branch).",
        _tool_schema(
            {
                "title": _string_prop("title", "Project title, e.g. 【PMS组】采购平台监控指标开发"),
                "description": _string_prop(
                    "description",
                    "Prefer: <TAPD URL>\\n分支：<branch>",
                ),
                "status": _string_prop(
                    "status",
                    "Project status: planned, in_progress, paused, completed, cancelled (default planned)",
                ),
                "priority": _string_prop("priority", "Project priority: none, urgent, high, medium, low"),
                "lead_id": _string_prop("lead_id", "Optional lead member/agent/squad ID"),
                "lead_type": _string_prop(
                    "lead_type",
                    "Lead type: member, agent, or squad (defaults to member when lead_id is set)",
                ),
                "start_date": _string_prop("start_date", "Optional start date (YYYY-MM-DD)"),
                "due_date": _string_prop("due_date", "Optional due date (YYYY-MM-DD)"),
                "resources": resource_schema,
                "dry_run": _boolean_prop("dry_run", "If true, validate without creating"),
            },
            required=["title"],
        ),
    ))

    tools.append(_make_tool(
        "multica_create_task",
        "Create a new task in a project.",
        _tool_schema(
            {
                "project_id": _string_prop("project_id", "Project ID to create the task in"),
                "title": _string_prop("title", "Task title"),
                "description": _string_prop("description", "Task description (Markdown supported)"),
                "priority": _string_prop("priority", "Task priority: none, urgent, high, medium, low"),
                "assignee": _string_prop("assignee", "Assignee ID (member, agent, or squad)"),
                "assignee_type": _string_prop("assignee_type", "Assignee type: member, agent, or squad (inferred from agents list when omitted)"),
                "stage": _number_prop("stage", "Optional ordered stage (>= 1) for sub-issue barrier grouping under a parent"),
                "dry_run": _boolean_prop("dry_run", "If true, validate without creating"),
            },
            required=["project_id", "title", "description"],
        ),
    ))

    tools.append(_make_tool(
        "multica_create_subtask",
        "Create a subtask under an existing task.",
        _tool_schema(
            {
                "parent_task_id": _string_prop("parent_task_id", "Parent task ID"),
                "title": _string_prop("title", "Subtask title"),
                "description": _string_prop("description", "Subtask description"),
                "assignee": _string_prop("assignee", "Assignee ID"),
                "assignee_type": _string_prop("assignee_type", "Assignee type: member, agent, or squad"),
                "stage": _number_prop("stage", "Optional ordered stage (>= 1) for barrier grouping among sibling subtasks"),
                "dry_run": _boolean_prop("dry_run", "If true, validate without creating"),
            },
            required=["parent_task_id", "title", "description"],
        ),
    ))

    tools.append(_make_tool(
        "multica_update_task",
        "Update a task's title, description, status, priority, assignee, or stage. Use suppress_run to apply assignee/status changes without starting an agent run, and handoff_note to inject context when a run starts.",
        _tool_schema(
            {
                "task_id": _string_prop("task_id", "Task ID to update"),
                "title": _string_prop("title", "New title"),
                "description": _string_prop("description", "New description"),
                "status": _string_prop("status", "New status: backlog, todo, in_progress, in_review, done, blocked, cancelled"),
                "priority": _string_prop("priority", "New priority: none, urgent, high, medium, low"),
                "assignee": _string_prop("assignee", "New assignee ID. Pass an empty string to unassign."),
                "assignee_type": _string_prop("assignee_type", "Assignee type: member, agent, or squad"),
                "stage": _number_prop("stage", "Ordered stage (>= 1) for sub-issue barrier grouping"),
                "clear_stage": _boolean_prop("clear_stage", "If true, remove the task from its stage (unstage)"),
                "suppress_run": _boolean_prop("suppress_run", "If true, apply changes without enqueueing an agent run"),
                "handoff_note": _string_prop("handoff_note", "Optional handoff instruction injected when an agent run starts"),
                "dry_run": _boolean_prop("dry_run", "If true, validate without updating"),
            },
            required=["task_id"],
        ),
    ))

    tools.append(_make_tool(
        "multica_add_comment",
        "Add a comment to a task. Prefix the comment with /note to leave a human-only note that does not trigger agents. Use suppress_agent_ids to skip specific agents while still triggering others.",
        _tool_schema(
            {
                "task_id": _string_prop("task_id", "Task ID"),
                "comment": _string_prop("comment", "Comment text (Markdown supported). Prefix with /note to skip all agent triggers."),
                "parent_id": _string_prop("parent_id", "Optional parent comment ID for thread replies"),
                "suppress_agent_ids": _array_prop("suppress_agent_ids", "Optional agent IDs to exclude from comment-triggered runs"),
            },
            required=["task_id", "comment"],
        ),
    ))

    tools.append(_make_tool(
        "multica_assign_task",
        "Assign a task to a person or agent.",
        _tool_schema(
            {
                "task_id": _string_prop("task_id", "Task ID"),
                "assignee_id": _string_prop("assignee_id", "ID of the member, agent, or squad to assign"),
                "assignee_type": _string_prop("assignee_type", "Assignee type: member, agent, or squad"),
            },
            required=["task_id", "assignee_id"],
        ),
    ))

    # create_task_with_subtasks: subtasks is an array of objects
    subtask_items_schema = {
        "type": "object",
        "properties": {
            "title": _string_prop("title", "Subtask title"),
            "description": _string_prop("description", "Subtask description"),
        },
        "required": ["title", "description"],
    }
    tools.append(_make_tool(
        "multica_create_task_with_subtasks",
        "Create a parent task with subtasks in a single operation.",
        _tool_schema(
            {
                "project_id": _string_prop("project_id", "Project ID"),
                "title": _string_prop("title", "Parent task title"),
                "description": _string_prop("description", "Parent task description"),
                "subtasks": {
                    "type": "array",
                    "items": subtask_items_schema,
                    "description": "List of subtask definitions",
                },
                "assignee": _string_prop("assignee", "Assignee ID for parent and subtasks"),
                "assignee_type": _string_prop("assignee_type", "Assignee type: member, agent, or squad"),
                "dry_run": _boolean_prop("dry_run", "If true, validate without creating"),
            },
            required=["project_id", "title", "description", "subtasks"],
        ),
    ))

    return tools


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _json_result(data: Any) -> CallToolResult:
    """Serialize *data* to pretty-printed JSON and wrap it in a CallToolResult."""
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _error_result(op: str, err: Exception) -> CallToolResult:
    """Build an error CallToolResult."""
    logger.warning("tool error", extra={"operation": op, "error": str(err)})
    return CallToolResult(
        content=[TextContent(type="text", text=f"{op}: {err}")],
        isError=True,
    )


# ---------------------------------------------------------------------------
# Argument extraction helpers
# ---------------------------------------------------------------------------


def _arg_str(args: dict[str, Any], key: str) -> str:
    v = args.get(key)
    if v is None:
        return ""
    return str(v)


def _arg_str_opt(args: dict[str, Any], key: str) -> str | None:
    """Return the string value or None (empty string also becomes None)."""
    v = args.get(key)
    if v is None:
        return None
    s = str(v)
    if s == "":
        return None
    return s


def _arg_str_opt_or_empty(args: dict[str, Any], key: str) -> str | None:
    """Return the string value or None — empty string is preserved as '' (for unassign)."""
    v = args.get(key)
    if v is None:
        return None
    return str(v)


def _arg_int_opt(args: dict[str, Any], key: str) -> int | None:
    v = args.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _arg_bool(args: dict[str, Any], key: str) -> bool:
    v = args.get(key)
    if v is None:
        return False
    return bool(v)


def _arg_str_list(args: dict[str, Any], key: str) -> list[str]:
    v = args.get(key)
    if v is None:
        return []
    if isinstance(v, list):
        return [str(item) for item in v if item is not None]
    return []


# ---------------------------------------------------------------------------
# MCPServer wrapper
# ---------------------------------------------------------------------------


class MCPServer:
    """High-level wrapper around the MCP SDK server.

    Registers all multica tools and dispatches calls to the UseCase layer.
    """

    def __init__(self, use_case: UseCase, read_only: bool = False) -> None:
        self._use_case = use_case
        self._read_only = read_only
        self._server = Server("multica-mcp", version=VERSION)
        self._tools = _build_tools(read_only)
        self._register_handlers()

    @property
    def server(self) -> Server:
        """Return the underlying MCP SDK server."""
        return self._server

    def _register_handlers(self) -> None:
        server = self._server

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            return self._tools

        @server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
            return await self._handle_call(name, arguments)

    async def _handle_call(self, name: str, args: dict[str, Any]) -> CallToolResult:
        """Dispatch a tool call to the appropriate handler."""
        try:
            if name == "multica_list_projects":
                return await self._handle_list_projects(args)
            if name == "multica_get_project":
                return await self._handle_get_project(args)
            if name == "multica_list_tasks":
                return await self._handle_list_tasks(args)
            if name == "multica_get_task":
                return await self._handle_get_task(args)
            if name == "multica_search_tasks":
                return await self._handle_search_tasks(args)
            if name == "multica_list_agents":
                return await self._handle_list_agents(args)
            if name == "multica_plan_task_breakdown":
                return await self._handle_plan_task_breakdown(args)
            if name == "multica_preview_comment_triggers":
                return await self._handle_preview_comment_triggers(args)
            if name == "multica_preview_issue_triggers":
                return await self._handle_preview_issue_triggers(args)
            if name == "multica_create_project":
                return await self._handle_create_project(args)
            if name == "multica_create_task":
                return await self._handle_create_task(args)
            if name == "multica_create_subtask":
                return await self._handle_create_subtask(args)
            if name == "multica_update_task":
                return await self._handle_update_task(args)
            if name == "multica_add_comment":
                return await self._handle_add_comment(args)
            if name == "multica_assign_task":
                return await self._handle_assign_task(args)
            if name == "multica_create_task_with_subtasks":
                return await self._handle_create_task_with_subtasks(args)

            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                isError=True,
            )
        except Exception as exc:
            # Fallback error handler — per-tool handlers should catch their own
            logger.exception("unhandled tool error", extra={"tool": name})
            return _error_result(name, exc)

    # ---- read tool handlers ----

    async def _handle_list_projects(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = ListProjectsInput(query=_arg_str(args, "query"))
            projects = await self._use_case.list_projects(input)
            data = [p.model_dump(by_alias=True) for p in projects]
            return _json_result(data)
        except Exception as exc:
            return _error_result("list projects", exc)

    async def _handle_get_project(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = GetProjectInput(project_id=_arg_str(args, "project_id"))
            project = await self._use_case.get_project(input)
            return _json_result(project.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("get project", exc)

    async def _handle_list_tasks(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = ListTasksInput(
                project_id=_arg_str(args, "project_id"),
                status=_arg_str_opt(args, "status"),
                assignee=_arg_str_opt(args, "assignee"),
                query=_arg_str_opt(args, "query"),
                limit=_arg_int_opt(args, "limit"),
            )
            tasks = await self._use_case.list_tasks(input)
            data = [t.model_dump(by_alias=True, mode="json") for t in tasks]
            return _json_result(data)
        except Exception as exc:
            return _error_result("list tasks", exc)

    async def _handle_get_task(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = GetTaskInput(task_id=_arg_str(args, "task_id"))
            task = await self._use_case.get_task(input)
            return _json_result(task.model_dump(by_alias=True, mode="json"))
        except Exception as exc:
            return _error_result("get task", exc)

    async def _handle_search_tasks(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = SearchTasksInput(
                query=_arg_str(args, "query"),
                project_id=_arg_str_opt(args, "project_id"),
                status=_arg_str_opt(args, "status"),
                limit=_arg_int_opt(args, "limit"),
            )
            tasks = await self._use_case.search_tasks(input)
            data = [t.model_dump(by_alias=True, mode="json") for t in tasks]
            return _json_result(data)
        except Exception as exc:
            return _error_result("search tasks", exc)

    async def _handle_list_agents(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = ListAgentsInput(project_id=_arg_str_opt(args, "project_id"))
            agents = await self._use_case.list_agents(input)
            data = [a.model_dump(by_alias=True) for a in agents]
            return _json_result(data)
        except Exception as exc:
            return _error_result("list agents", exc)

    async def _handle_plan_task_breakdown(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = PlanTaskBreakdownInput(
                title=_arg_str(args, "title"),
                description=_arg_str(args, "description"),
                project_context=_arg_str_opt(args, "project_context"),
            )
            result = await self._use_case.plan_task_breakdown(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("plan task breakdown", exc)

    async def _handle_preview_comment_triggers(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = PreviewCommentTriggersInput(
                task_id=_arg_str(args, "task_id"),
                content=_arg_str(args, "content"),
                parent_id=_arg_str_opt(args, "parent_id"),
            )
            result = await self._use_case.preview_comment_triggers(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("preview comment triggers", exc)

    async def _handle_preview_issue_triggers(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = PreviewIssueTriggersInput(
                issue_ids=_arg_str_list(args, "issue_ids"),
                is_create=_arg_bool(args, "is_create"),
                assignee_type=_arg_str_opt(args, "assignee_type"),
                assignee_id=_arg_str_opt(args, "assignee_id"),
                status=_arg_str_opt(args, "status"),
            )
            result = await self._use_case.preview_issue_triggers(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("preview issue triggers", exc)

    # ---- write tool handlers ----

    async def _handle_create_project(self, args: dict[str, Any]) -> CallToolResult:
        try:
            resources_raw = args.get("resources") or []
            resources: list[ProjectResourceDef] = []
            if isinstance(resources_raw, list):
                for item in resources_raw:
                    if not isinstance(item, dict):
                        continue
                    resources.append(
                        ProjectResourceDef(
                            url=str(item.get("url") or ""),
                            label=item.get("label"),
                            ref=item.get("ref"),
                            default_branch_hint=item.get("default_branch_hint"),
                        )
                    )
            input = CreateProjectInput(
                title=_arg_str(args, "title"),
                description=_arg_str(args, "description"),
                status=_arg_str_opt(args, "status"),
                priority=_arg_str_opt(args, "priority"),
                lead_id=_arg_str_opt(args, "lead_id"),
                lead_type=_arg_str_opt(args, "lead_type"),
                start_date=_arg_str_opt(args, "start_date"),
                due_date=_arg_str_opt(args, "due_date"),
                resources=resources,
                dry_run=_arg_bool(args, "dry_run"),
            )
            result = await self._use_case.create_project(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("create project", exc)

    async def _handle_create_task(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = CreateTaskInput(
                project_id=_arg_str(args, "project_id"),
                title=_arg_str(args, "title"),
                description=_arg_str(args, "description"),
                priority=_arg_str_opt(args, "priority"),
                assignee=_arg_str_opt(args, "assignee"),
                assignee_type=_arg_str_opt(args, "assignee_type"),
                stage=_arg_int_opt(args, "stage"),
                dry_run=_arg_bool(args, "dry_run"),
            )
            result = await self._use_case.create_task(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("create task", exc)

    async def _handle_create_subtask(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = CreateSubtaskInput(
                parent_task_id=_arg_str(args, "parent_task_id"),
                title=_arg_str(args, "title"),
                description=_arg_str(args, "description"),
                assignee=_arg_str_opt(args, "assignee"),
                assignee_type=_arg_str_opt(args, "assignee_type"),
                stage=_arg_int_opt(args, "stage"),
                dry_run=_arg_bool(args, "dry_run"),
            )
            result = await self._use_case.create_subtask(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("create subtask", exc)

    async def _handle_update_task(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = UpdateTaskInput(
                task_id=_arg_str(args, "task_id"),
                title=_arg_str_opt(args, "title"),
                description=_arg_str_opt(args, "description"),
                status=_arg_str_opt(args, "status"),
                priority=_arg_str_opt(args, "priority"),
                assignee=_arg_str_opt_or_empty(args, "assignee"),
                assignee_type=_arg_str_opt(args, "assignee_type"),
                stage=_arg_int_opt(args, "stage"),
                clear_stage=_arg_bool(args, "clear_stage"),
                suppress_run=_arg_bool(args, "suppress_run"),
                handoff_note=_arg_str(args, "handoff_note"),
                dry_run=_arg_bool(args, "dry_run"),
            )
            result = await self._use_case.update_task(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("update task", exc)

    async def _handle_add_comment(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = AddCommentInput(
                task_id=_arg_str(args, "task_id"),
                comment=_arg_str(args, "comment"),
                parent_id=_arg_str_opt(args, "parent_id"),
                suppress_agent_ids=_arg_str_list(args, "suppress_agent_ids"),
            )
            result = await self._use_case.add_comment(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("add comment", exc)

    async def _handle_assign_task(self, args: dict[str, Any]) -> CallToolResult:
        try:
            input = AssignTaskInput(
                task_id=_arg_str(args, "task_id"),
                assignee_id=_arg_str(args, "assignee_id"),
                assignee_type=_arg_str_opt(args, "assignee_type"),
            )
            result = await self._use_case.assign_task(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("assign task", exc)

    async def _handle_create_task_with_subtasks(self, args: dict[str, Any]) -> CallToolResult:
        try:
            subtasks_raw = args.get("subtasks", [])
            if not isinstance(subtasks_raw, list):
                return CallToolResult(
                    content=[TextContent(type="text", text="create task with subtasks: subtasks must be an array")],
                    isError=True,
                )

            subtask_defs: list[SubtaskDef] = []
            for item in subtasks_raw:
                if not isinstance(item, dict):
                    continue
                subtask_defs.append(SubtaskDef(
                    title=str(item.get("title", "")),
                    description=str(item.get("description", "")),
                ))

            input = CreateTaskWithSubtasksInput(
                project_id=_arg_str(args, "project_id"),
                title=_arg_str(args, "title"),
                description=_arg_str(args, "description"),
                subtasks=subtask_defs,
                assignee=_arg_str_opt(args, "assignee"),
                assignee_type=_arg_str_opt(args, "assignee_type"),
                dry_run=_arg_bool(args, "dry_run"),
            )
            result = await self._use_case.create_task_with_subtasks(input)
            return _json_result(result.model_dump(by_alias=True))
        except Exception as exc:
            return _error_result("create task with subtasks", exc)
