"""Multica REST API client implementation.

Mirrors the Go version's ``internal/multica/client.go``.
All public methods are async.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..domain import (
    AddCommentInput,
    Agent,
    Comment,
    CommentTriggerPreview,
    CreateProjectInput,
    CreateTaskInput,
    IssueTriggerPreview,
    ListTasksInput,
    PreviewCommentTriggersInput,
    PreviewIssueTriggersInput,
    Project,
    Task,
    UpdateTaskInput,
    Workspace,
)

logger = logging.getLogger(__name__)


class MulticaAPIError(Exception):
    """Raised when the Multica API returns a non-2xx status code."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"multica api error: status={status_code} message={message}")


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _unwrap_list(data: Any, key: str) -> list[Any]:
    """Accept either a bare JSON array or an object wrapping the list under ``key``.

    Multica deployments may return ``[{...}]`` or ``{\"workspaces\": [{...}]}``.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = data.get(key, [])
        return items if isinstance(items, list) else []
    return []


def _parse_error_message(body: str) -> str:
    """Try to extract an ``error`` field from a JSON error response."""
    try:
        import json

        payload = json.loads(body)
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except Exception:
        pass
    return _truncate(body, 200)


class MulticaClient:
    """Async HTTP client for the Multica REST API.

    Args:
        base_url: Multica instance base URL (e.g. ``https://app.multica.ai``).
        token: Personal access token (usually ``mul_`` prefix).
        client_version: Version string sent in ``X-Client-Version`` header.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        client_version: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token.strip()
        self._client_version = client_version.strip()
        self._workspace_id: str = ""
        self._workspace_slug: str = ""
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # -- workspace scope ---------------------------------------------------

    def set_workspace_scope(self, workspace_id: str = "", slug: str = "") -> None:
        """Configure which workspace scoped APIs target.

        When *slug* is non-empty it is sent as ``X-Workspace-Slug`` (Multica
        resolves it first).  When only *workspace_id* is set it is sent as
        ``X-Workspace-ID``.
        """
        self._workspace_id = workspace_id.strip()
        self._workspace_slug = slug.strip()

    def _workspace_log_attrs(self) -> dict[str, str]:
        if self._workspace_slug:
            return {"workspace_slug": self._workspace_slug}
        return {"workspace_id": self._workspace_id}

    def _attach_workspace_headers(self, headers: dict[str, str]) -> None:
        if self._workspace_slug:
            headers["X-Workspace-Slug"] = self._workspace_slug
            return
        if self._workspace_id:
            headers["X-Workspace-ID"] = self._workspace_id
            return
        raise RuntimeError(
            "multica client: workspace scope not configured (call set_workspace_scope with id or slug)"
        )

    # -- generic request helper --------------------------------------------

    async def _do_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        scoped: bool = True,
    ) -> Any:
        """Execute an HTTP request and return the parsed JSON body.

        Raises:
            MulticaAPIError: on non-2xx responses.
            httpx.HTTPError: on transport errors.
        """
        url = self._base_url + path
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Client-Platform": "mcp",
        }
        if self._client_version:
            headers["X-Client-Version"] = self._client_version
        if scoped:
            self._attach_workspace_headers(headers)

        logger.debug("multica request", extra={"method": method, "path": path})

        response = await self._client.request(method, url, headers=headers, json=body)

        if response.status_code >= 400:
            text = response.text
            logger.debug(
                "api error response",
                extra={
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "body": _truncate(text, 500),
                },
            )
            raise MulticaAPIError(response.status_code, _parse_error_message(text))

        if response.content:
            return response.json()
        return None

    # -- workspaces --------------------------------------------------------

    async def list_workspaces(self) -> list[Workspace]:
        data = await self._do_request("GET", "/api/workspaces", scoped=False)
        items = _unwrap_list(data, "workspaces")
        return [Workspace(**item) for item in items]

    async def get_workspace(self, workspace_id: str) -> Workspace:
        data = await self._do_request("GET", f"/api/workspaces/{workspace_id}", scoped=False)
        return Workspace(**data)

    # -- projects ----------------------------------------------------------

    async def list_projects(self) -> list[Project]:
        data = await self._do_request("GET", "/api/projects")
        items = _unwrap_list(data, "projects")
        return [Project(**item) for item in items]

    async def search_projects(self, query: str) -> list[Project]:
        data = await self._do_request("GET", f"/api/projects/search?q={_quote(query)}")
        items = _unwrap_list(data, "projects")
        return [Project(**item) for item in items]

    async def get_project(self, project_id: str) -> Project:
        data = await self._do_request("GET", f"/api/projects/{project_id}")
        return Project(**data)

    async def create_project(self, input: CreateProjectInput) -> Project:
        body: dict[str, Any] = {"title": input.title}
        if input.description:
            body["description"] = input.description
        if input.status:
            body["status"] = input.status
        if input.priority:
            body["priority"] = input.priority
        if input.lead_id:
            body["lead_id"] = input.lead_id
            if input.lead_type:
                body["lead_type"] = input.lead_type
        if input.start_date:
            body["start_date"] = input.start_date
        if input.due_date:
            body["due_date"] = input.due_date
        if input.resources:
            body["resources"] = [
                {
                    "resource_type": "github_repo",
                    "label": r.label,
                    "position": i,
                    "resource_ref": {
                        k: v
                        for k, v in {
                            "url": r.url,
                            "ref": r.ref,
                            "default_branch_hint": r.default_branch_hint or r.ref,
                        }.items()
                        if v
                    },
                }
                for i, r in enumerate(input.resources)
            ]

        try:
            data = await self._do_request("POST", "/api/projects", body=body)
            project = Project(**data)
        except MulticaAPIError:
            if not input.resources:
                raise
            # Some servers reject embedded resources; create then attach.
            body.pop("resources", None)
            data = await self._do_request("POST", "/api/projects", body=body)
            project = Project(**data)
            for i, r in enumerate(input.resources):
                await self.create_project_resource(
                    project.id,
                    url=r.url,
                    label=r.label,
                    ref=r.ref,
                    default_branch_hint=r.default_branch_hint or r.ref,
                    position=i,
                )

        logger.info(
            "project created",
            extra={"project_id": project.id, "title": project.title, **self._workspace_log_attrs()},
        )
        return project

    async def create_project_resource(
        self,
        project_id: str,
        *,
        url: str,
        label: str | None = None,
        ref: str | None = None,
        default_branch_hint: str | None = None,
        position: int | None = None,
    ) -> dict[str, Any]:
        resource_ref: dict[str, Any] = {"url": url}
        if ref:
            resource_ref["ref"] = ref
        hint = default_branch_hint or ref
        if hint:
            resource_ref["default_branch_hint"] = hint
        body: dict[str, Any] = {
            "resource_type": "github_repo",
            "resource_ref": resource_ref,
        }
        if label:
            body["label"] = label
        if position is not None:
            body["position"] = position
        return await self._do_request("POST", f"/api/projects/{project_id}/resources", body=body)

    # -- tasks / issues ----------------------------------------------------

    async def list_tasks(self, opts: ListTasksInput) -> list[Task]:
        params: list[tuple[str, str]] = []
        if opts.project_id:
            params.append(("project_id", opts.project_id))
        if opts.status:
            params.append(("status", opts.status))
        if opts.assignee:
            params.append(("assignee_id", opts.assignee))
        if opts.limit is not None and opts.limit > 0:
            params.append(("limit", str(opts.limit)))
        query = _build_query(params)
        path = f"/api/issues{query}"
        data = await self._do_request("GET", path)
        items = data.get("issues", []) if isinstance(data, dict) else []
        return [Task(**item) for item in items]

    async def get_task(self, task_id: str) -> Task:
        data = await self._do_request("GET", f"/api/issues/{task_id}")
        return Task(**data)

    async def list_child_issues(self, parent_id: str) -> list[Task]:
        data = await self._do_request("GET", f"/api/issues/{parent_id}/children")
        items = data.get("issues", []) if isinstance(data, dict) else []
        return [Task(**item) for item in items]

    async def create_task(self, input: CreateTaskInput) -> Task:
        body: dict[str, Any] = {
            "title": input.title,
            "description": input.description,
        }
        if input.priority:
            body["priority"] = input.priority
        if input.assignee:
            body["assignee_id"] = input.assignee
            if input.assignee_type:
                body["assignee_type"] = input.assignee_type
        if input.project_id:
            body["project_id"] = input.project_id
        if input.parent_issue_id:
            body["parent_issue_id"] = input.parent_issue_id
        if input.stage is not None and input.stage >= 1:
            body["stage"] = input.stage

        data = await self._do_request("POST", "/api/issues", body=body)
        task = Task(**data)
        logger.info(
            "task created",
            extra={"task_id": task.id, "title": task.title, **self._workspace_log_attrs()},
        )
        return task

    async def update_task(self, task_id: str, input: UpdateTaskInput) -> Task:
        body: dict[str, Any] = {}
        if input.title is not None:
            body["title"] = input.title
        if input.description is not None:
            body["description"] = input.description
        if input.status is not None:
            body["status"] = input.status
        if input.priority is not None:
            body["priority"] = input.priority
        if input.assignee is not None:
            if input.assignee == "":
                body["assignee_id"] = None
                body["assignee_type"] = None
            else:
                body["assignee_id"] = input.assignee
                if input.assignee_type:
                    body["assignee_type"] = input.assignee_type
        if input.clear_stage:
            body["stage"] = None
        elif input.stage is not None:
            body["stage"] = input.stage
        if input.suppress_run:
            body["suppress_run"] = True
        if input.handoff_note:
            body["handoff_note"] = input.handoff_note

        data = await self._do_request("PUT", f"/api/issues/{task_id}", body=body)
        logger.info(
            "task updated",
            extra={"task_id": task_id, **self._workspace_log_attrs()},
        )
        return Task(**data)

    # -- comments ----------------------------------------------------------

    async def list_comments(self, issue_id: str) -> list[Comment]:
        data = await self._do_request("GET", f"/api/issues/{issue_id}/comments")
        items = data if isinstance(data, list) else []
        return [Comment(**item) for item in items]

    async def create_comment(self, input: AddCommentInput) -> Comment:
        body: dict[str, Any] = {"content": input.comment}
        if input.parent_id:
            body["parent_id"] = input.parent_id
        if input.suppress_agent_ids:
            body["suppress_agent_ids"] = input.suppress_agent_ids

        data = await self._do_request(
            "POST", f"/api/issues/{input.task_id}/comments", body=body
        )
        logger.info(
            "comment created",
            extra={
                "comment_id": data.get("id", ""),
                "issue_id": input.task_id,
                **self._workspace_log_attrs(),
            },
        )
        return Comment(**data)

    # -- trigger previews --------------------------------------------------

    async def preview_comment_triggers(
        self, input: PreviewCommentTriggersInput
    ) -> CommentTriggerPreview:
        body: dict[str, Any] = {"content": input.content}
        if input.parent_id:
            body["parent_id"] = input.parent_id

        data = await self._do_request(
            "POST", f"/api/issues/{input.task_id}/comments/trigger-preview", body=body
        )
        return CommentTriggerPreview(**data)

    async def preview_issue_triggers(
        self, input: PreviewIssueTriggersInput
    ) -> IssueTriggerPreview:
        body: dict[str, Any] = {}
        if input.issue_ids:
            body["issue_ids"] = input.issue_ids
        if input.is_create:
            body["is_create"] = True
        if input.assignee_type:
            body["assignee_type"] = input.assignee_type
        if input.assignee_id:
            body["assignee_id"] = input.assignee_id
        if input.status:
            body["status"] = input.status

        data = await self._do_request("POST", "/api/issues/preview-trigger", body=body)
        return IssueTriggerPreview(**data)

    # -- agents ------------------------------------------------------------

    async def list_agents(self) -> list[Agent]:
        data = await self._do_request("GET", "/api/agents")
        items = data if isinstance(data, list) else []
        return [Agent(**item) for item in items]

    # -- search ------------------------------------------------------------

    async def search_issues(
        self,
        query: str,
        project_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[Task]:
        params: list[tuple[str, str]] = [("q", query)]
        if project_id:
            params.append(("project_id", project_id))
        if status:
            params.append(("status", status))
        if limit is not None and limit > 0:
            params.append(("limit", str(limit)))
        path = f"/api/issues/search{_build_query(params)}"

        data = await self._do_request("GET", path)
        items = data.get("issues", []) if isinstance(data, dict) else []
        # Go version extracts the embedded Task from searchIssueItem
        # In Python/Pydantic we can just pick the fields that Task knows about
        result: list[Task] = []
        for item in items:
            # item may contain extra fields (match_source, matched_snippet)
            # Task model will ignore them via extra='ignore' or populate_by_name
            result.append(Task(**item))
        return result


# -- helpers ---------------------------------------------------------------


def _quote(value: str) -> str:
    """URL-encode a query parameter value."""
    from urllib.parse import quote

    return quote(value)


def _build_query(params: list[tuple[str, str]]) -> str:
    if not params:
        return ""
    from urllib.parse import urlencode

    return "?" + urlencode(params)
